import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import os
import requests
import urllib3
import plotly.express as px

# SSL 인증서 오류 우회 (사내망/프록시 환경 대응)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
old_request = requests.Session.request
requests.Session.request = lambda self, *args, **kwargs: old_request(self, *args, **kwargs | {'verify': False})

st.set_page_config(page_title="Personal Wealth Dashboard", layout="wide")

from streamlit_gsheets import GSheetsConnection

# 구글 시트 연결
def get_gsheets_connection():
    return st.connection("gsheets", type=GSheetsConnection)

# 데이터 로드
def load_assets():
    try:
        conn = get_gsheets_connection()
        # 시트 이름 'Assets'에서 데이터를 읽어옵니다. ttl="0m"으로 항상 최신 데이터를 가져옵니다.
        df = conn.read(worksheet="Assets", ttl="0m")
        
        # 빈 시트이거나 잘못된 데이터인 경우 초기화
        if df.empty or "Ticker" not in df.columns:
            return pd.DataFrame(columns=["Group", "Category", "Ticker", "Purchase Date", "Purchase Price", "Quantity", "Currency"])
            
        # 기존 마이그레이션 로직
        if "Category" not in df.columns:
            df.insert(0, "Category", "미국시장1")
            
        if "Purchase Price (USD)" in df.columns:
            df.rename(columns={"Purchase Price (USD)": "Purchase Price"}, inplace=True)
            
        if "Currency" not in df.columns:
            currencies = []
            for t in df["Ticker"]:
                if pd.isna(t):
                    currencies.append("USD")
                    continue
                if str(t).endswith(".KS") or str(t).endswith(".KQ") or str(t).startswith("http"):
                    currencies.append("KRW")
                else:
                    currencies.append("USD")
            df["Currency"] = currencies
            save_assets(df)
            
        if "Group" not in df.columns:
            df.insert(0, "Group", "기본계좌")
            save_assets(df)
            
        return df
    except Exception as e:
        print(f"Error loading assets from sheets: {e}")
        return pd.DataFrame(columns=["Group", "Category", "Ticker", "Purchase Date", "Purchase Price", "Quantity", "Currency"])

# 데이터 저장
def save_assets(df):
    try:
        conn = get_gsheets_connection()
        conn.update(worksheet="Assets", data=df)
    except Exception as e:
        print(f"Error saving assets to sheets: {e}")
        st.error(f"구글 시트 저장 실패: {e}")

def load_target_weights():
    try:
        conn = get_gsheets_connection()
        df = conn.read(worksheet="Targets", ttl="0m")
        if df.empty or "Category" not in df.columns:
            raise ValueError("Empty or invalid targets sheet")
        return df
    except Exception as e:
        print(f"Error loading targets from sheets: {e}")
        return pd.DataFrame([
            {"Category": "미국시장1", "Target (%)": 20.0},
            {"Category": "미국시장2", "Target (%)": 20.0},
            {"Category": "미국 외", "Target (%)": 30.0},
            {"Category": "채권", "Target (%)": 15.0},
            {"Category": "금", "Target (%)": 15.0}
        ])

def save_target_weights(df):
    try:
        conn = get_gsheets_connection()
        conn.update(worksheet="Targets", data=df)
    except Exception as e:
        print(f"Error saving targets to sheets: {e}")
        st.error(f"구글 시트 저장 실패: {e}")

import requests
from bs4 import BeautifulSoup
import urllib3
import re
urllib3.disable_warnings()

def fetch_metlife_data(base_url, start_dt, end_dt):
    try:
        url = base_url
        url = re.sub(r'stDate=\d+', f'stDate={start_dt.strftime("%Y%m%d")}', url)
        url = re.sub(r'edDate=\d+', f'edDate={end_dt.strftime("%Y%m%d")}', url)
        res = requests.get(url, verify=False, timeout=10)
        soup = BeautifulSoup(res.content.decode('utf-8', errors='replace'), 'html.parser')
        tables = soup.find_all('table')
        if not tables:
            return pd.Series(dtype=float)
        
        rows = tables[0].find_all('tr')
        dates = []
        prices = []
        for row in rows[1:]:
            th = row.find('th')
            tds = row.find_all('td')
            if th and tds:
                date_str = th.text.strip()
                price_str = tds[0].text.strip().replace(',', '')
                try:
                    dates.append(pd.to_datetime(date_str))
                    prices.append(float(price_str))
                except:
                    pass
        if dates and prices:
            series = pd.Series(prices, index=dates).sort_index()
            return series
    except Exception as e:
        print(f"Error fetching metlife: {e}")
    return pd.Series(dtype=float)

# 환율 및 시세 가져오기 (캐싱 적용)
@st.cache_data(ttl=3600)
def get_current_data(ticker):
    try:
        end_date = datetime.today()
        start_date = end_date - timedelta(days=5)
        
        if ticker.startswith("http"):
            series = fetch_metlife_data(ticker, start_date, end_date)
            if not series.empty:
                return series.iloc[-1]
            return None
            
        data = fdr.DataReader(ticker, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        if not data.empty:
            return data['Close'].iloc[-1]
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
    return None

@st.cache_data(ttl=86400)
def get_historical_exchange_rate(date_str):
    try:
        start_date = datetime.strptime(date_str, "%Y-%m-%d")
        end_date = start_date + timedelta(days=5) # 주말 대비 몇 일 여유분
        data = fdr.DataReader("USD/KRW", start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        if not data.empty:
            return data['Close'].iloc[0]
    except Exception as e:
        print(f"Error fetching historical exchange rate: {e}")
    return None

@st.cache_data(ttl=3600)
def fetch_history_data(tickers):
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=5*365)
    start_date_str = start_dt.strftime("%Y-%m-%d")
    
    hist_dict = {}
    for t in tickers:
        try:
            if t.startswith("http"):
                series = fetch_metlife_data(t, start_dt, end_dt)
                if not series.empty:
                    hist_dict[t] = series
            else:
                df = fdr.DataReader(t, start_date_str)
                if not df.empty:
                    hist_dict[t] = df['Close']
        except:
            pass
    
    if not hist_dict:
        return pd.DataFrame()
        
    hist_df = pd.DataFrame(hist_dict)
    hist_df = hist_df.ffill().bfill() # 누락된 휴일 데이터 채우기
    return hist_df

def check_password():
    """Returns `True` if the user had the correct password."""
    # 비밀번호 설정이 안 되어 있다면 일단 통과시킵니다.
    if "app_password" not in st.secrets:
        return True

    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # 보안을 위해 세션에서 비밀번호 삭제
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("🔒 Security")
        st.text_input("대시보드 접속 비밀번호를 입력하세요", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.title("🔒 Security")
        st.text_input("대시보드 접속 비밀번호를 입력하세요", type="password", on_change=password_entered, key="password")
        st.error("😕 비밀번호가 틀렸습니다. 다시 시도해주세요.")
        return False
    else:
        return True

def main():
    if not check_password():
        st.stop() # 비밀번호가 틀리면 여기서 앱 실행을 멈춤

    st.title("📈 Personal Wealth Dashboard")

    hide_amounts = st.toggle("👀 금액 숨기기 (공공장소 모드)", value=False)
    st.markdown("---")

    # 2. 현재 환율 가져오기
    current_krw_rate = get_current_data("USD/KRW")
    if current_krw_rate is None:
        st.error("현재 환율 정보를 가져오지 못했습니다. 임시로 1350원을 적용합니다.")
        current_krw_rate = 1350.0 # fallback

    st.write(f"**현재 달러/원 환율:** ₩{current_krw_rate:,.2f}")

    # 3. 자산 목록 및 가치 계산
    df = load_assets()
    
    if not df.empty:
        # 데이터프레임 복사본으로 작업
        display_df = df.copy()
        
        # 계산을 위한 리스트 준비
        hist_rates = []
        purch_krw = []
        tot_purch_usds = []
        curr_prices = []
        curr_usd_vals = []
        curr_krw_vals = []
        profits_usd = []
        profits_krw = []
        profits_pct = []
        fx_profits_krw = []
        asset_profits_krw = []

        # 각 행마다 시세 및 환율 조회
        for index, row in display_df.iterrows():
            # 과거 환율
            h_rate = get_historical_exchange_rate(row["Purchase Date"])
            if h_rate is None:
                h_rate = current_krw_rate # fallback
            hist_rates.append(h_rate)
            
            ticker = row["Ticker"]
            is_foreign = (row.get("Currency", "USD") == "USD")
            
            # 구입 금액 계산
            input_price = row["Purchase Price"]
            if is_foreign:
                total_purch_usd = input_price * row["Quantity"]
                purch_krw_val = total_purch_usd * h_rate
            else:
                purch_krw_val = input_price * row["Quantity"]
                total_purch_usd = purch_krw_val / h_rate if h_rate > 0 else 0
            
            purch_krw.append(purch_krw_val)
            tot_purch_usds.append(total_purch_usd)
            
            # 현재 시세
            c_price = get_current_data(ticker)
            if c_price is None:
                c_price = input_price # fallback if API fails
            curr_prices.append(c_price)
            
            # 현재 가치 계산
            if is_foreign:
                c_usd_val = c_price * row["Quantity"]
                c_krw_val = c_usd_val * current_krw_rate
            else:
                c_krw_val = c_price * row["Quantity"]
                c_usd_val = c_krw_val / current_krw_rate if current_krw_rate > 0 else 0
                
            curr_usd_vals.append(c_usd_val)
            curr_krw_vals.append(c_krw_val)
            
            # 수익률 계산
            p_usd = c_usd_val - total_purch_usd
            p_krw = c_krw_val - purch_krw_val
            p_pct = (p_krw / purch_krw_val) * 100 if purch_krw_val > 0 else 0
            
            # 환차익과 자산손익 분리
            if is_foreign:
                fx_p = total_purch_usd * (current_krw_rate - h_rate)
                asset_p = p_krw - fx_p
            else:
                fx_p = 0
                asset_p = p_krw
                
            profits_usd.append(p_usd)
            profits_krw.append(p_krw)
            profits_pct.append(p_pct)
            fx_profits_krw.append(fx_p)
            asset_profits_krw.append(asset_p)
            
        # 데이터프레임에 파생 컬럼 추가
        display_df["Historical Rate (KRW)"] = hist_rates
        display_df["Total Purchase (USD)"] = tot_purch_usds
        display_df["Total Purchase (KRW)"] = purch_krw
        display_df["Current Price (USD)"] = curr_prices
        display_df["Current Value (USD)"] = curr_usd_vals
        display_df["Current Value (KRW)"] = curr_krw_vals
        display_df["Asset Profit (KRW)"] = asset_profits_krw
        display_df["FX Profit (KRW)"] = fx_profits_krw
        display_df["Profit/Loss (KRW)"] = profits_krw
        display_df["Profit/Loss (%)"] = profits_pct

        # 체크박스 컬럼 추가
        display_df.insert(0, "그래프 표시", False)

        # 계산된 파생 컬럼들을 미리 문자열(콤마 및 기호 포함)로 포맷팅
        # 단, 에디터에서 원본 숫자값이 반환되어야 하는 컬럼(base_cols)은 제외
        editor_df = display_df.copy()
        editor_df["Historical Rate (KRW)"] = editor_df["Historical Rate (KRW)"].map("₩{:,.2f}".format)
        editor_df["Total Purchase (USD)"] = editor_df["Total Purchase (USD)"].map("${:,.2f}".format)
        editor_df["Total Purchase (KRW)"] = editor_df["Total Purchase (KRW)"].map("₩{:,.0f}".format)
        
        formatted_curr_prices = []
        for _, r in editor_df.iterrows():
            if r.get("Currency", "USD") == "USD":
                formatted_curr_prices.append(f"${r['Current Price (USD)']:,.2f}")
            else:
                formatted_curr_prices.append(f"₩{r['Current Price (USD)']:,.0f}")
        editor_df["Current Price (USD)"] = formatted_curr_prices
        
        editor_df["Current Value (USD)"] = editor_df["Current Value (USD)"].map("${:,.2f}".format)
        editor_df["Current Value (KRW)"] = editor_df["Current Value (KRW)"].map("₩{:,.0f}".format)
        editor_df["Asset Profit (KRW)"] = editor_df["Asset Profit (KRW)"].map("₩{:,.0f}".format)
        editor_df["FX Profit (KRW)"] = editor_df["FX Profit (KRW)"].map("₩{:,.0f}".format)
        editor_df["Profit/Loss (KRW)"] = editor_df["Profit/Loss (KRW)"].map("₩{:,.0f}".format)
        editor_df["Profit/Loss (%)"] = editor_df["Profit/Loss (%)"].map("{:,.2f}%".format)

        # column_config를 이용한 포맷팅 (st.data_editor 용)
        target_weights_df = load_target_weights()
        category_options = target_weights_df["Category"].tolist() + ["미분류"]

        col_config = {
            "그래프 표시": st.column_config.CheckboxColumn("📊 그래프 표시", default=False),
            "Group": st.column_config.TextColumn("증권사/계좌 (대분류)"),
            "Category": st.column_config.SelectboxColumn("자산 분류 (소분류)", options=category_options),
            "Ticker": st.column_config.TextColumn("티커"),
            "Purchase Date": st.column_config.TextColumn("매수 일자"),
            # 편집 가능한 숫자는 콤마가 있으면 오히려 수정시 불편할 수 있으나, 가독성을 위해 format 지정 
            "Purchase Price": st.column_config.NumberColumn("매수 단가 (수정가능)"), 
            "Quantity": st.column_config.NumberColumn("수량 (수정가능)"),
            "Currency": st.column_config.SelectboxColumn("통화", options=["USD", "KRW"]),
            
            # 아래 컬럼들은 문자열로 매핑되었으므로 TextColumn으로 취급(수정불가)
            "Historical Rate (KRW)": st.column_config.TextColumn("과거 환율", disabled=True),
            "Total Purchase (USD)": st.column_config.TextColumn("총 매수(USD)", disabled=True),
            "Total Purchase (KRW)": st.column_config.TextColumn("총 매수(KRW)", disabled=True),
            "Current Price (USD)": st.column_config.TextColumn("현재 시세", disabled=True),
            "Current Value (USD)": st.column_config.TextColumn("현재 가치(USD)", disabled=True),
            "Current Value (KRW)": st.column_config.TextColumn("현재 가치(KRW)", disabled=True),
            "Asset Profit (KRW)": st.column_config.TextColumn("자산 손익(KRW)", disabled=True),
            "FX Profit (KRW)": st.column_config.TextColumn("환차익(KRW)", disabled=True),
            "Profit/Loss (KRW)": st.column_config.TextColumn("수익/손실(KRW)", disabled=True),
            "Profit/Loss (%)": st.column_config.TextColumn("수익률(%)", disabled=True),
        }
        
        st.markdown("💡 **Tip:** 표 안의 값을 더블클릭하여 자유롭게 수정하거나, 가장 왼쪽 인덱스를 클릭하고 `Del` 키를 눌러 삭제할 수 있습니다. 수정을 완료하면 표 아래의 **저장** 버튼을 누르세요. <br/>좌측 **📊 그래프 표시** 체크박스를 켜시면 해당 자산만 차트에 나타납니다.", unsafe_allow_html=True)
        
        # 일괄 선택 옵션 추가
        col_sel1, col_sel2 = st.columns(2)
        with col_sel1:
            sel_groups = st.multiselect("📂 대분류(증권사/계좌) 일괄 선택", display_df["Group"].unique(), help="선택한 대분류에 속한 모든 자산이 아래 요약과 그래프에 반영됩니다.")
        with col_sel2:
            sel_categories = st.multiselect("🏷️ 소분류(자산 성격) 일괄 선택", display_df["Category"].unique(), help="선택한 소분류에 속한 모든 자산이 아래 요약과 그래프에 반영됩니다.")

        base_cols = ["Group", "Category", "Ticker", "Purchase Date", "Purchase Price", "Quantity", "Currency"]
        edited_display = st.data_editor(
            editor_df,
            column_config=col_config,
            use_container_width=True,
            num_rows="dynamic",
            height=int((len(editor_df) + 2) * 35) + 3,
            key="main_table_editor"
        )
        
        if st.button("수정/삭제 변경사항 저장"):
            edited_base = edited_display[base_cols]
            save_assets(edited_base)
            st.success("자산 정보가 성공적으로 업데이트 되었습니다!")
            st.rerun()

        selected_rows = edited_display.index[edited_display["그래프 표시"] == True].tolist()
        
        # 일괄 선택된 그룹이나 카테고리가 있다면 선택 목록에 추가
        if sel_groups:
            group_indices = edited_display.index[edited_display["Group"].isin(sel_groups)].tolist()
            selected_rows.extend(group_indices)
        if sel_categories:
            cat_indices = edited_display.index[edited_display["Category"].isin(sel_categories)].tolist()
            selected_rows.extend(cat_indices)
            
        selected_rows = list(set(selected_rows)) # 중복 제거


        # --- 자산 총액 변동 그래프 (표 바로 아래 배치) ---
        has_selection = len(selected_rows) > 0
        target_df = edited_display.loc[selected_rows] if has_selection else edited_display
        
        if has_selection:
            sel_tickers = target_df["Ticker"].tolist()
            if len(sel_tickers) <= 3:
                tickers_str = ", ".join(sel_tickers)
            else:
                tickers_str = f"{sel_tickers[0]} 외 {len(sel_tickers)-1}종목"
            st.subheader(f"📈 {tickers_str} 합산 가치 변동 추이")
            st.caption(f"선택하신 자산들의 원화 가치 변동입니다.")
        else:
            st.subheader("📈 현재 전체 포트폴리오 가치 변동 추이")
            st.caption("현재 보유중인 전체 자산 수량을 과거에도 동일하게 보유했다고 가정했을 때의 원화 가치 변동입니다.")
        
        unique_tickers = edited_display["Ticker"].unique().tolist()
        if "USD/KRW" not in unique_tickers:
            unique_tickers.append("USD/KRW")
            
        hist_data = fetch_history_data(unique_tickers)
        
        if not hist_data.empty and "USD/KRW" in hist_data.columns:
            total_series = pd.Series(0.0, index=hist_data.index)
            
            # 선택된 자산이 있으면 해당 자산만, 없으면 전체 사용
            
            for _, r in target_df.iterrows():
                ticker = r["Ticker"]
                qty = r["Quantity"]
                is_foreign = not (ticker.endswith(".KS") or ticker.endswith(".KQ") or ticker.startswith("http"))
                if ticker in hist_data.columns:
                    if is_foreign:
                        total_series += hist_data[ticker] * qty * hist_data["USD/KRW"]
                    else:
                        total_series += hist_data[ticker] * qty
            
            period = st.radio(
                "기간 선택",
                ["1D", "1W", "1M", "YTD", "6M", "1Y", "3Y", "5Y"],
                horizontal=True,
                index=5 # 기본값 1Y
            )

            today = datetime.today()
            if period == "1D": start_dt = today - timedelta(days=2)
            elif period == "1W": start_dt = today - timedelta(days=7)
            elif period == "1M": start_dt = today - timedelta(days=30)
            elif period == "YTD": start_dt = datetime(today.year, 1, 1)
            elif period == "6M": start_dt = today - timedelta(days=180)
            elif period == "1Y": start_dt = today - timedelta(days=365)
            elif period == "3Y": start_dt = today - timedelta(days=365*3)
            else: start_dt = today - timedelta(days=365*5)
                
            filtered_series = total_series[total_series.index >= start_dt]
            
            if not filtered_series.empty:
                first_val = filtered_series.iloc[0]
                last_val = filtered_series.iloc[-1]
                diff = last_val - first_val
                pct_change = (diff / first_val) * 100 if first_val > 0 else 0
                
                chart_df = filtered_series.reset_index()
                chart_df.columns = ["Date", "Total Value (KRW)"]
                
                if hide_amounts:
                    st.metric("선택한 기간 내 자산 변동", "********", f"{pct_change:+.2f}%")
                    if first_val > 0:
                        chart_df["Total Value (KRW)"] = (chart_df["Total Value (KRW)"] / first_val) * 100
                    fig2 = px.line(chart_df, x="Date", y="Total Value (KRW)", color_discrete_sequence=["#2ca02c"])
                    fig2.update_layout(xaxis_title="", yaxis_title="상대 가치 (시작점=100)", margin=dict(t=10, b=10, l=10, r=10), hovermode="x unified")
                else:
                    st.metric("선택한 기간 내 자산 변동", f"₩{last_val:,.0f}", f"{diff:,.0f} 원 ({pct_change:+.2f}%)")
                    fig2 = px.line(chart_df, x="Date", y="Total Value (KRW)", color_discrete_sequence=["#2ca02c"])
                    fig2.update_layout(xaxis_title="", yaxis_title="원화(₩)", margin=dict(t=10, b=10, l=10, r=10), hovermode="x unified")
                    
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.warning("선택한 기간에 해당하는 데이터가 없습니다.")

        # 요약 정보 표시 (선택된 자산 기준, 없으면 전체)
        calc_df = display_df.loc[selected_rows] if (has_selection and len(selected_rows) < len(display_df)) else display_df
        
        total_purchase_krw = calc_df["Total Purchase (KRW)"].sum()
        total_current_krw = calc_df["Current Value (KRW)"].sum()
        total_current_usd = calc_df["Current Value (USD)"].sum()
        total_profit_krw = total_current_krw - total_purchase_krw
        total_profit_pct = (total_profit_krw / total_purchase_krw) * 100 if total_purchase_krw > 0 else 0
        total_asset_profit_krw = calc_df["Asset Profit (KRW)"].sum()
        total_fx_profit_krw = calc_df["FX Profit (KRW)"].sum()

        st.markdown("---")
        if has_selection and len(selected_rows) < len(display_df):
            st.subheader("📌 선택된 자산 요약")
        else:
            st.subheader("총 자산 요약")
        
        def display_metric(label, value, is_pct=False, prefix="₩"):
            if hide_amounts:
                return "********"
            if is_pct:
                return f"{value:,.2f}%"
            if prefix == "$":
                return f"${value:,.2f}"
            return f"{prefix}{value:,.0f}"

        col1, col2, col3 = st.columns(3)
        col1.metric("총 매수 금액 (원화 환산)", display_metric("총 매수 금액 (원화 환산)", total_purchase_krw))
        col2.metric("현재 총 자산 (원화)", display_metric("현재 총 자산 (원화)", total_current_krw), display_metric("수익", total_profit_krw, prefix="") if not hide_amounts else None)
        col3.metric("현재 총 자산 (달러)", display_metric("현재 총 자산 (달러)", total_current_usd, prefix="$"))
        
        st.write("")
        col4, col5, col6 = st.columns(3)
        col4.metric("총 수익률 (원화 기준)", display_metric("총 수익률 (원화 기준)", total_profit_pct, is_pct=True))
        col5.metric("총 자산 손익 (원화)", display_metric("총 자산 손익 (원화)", total_asset_profit_krw))
        col6.metric("총 환차익 (원화)", display_metric("총 환차익 (원화)", total_fx_profit_krw))

        # 1. 자산 분류(소분류)별 비율 분석
        st.markdown("---")
        st.subheader("📊 자산 포트폴리오 비중 (소분류)")
        
        target_weights_df = load_target_weights()
        target_categories = target_weights_df["Category"].tolist()
        
        # 목표 비중에 정의된 카테고리에 속한 자산만 필터링하여 총합 계산
        filtered_display_df = display_df[display_df["Category"].isin(target_categories)]
        target_total_krw = filtered_display_df["Current Value (KRW)"].sum()
        
        category_df = filtered_display_df.groupby("Category")["Current Value (KRW)"].sum().reset_index()
        category_df["Ratio (%)"] = (category_df["Current Value (KRW)"] / target_total_krw) * 100 if target_total_krw > 0 else 0
        
        # 목표 비중과 비교할 수 있도록 병합 (정의된 카테고리가 모두 나오도록)
        category_df = pd.merge(target_weights_df, category_df, on="Category", how="left").fillna(0)
        
        col_chart, col_table = st.columns([1, 1.3])
        
        with col_chart:
            # 값이 0보다 큰 카테고리만 차트에 표시
            plot_df = category_df[category_df["Current Value (KRW)"] > 0]
            if not plot_df.empty:
                fig = px.pie(plot_df, values='Current Value (KRW)', names='Category', hole=0.4, 
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("포트폴리오에 자산이 없습니다.")
            
        with col_table:
            st.write("<br>", unsafe_allow_html=True)
            
            # 과부족 계산 (전체 자산이 아닌 '목표에 정의된 자산들의 총합' 기준)
            table_df = category_df.copy()
            table_df["목표 금액"] = (target_total_krw * table_df["Target (%)"] / 100)
            table_df["과부족 금액"] = table_df["Current Value (KRW)"] - table_df["목표 금액"]
            table_df["비중 차이"] = table_df["Ratio (%)"] - table_df["Target (%)"]
            
            # 출력용 테이블 생성
            display_table = table_df[["Category", "Target (%)", "Ratio (%)", "비중 차이", "Current Value (KRW)", "과부족 금액"]].copy()
            display_table.columns = ["자산 분류", "목표 비중", "현재 비중", "비중 차이", "현재 금액", "과부족 금액"]
            
            # 포맷팅
            display_table["목표 비중"] = display_table["목표 비중"].map("{:.1f}%".format)
            display_table["현재 비중"] = display_table["현재 비중"].map("{:.1f}%".format)
            display_table["비중 차이"] = display_table["비중 차이"].apply(lambda x: f"{x:+.1f}%p")
            
            display_table["현재 금액"] = display_table["현재 금액"].map("₩{:,.0f}".format)
            display_table["과부족 금액"] = display_table["과부족 금액"].apply(lambda x: f"₩{x:+,.0f}")
            
            st.dataframe(display_table, use_container_width=True, hide_index=True, height=int((len(display_table) + 1.5) * 35))

        # 2. 계좌/증권사(대분류)별 비율 분석
        st.markdown("---")
        st.subheader("🏢 계좌/증권사별 비중 (대분류)")
        
        group_df = display_df.groupby("Group")["Current Value (KRW)"].sum().reset_index()
        group_df["Ratio (%)"] = (group_df["Current Value (KRW)"] / total_current_krw) * 100 if total_current_krw > 0 else 0
        
        col_g_chart, col_g_table = st.columns([1, 1.3])
        with col_g_chart:
            plot_g_df = group_df[group_df["Current Value (KRW)"] > 0]
            if not plot_g_df.empty:
                fig_g = px.pie(plot_g_df, values='Current Value (KRW)', names='Group', hole=0.4, 
                               color_discrete_sequence=px.colors.qualitative.Set2)
                fig_g.update_traces(textposition='inside', textinfo='percent+label')
                fig_g.update_layout(margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig_g, use_container_width=True)
        with col_g_table:
            st.write("<br>", unsafe_allow_html=True)
            g_display = group_df.copy()
            g_display.columns = ["계좌/증권사 (대분류)", "현재 금액", "현재 비중"]
            g_display = g_display[["계좌/증권사 (대분류)", "현재 비중", "현재 금액"]]
            g_display["현재 비중"] = g_display["현재 비중"].map("{:.1f}%".format)
            g_display["현재 금액"] = g_display["현재 금액"].map("₩{:,.0f}".format)
            st.dataframe(g_display, use_container_width=True, hide_index=True, height=int((len(g_display) + 1.5) * 35))

        # 자산 총액 변동 그래프




    else:
        st.info("아래 폼에서 자산을 추가하거나 구글 시트에서 입력해주세요.")

    st.markdown("---")
    st.header("새로운 자산 추가")
    with st.form("add_asset_form"):
        target_weights_df = load_target_weights()
        category_options = target_weights_df["Category"].tolist() + ["미분류"]
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            group = st.text_input("증권사/계좌 (대분류)", "기본계좌")
            category = st.selectbox("자산 분류 (소분류)", category_options)
            ticker_input = st.text_input("티커 또는 메트라이프 공시 URL", "")
            purchase_date_str = st.text_input("구매 일자 (YYYY-MM-DD)", datetime.today().strftime("%Y-%m-%d"))
        with col_f2:
            purchase_price = st.number_input("구입 금액 (1주당 가격 또는 기준가)", min_value=0.0, format="%.2f")
            currency = st.radio("구입 통화", ["USD (달러)", "KRW (원화)"], horizontal=True)
            quantity = st.number_input("수량", min_value=0.0, format="%.4f")
            
        submit_button = st.form_submit_button(label="추가")

        if submit_button:
            ticker = ticker_input.strip()
            if not ticker.startswith("http"):
                ticker = ticker.upper()
                
            try:
                valid_date = datetime.strptime(purchase_date_str, "%Y-%m-%d")
                is_valid_date = True
            except ValueError:
                is_valid_date = False
                
            if ticker and purchase_price > 0 and quantity > 0 and is_valid_date:
                df = load_assets()
                currency_code = "USD" if "USD" in currency else "KRW"
                new_row = pd.DataFrame([{
                    "Group": group,
                    "Category": category,
                    "Ticker": ticker,
                    "Purchase Date": valid_date.strftime("%Y-%m-%d"),
                    "Purchase Price": purchase_price,
                    "Quantity": quantity,
                    "Currency": currency_code
                }])
                df = pd.concat([df, new_row], ignore_index=True)
                save_assets(df)
                st.success(f"{ticker} 자산이 추가되었습니다!")
                st.rerun()
            else:
                st.error("모든 항목을 올바르게 입력해주세요. (날짜는 YYYY-MM-DD 형식)")

    st.markdown("---")
    with st.expander("🎯 자산 분류 및 목표 비중 커스텀 설정", expanded=False):
        st.caption("새로운 자산 분류를 추가하거나, 목표 비중(%)을 수정할 수 있습니다. 변경 후 아래 '저장' 버튼을 누르세요. (표를 클릭해서 바로 수정/추가/삭제 가능)")
        
        # 여기서 다시 로드(혹시 모를 상태 꼬임 방지)
        current_targets_df = load_target_weights()
        edited_targets = st.data_editor(
            current_targets_df,
            num_rows="dynamic",
            use_container_width=True,
            key="target_weights_editor",
            column_config={
                "Category": st.column_config.TextColumn("자산 분류 (Category)", required=True),
                "Target (%)": st.column_config.NumberColumn("목표 비중 (%)", min_value=0.0, max_value=100.0, required=True, format="%.1f")
            }
        )
        
        if st.button("목표 비중 저장", type="primary"):
            save_target_weights(edited_targets)
            st.success("새로운 자산 분류와 목표 비중이 저장되었습니다!")
            st.rerun()

if __name__ == "__main__":
    main()

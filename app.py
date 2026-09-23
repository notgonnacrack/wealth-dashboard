import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

def get_kst_today():
    return datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)
import os
import requests
import urllib3
import plotly.express as px

# SSL ?¸ì¦???¤ë¥˜ ?°íšŒ (?¬ë‚´ë§??„ë¡???˜ê²½ ?€??
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
old_request = requests.Session.request
requests.Session.request = lambda self, *args, **kwargs: old_request(self, *args, **kwargs | {'verify': False})

st.set_page_config(page_title="Personal Wealth Dashboard", layout="wide")

from streamlit_gsheets import GSheetsConnection

# êµ¬ê? ?œíŠ¸ ?°ê²°
def get_gsheets_connection():
    return st.connection("gsheets", type=GSheetsConnection)

# ?°ì´??ë¡œë“œ
def load_assets():
    try:
        conn = get_gsheets_connection()
        # ?œíŠ¸ ?´ë¦„ 'Assets'?ì„œ ?°ì´?°ë? ?½ì–´?µë‹ˆ?? ttl="0m"?¼ë¡œ ??ƒ ìµœì‹  ?°ì´?°ë? ê°€?¸ì˜µ?ˆë‹¤.
        df = conn.read(worksheet="Assets", ttl="0m")
        
        # ë¹??œíŠ¸?´ê±°???˜ëª»???°ì´?°ì¸ ê²½ìš° ì´ˆê¸°??        if df.empty or "Ticker" not in df.columns:
            return pd.DataFrame(columns=["Group", "Category", "Ticker", "Purchase Date", "Purchase Price", "Quantity", "Currency"])
            
        # ê¸°ì¡´ ë§ˆì´ê·¸ë ˆ?´ì…˜ ë¡œì§
        if "Category" not in df.columns:
            df.insert(0, "Category", "ë¯¸êµ­?œì¥1")
            
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
            df.insert(0, "Group", "ê¸°ë³¸ê³„ì¢Œ")
            save_assets(df)
            
        # ArrowTypeError ë°©ì?ë¥??„í•œ ?°ì´???€???•ë¦¬
        df["Group"] = df["Group"].fillna("ê¸°ë³¸ê³„ì¢Œ").astype(str)
        df["Category"] = df["Category"].fillna("ë¯¸ë¶„ë¥?).astype(str)
        df["Ticker"] = df["Ticker"].fillna("").astype(str).str.strip()
        df["Purchase Date"] = df["Purchase Date"].fillna("").astype(str)
        df["Currency"] = df["Currency"].fillna("USD").astype(str)
        df["Purchase Price"] = pd.to_numeric(df["Purchase Price"], errors='coerce').fillna(0.0)
        df["Quantity"] = pd.to_numeric(df["Quantity"], errors='coerce').fillna(0.0)
            
        return df
    except Exception as e:
        print(f"Error loading assets from sheets: {e}")
        return pd.DataFrame(columns=["Group", "Category", "Ticker", "Purchase Date", "Purchase Price", "Quantity", "Currency"])

# ?°ì´???€??def save_assets(df):
    try:
        conn = get_gsheets_connection()
        conn.update(worksheet="Assets", data=df)
        load_assets.clear() # ?€????ì¦‰ì‹œ ë°˜ì˜???„í•´ ìºì‹œ ?? œ
    except Exception as e:
        print(f"Error saving assets to sheets: {e}")
        st.error(f"êµ¬ê? ?œíŠ¸ ?€???¤íŒ¨: {e}")

@st.cache_data(ttl=60)
def get_targets_raw():
    try:
        conn = get_gsheets_connection()
        # ìºì‹±?€ st.cache_data??ë§¡ê¸°ê³? conn.read ?ì²´ ìºì‹œ???„ê±°??ë¬´ì‹œ
        df = conn.read(worksheet="Targets", ttl="0m")
        if df.empty or "Category" not in df.columns:
            raise ValueError("Empty or invalid targets sheet")
        return df
    except Exception as e:
        print(f"Error loading targets from sheets: {e}")
        return pd.DataFrame([
            {"Category": "ë¯¸êµ­?œì¥1", "Target (%)": 20.0},
            {"Category": "ë¯¸êµ­?œì¥2", "Target (%)": 20.0},
            {"Category": "ë¯¸êµ­ ??, "Target (%)": 30.0},
            {"Category": "ì±„ê¶Œ", "Target (%)": 15.0},
            {"Category": "ê¸?, "Target (%)": 15.0}
        ])

def load_target_weights():
    df = get_targets_raw()
    return df[df["Category"] != "_AVAILABLE_CASH_"].copy()

def get_available_cash():
    df = get_targets_raw()
    cash_row = df[df["Category"] == "_AVAILABLE_CASH_"]
    if not cash_row.empty:
        return float(cash_row["Target (%)"].iloc[0])
    return 0.0

def save_available_cash(cash_amount):
    df = get_targets_raw()
    if "_AVAILABLE_CASH_" in df["Category"].values:
        df.loc[df["Category"] == "_AVAILABLE_CASH_", "Target (%)"] = float(cash_amount)
    else:
        df = pd.concat([df, pd.DataFrame([{"Category": "_AVAILABLE_CASH_", "Target (%)": float(cash_amount)}])], ignore_index=True)
    save_target_weights(df)

def save_target_weights(df):
    try:
        conn = get_gsheets_connection()
        conn.update(worksheet="Targets", data=df)
        # êµ¬ê? ?œíŠ¸ ?…ë°?´íŠ¸ ?±ê³µ ?? ?¤ìŒ ì¡°íšŒ ??ì¦‰ì‹œ ë°˜ì˜?˜ë„ë¡?ìºì‹œ ?? œ
        get_targets_raw.clear() 
    except Exception as e:
        print(f"Error saving targets to sheets: {e}")
        st.error(f"êµ¬ê? ?œíŠ¸ ?€???¤íŒ¨: {e}")

import requests

def fetch_yahoo(ticker, start_date_str, end_date_str):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5y"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            result = data.get('chart', {}).get('result', [])
            if result:
                timestamps = result[0].get('timestamp', [])
                closes = result[0].get('indicators', {}).get('quote', [{}])[0].get('close', [])
                if timestamps and closes:
                    from zoneinfo import ZoneInfo
                    from datetime import timezone
                    kst = ZoneInfo("Asia/Seoul")
                    dates = [datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(kst).replace(tzinfo=None) for ts in timestamps]
                    df = pd.DataFrame({'Close': closes}, index=dates)
                    df = df.dropna()
                    df = df[df.index >= pd.to_datetime(start_date_str)]
                    df = df[df.index <= pd.to_datetime(end_date_str) + pd.Timedelta(days=1)]
                    return df
    except Exception as e:
        print(f"Yahoo fetch error for {ticker}: {e}")
    return pd.DataFrame()

# ?˜ìœ¨ ë°??œì„¸ ê°€?¸ì˜¤ê¸?(ìºì‹± ?ìš©)
@st.cache_data(ttl=3600)
def get_current_data(ticker):
    try:
        end_date = get_kst_today()
        start_date = end_date - timedelta(days=5)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        if ticker == "USD/KRW":
            df = fetch_yahoo("KRW=X", start_str, end_str)
            if not df.empty:
                return df['Close'].iloc[-1]
        elif ticker.isalpha():
            df = fetch_yahoo(ticker, start_str, end_str)
            if not df.empty:
                return df['Close'].iloc[-1]
            
        data = fdr.DataReader(ticker, start_str, end_str)
        if not data.empty:
            return data['Close'].iloc[-1]
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
    return None

@st.cache_data(ttl=86400)
def get_historical_exchange_rate(date_str):
    try:
        # ?¤ì–‘??? ì§œ ?•ì‹(2024.01.01 ?? ì§€?ì„ ?„í•´ pandas to_datetime ?¬ìš©
        start_date = pd.to_datetime(date_str)
        end_date = start_date + timedelta(days=5) # ì£¼ë§ ?€ë¹?ëª????¬ìœ ë¶?        df = fetch_yahoo("KRW=X", start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        if not df.empty:
            return df['Close'].iloc[0]
        
        # ?´ë°±
        data = fdr.DataReader("USD/KRW", start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        if not data.empty:
            return data['Close'].iloc[0]
    except Exception as e:
        print(f"Error fetching historical exchange rate for '{date_str}': {e}")
    return None

@st.cache_data(ttl=3600)
def fetch_history_data(tickers):
    end_dt = get_kst_today()
    start_dt = end_dt - timedelta(days=5*365)
    start_date_str = start_dt.strftime("%Y-%m-%d")
    end_date_str = end_dt.strftime("%Y-%m-%d")
    
    hist_dict = {}
    for t in tickers:
        try:
            if t == "USD/KRW":
                df = fetch_yahoo("KRW=X", start_date_str, end_date_str)
                if not df.empty:
                    hist_dict[t] = df['Close']
                    continue
            elif t.isalpha():
                df = fetch_yahoo(t, start_date_str, end_date_str)
                if not df.empty:
                    hist_dict[t] = df['Close']
                    continue
            
            df = fdr.DataReader(t, start_date_str)
            if not df.empty:
                hist_dict[t] = df['Close']
        except:
            pass
    
    if not hist_dict:
        return pd.DataFrame()
        
    hist_df = pd.DataFrame(hist_dict)
    hist_df = hist_df.ffill().bfill() # ?„ë½???´ì¼ ?°ì´??ì±„ìš°ê¸?    return hist_df

def check_password():
    """Returns `True` if the user had the correct password."""
    # ë¹„ë?ë²ˆí˜¸ ?¤ì •?????˜ì–´ ?ˆë‹¤ë©??¼ë‹¨ ?µê³¼?œí‚µ?ˆë‹¤.
    if "app_password" not in st.secrets:
        return True

    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # ë³´ì•ˆ???„í•´ ?¸ì…˜?ì„œ ë¹„ë?ë²ˆí˜¸ ?? œ
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("?”’ Security")
        st.text_input("?€?œë³´???‘ì† ë¹„ë?ë²ˆí˜¸ë¥??…ë ¥?˜ì„¸??, type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.title("?”’ Security")
        st.text_input("?€?œë³´???‘ì† ë¹„ë?ë²ˆí˜¸ë¥??…ë ¥?˜ì„¸??, type="password", on_change=password_entered, key="password")
        st.error("?˜• ë¹„ë?ë²ˆí˜¸ê°€ ?€?¸ìŠµ?ˆë‹¤. ?¤ì‹œ ?œë„?´ì£¼?¸ìš”.")
        return False
    else:
        return True

def main():
    if not check_password():
        st.stop() # ë¹„ë?ë²ˆí˜¸ê°€ ?€ë¦¬ë©´ ?¬ê¸°?????¤í–‰??ë©ˆì¶¤

    st.title("?“ˆ Personal Wealth Dashboard")

    hide_amounts = st.toggle("?? ê¸ˆì•¡ ?¨ê¸°ê¸?(ê³µê³µ?¥ì†Œ ëª¨ë“œ)", value=False)
    st.markdown("---")

    # 2. ?„ì¬ ?˜ìœ¨ ê°€?¸ì˜¤ê¸?    current_krw_rate = get_current_data("USD/KRW")
    if current_krw_rate is None:
        st.error("?„ì¬ ?˜ìœ¨ ?•ë³´ë¥?ê°€?¸ì˜¤ì§€ ëª»í–ˆ?µë‹ˆ?? ?„ì‹œë¡?1350?ì„ ?ìš©?©ë‹ˆ??")
        current_krw_rate = 1350.0 # fallback

    st.write(f"**?„ì¬ ?¬ëŸ¬/???˜ìœ¨:** ??current_krw_rate:,.2f}")

    # 3. ?ì‚° ëª©ë¡ ë°?ê°€ì¹?ê³„ì‚°
    df = load_assets()
    
    if not df.empty:
        # ?°ì´?°í”„?ˆì„ ë³µì‚¬ë³¸ìœ¼ë¡??‘ì—…
        display_df = df.copy()
        
        # ê³„ì‚°???„í•œ ë¦¬ìŠ¤??ì¤€ë¹?        hist_rates = []
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

        # ê°??‰ë§ˆ???œì„¸ ë°??˜ìœ¨ ì¡°íšŒ
        for index, row in display_df.iterrows():
            # ê³¼ê±° ?˜ìœ¨
            h_rate = get_historical_exchange_rate(row["Purchase Date"])
            if h_rate is None:
                h_rate = current_krw_rate # fallback
            hist_rates.append(h_rate)
            
            ticker = row["Ticker"]
            # Currency ì»¬ëŸ¼??ê³µë°±?´ë‚˜ ?Œë¬¸?ê? ?ì—¬?ˆì–´???ˆì „?˜ê²Œ USDë¡??¸ì‹?˜ë„ë¡?ê°œì„ 
            currency_val = str(row.get("Currency", "USD")).strip().upper()
            is_foreign = (currency_val == "USD")
            
            # êµ¬ì… ê¸ˆì•¡ ê³„ì‚°
            input_price = row["Purchase Price"]
            if is_foreign:
                total_purch_usd = input_price * row["Quantity"]
                purch_krw_val = total_purch_usd * h_rate
            else:
                purch_krw_val = input_price * row["Quantity"]
                total_purch_usd = purch_krw_val / h_rate if h_rate > 0 else 0
            
            purch_krw.append(purch_krw_val)
            tot_purch_usds.append(total_purch_usd)
            
            # ?„ì¬ ?œì„¸
            c_price = get_current_data(ticker)
            if c_price is None:
                c_price = input_price # fallback if API fails
            curr_prices.append(c_price)
            
            # ?„ì¬ ê°€ì¹?ê³„ì‚°
            if is_foreign:
                c_usd_val = c_price * row["Quantity"]
                c_krw_val = c_usd_val * current_krw_rate
            else:
                c_krw_val = c_price * row["Quantity"]
                c_usd_val = c_krw_val / current_krw_rate if current_krw_rate > 0 else 0
                
            curr_usd_vals.append(c_usd_val)
            curr_krw_vals.append(c_krw_val)
            
            # ?˜ìµë¥?ê³„ì‚°
            p_usd = c_usd_val - total_purch_usd
            p_krw = c_krw_val - purch_krw_val
            p_pct = (p_krw / purch_krw_val) * 100 if purch_krw_val > 0 else 0
            
            # ?˜ì°¨?µê³¼ ?ì‚°?ìµ ë¶„ë¦¬
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
            
        # ?°ì´?°í”„?ˆì„???Œìƒ ì»¬ëŸ¼ ì¶”ê?
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

        # ?´ë? ?ë³„??ë°?ì²´í¬ë°•ìŠ¤ ì»¬ëŸ¼ ì¶”ê?
        display_df.insert(0, "_ID", range(len(display_df)))
        display_df.insert(1, "ê·¸ë˜???œì‹œ", False)

        def format_money(val, is_profit=False, is_pct=False):
            if pd.isna(val): return ""
            if is_profit:
                if val > 0.01: return f"?”´ +{val:,.2f}%" if is_pct else f"?”´ +{val:,.0f}"
                elif val < -0.01: return f"?”µ {val:,.2f}%" if is_pct else f"?”µ {val:,.0f}"
                else: return f"{val:,.2f}%" if is_pct else f"{val:,.0f}"
            else:
                return f"{val:,.2f}%" if is_pct else f"{val:,.0f}"

        editor_df = display_df.copy()
        
        # ?©ê³„ ??ê³„ì‚° ë°?ì¶”ê?
        total_purch_krw_sum = editor_df["Total Purchase (KRW)"].sum()
        total_curr_krw_sum = editor_df["Current Value (KRW)"].sum()
        total_asset_profit = editor_df["Asset Profit (KRW)"].sum()
        total_fx_profit = editor_df["FX Profit (KRW)"].sum()
        total_profit = editor_df["Profit/Loss (KRW)"].sum()
        total_pct = (total_profit / total_purch_krw_sum) * 100 if total_purch_krw_sum > 0 else 0
        
        total_row = pd.DataFrame([{
            "_ID": -1,
            "ê·¸ë˜???œì‹œ": False,
            "Group": "?©ê³„",
            "Category": "-",
            "Ticker": "-",
            "Purchase Date": "-",
            "Purchase Price": 0.0,
            "Quantity": 0.0,
            "Currency": "-",
            "Historical Rate (KRW)": 0.0,
            "Total Purchase (USD)": editor_df["Total Purchase (USD)"].sum(),
            "Total Purchase (KRW)": total_purch_krw_sum,
            "Current Price (USD)": 0.0,
            "Current Value (USD)": editor_df["Current Value (USD)"].sum(),
            "Current Value (KRW)": total_curr_krw_sum,
            "Asset Profit (KRW)": total_asset_profit,
            "FX Profit (KRW)": total_fx_profit,
            "Profit/Loss (KRW)": total_profit,
            "Profit/Loss (%)": total_pct
        }])
        editor_df = pd.concat([editor_df, total_row], ignore_index=True)
        
        def format_money(val, is_profit=False, is_pct=False):
            if pd.isna(val): return ""
            if is_profit:
                if val > 0.01: return f"?”´ +{val:,.2f}%" if is_pct else f"?”´ +{val:,.0f}"
                elif val < -0.01: return f"?”µ {val:,.2f}%" if is_pct else f"?”µ {val:,.0f}"
                else: return f"{val:,.2f}%" if is_pct else f"{val:,.0f}"
            else:
                return f"{val:,.2f}%" if is_pct else f"{val:,.0f}"

        # ë¬¸ì?´ë¡œ ë³€?˜í•˜??ì½¤ë§ˆ?€ ?´ëª¨?°ì½˜ ?‰ìƒ???ìš© (ê¸€?ìƒ‰ ë³€ê²½ì´ ë¶ˆê??˜ì—¬ ?´ëª¨?°ì½˜?¼ë¡œ ?€ì²?
        editor_df["Historical Rate (KRW)"] = editor_df["Historical Rate (KRW)"].apply(lambda x: f"??x:,.2f}" if pd.notnull(x) else "")
        editor_df["Total Purchase (USD)"] = editor_df["Total Purchase (USD)"].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "")
        editor_df["Total Purchase (KRW)"] = editor_df["Total Purchase (KRW)"].apply(lambda x: f"??x:,.0f}" if pd.notnull(x) else "")
        
        formatted_curr_prices = []
        for _, r in editor_df.iterrows():
            if r.get("Currency", "USD") == "USD":
                formatted_curr_prices.append(f"${r['Current Price (USD)']:,.2f}")
            else:
                formatted_curr_prices.append(f"??r['Current Price (USD)']:,.0f}")
        editor_df["Current Price (USD)"] = formatted_curr_prices
        
        editor_df["Current Value (USD)"] = editor_df["Current Value (USD)"].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "")
        editor_df["Current Value (KRW)"] = editor_df["Current Value (KRW)"].apply(lambda x: f"??x:,.0f}" if pd.notnull(x) else "")
        
        # ?˜ìµ/?ì‹¤ ì»¬ëŸ¼??(?‰ìƒ ?´ëª¨?°ì½˜ ?ìš©)
        editor_df["Asset Profit (KRW)"] = editor_df["Asset Profit (KRW)"].apply(lambda x: format_money(x, True))
        editor_df["FX Profit (KRW)"] = editor_df["FX Profit (KRW)"].apply(lambda x: format_money(x, True))
        editor_df["Profit/Loss (KRW)"] = editor_df["Profit/Loss (KRW)"].apply(lambda x: format_money(x, True))
        editor_df["Profit/Loss (%)"] = editor_df["Profit/Loss (%)"].apply(lambda x: format_money(x, True, True))
        
        # ?°ì´???ë””???¸ë±??ë²„ê·¸ ë°©ì? (?™ì¼ ?°ì»¤ê°€ ?¬ëŸ¬ ê°œì¼ ??ê¼¬ì´???„ìƒ)
        # ?°ì»¤ ?€??ê³ ìœ ê°?_ID)???¸ë±?¤ë¡œ ?¬ìš©?˜ë˜, ?”ë©´?ì„œ???¨ê? ì²˜ë¦¬
        editor_df.set_index("_ID", inplace=True)

        target_weights_df = load_target_weights()
        category_options = target_weights_df["Category"].tolist() + ["ë¯¸ë¶„ë¥?]

        col_config = {
            "ê·¸ë˜???œì‹œ": st.column_config.CheckboxColumn("?“Š ê·¸ë˜???œì‹œ", default=False),
            "Group": st.column_config.TextColumn("ì¦ê¶Œ??ê³„ì¢Œ (?€ë¶„ë¥˜)"),
            "Category": st.column_config.SelectboxColumn("?ì‚° ë¶„ë¥˜ (?Œë¶„ë¥?", options=category_options),
            "Ticker": st.column_config.TextColumn("?°ì»¤"),
            "Purchase Date": st.column_config.TextColumn("ë§¤ìˆ˜ ?¼ì"),
            "Purchase Price": st.column_config.NumberColumn("ë§¤ìˆ˜ ?¨ê? (?˜ì •ê°€??"), 
            "Quantity": st.column_config.NumberColumn("?˜ëŸ‰ (?˜ì •ê°€??"),
            "Currency": st.column_config.SelectboxColumn("?µí™”", options=["USD", "KRW"]),
            
            # ?Œìƒ ì»¬ëŸ¼?¤ì? ?´ì œ ?¤ì‹œ ë¬¸ì??TextColumn)????            "Historical Rate (KRW)": st.column_config.TextColumn("ê³¼ê±° ?˜ìœ¨", disabled=True),
            "Total Purchase (USD)": st.column_config.TextColumn("ì´?ë§¤ìˆ˜(USD)", disabled=True),
            "Total Purchase (KRW)": st.column_config.TextColumn("ì´?ë§¤ìˆ˜(KRW)", disabled=True),
            "Current Price (USD)": st.column_config.TextColumn("?„ì¬ ?œì„¸", disabled=True),
            "Current Value (USD)": st.column_config.TextColumn("?„ì¬ ê°€ì¹?USD)", disabled=True),
            "Current Value (KRW)": st.column_config.TextColumn("?„ì¬ ê°€ì¹?KRW)", disabled=True),
            "Asset Profit (KRW)": st.column_config.TextColumn("?ì‚° ?ìµ(KRW)", disabled=True),
            "FX Profit (KRW)": st.column_config.TextColumn("?˜ì°¨??KRW)", disabled=True),
            "Profit/Loss (KRW)": st.column_config.TextColumn("?˜ìµ/?ì‹¤(KRW)", disabled=True),
            "Profit/Loss (%)": st.column_config.TextColumn("?˜ìµë¥?%)", disabled=True),
        }
        
        st.markdown("?’¡ **Tip:** ???ˆì˜ ê°’ì„ ?”ë¸”?´ë¦­?˜ì—¬ ?ìœ ë¡?²Œ ?˜ì •?˜ê±°?? ê°€???¼ìª½ ?¸ë±?¤ë? ?´ë¦­?˜ê³  `Del` ?¤ë? ?ŒëŸ¬ ?? œ?????ˆìŠµ?ˆë‹¤. ?˜ì •???„ë£Œ?˜ë©´ ???„ë˜??**?€??* ë²„íŠ¼???„ë¥´?¸ìš”. <br/>ì¢Œì¸¡ **?“Š ê·¸ë˜???œì‹œ** ì²´í¬ë°•ìŠ¤ë¥?ì¼œì‹œë©??´ë‹¹ ?ì‚°ë§?ì°¨íŠ¸???˜í??©ë‹ˆ??", unsafe_allow_html=True)
        
        base_cols = ["Group", "Category", "Ticker", "Purchase Date", "Purchase Price", "Quantity", "Currency"]
        edited_display = st.data_editor(
            editor_df,
            column_config=col_config,
            use_container_width=True,
            num_rows="dynamic",
            height=600,
            hide_index=True,
            key="main_table_editor"
        )
        
        if st.button("?˜ì •/?? œ ë³€ê²½ì‚¬???€??):
            edited_base = edited_display.reset_index()[base_cols]
            # ?©ê³„ ?‰ì? ?€?¥í•˜ì§€ ?ŠìŒ
            edited_base = edited_base[edited_base["Group"] != "?©ê³„"]
            save_assets(edited_base)
            st.success("?ì‚° ?•ë³´ê°€ ?±ê³µ?ìœ¼ë¡??…ë°?´íŠ¸ ?˜ì—ˆ?µë‹ˆ??")
            st.rerun()

        st.markdown("---")
        # ?¼ê´„ ? íƒ ?µì…˜ ì¶”ê? (ì°¨íŠ¸?€ ?”ì•½ ë°”ë¡œ ?„ë¡œ ?´ë™)
        col_sel1, col_sel2 = st.columns(2)
        with col_sel1:
            sel_groups = st.multiselect("?“‚ ?€ë¶„ë¥˜(ì¦ê¶Œ??ê³„ì¢Œ) ?¼ê´„ ? íƒ", display_df["Group"].unique(), help="? íƒ???€ë¶„ë¥˜???í•œ ëª¨ë“  ?ì‚°???„ë˜ ?”ì•½ê³?ê·¸ë˜?„ì— ë°˜ì˜?©ë‹ˆ??")
        with col_sel2:
            sel_categories = st.multiselect("?·ï¸??Œë¶„ë¥??ì‚° ?±ê²©) ?¼ê´„ ? íƒ", display_df["Category"].unique(), help="? íƒ???Œë¶„ë¥˜ì— ?í•œ ëª¨ë“  ?ì‚°???„ë˜ ?”ì•½ê³?ê·¸ë˜?„ì— ë°˜ì˜?©ë‹ˆ??")

        edited_display_reset = edited_display.reset_index()
        # ê·¸ë˜???”ì•½ ê³„ì‚° ??'?©ê³„' ?‰ì? ?œì™¸
        valid_display = edited_display_reset[edited_display_reset["_ID"] != -1]
        
        selected_ids = valid_display.loc[valid_display["ê·¸ë˜???œì‹œ"] == True, "_ID"].tolist()
        
        # ?¼ê´„ ? íƒ??ê·¸ë£¹?´ë‚˜ ì¹´í…Œê³ ë¦¬ê°€ ?ˆë‹¤ë©?? íƒ ëª©ë¡??ì¶”ê?
        if sel_groups:
            group_ids = valid_display.loc[valid_display["Group"].isin(sel_groups), "_ID"].tolist()
            selected_ids.extend(group_ids)
        if sel_categories:
            cat_ids = valid_display.loc[valid_display["Category"].isin(sel_categories), "_ID"].tolist()
            selected_ids.extend(cat_ids)
            
        selected_ids = list(set(selected_ids)) # ì¤‘ë³µ ?œê±°

        # --- ?ì‚° ì´ì•¡ ë³€??ê·¸ë˜??(??ë°”ë¡œ ?„ë˜ ë°°ì¹˜) ---
        has_selection = len(selected_ids) > 0
        target_df = valid_display[valid_display["_ID"].isin(selected_ids)] if has_selection else valid_display
        
        if has_selection:
            sel_tickers = target_df["Ticker"].tolist()
            if len(sel_tickers) <= 3:
                tickers_str = ", ".join(sel_tickers)
            else:
                tickers_str = f"{sel_tickers[0]} ??{len(sel_tickers)-1}ì¢…ëª©"
            st.subheader(f"?“ˆ {tickers_str} ?©ì‚° ê°€ì¹?ë³€??ì¶”ì´")
            st.caption(f"? íƒ?˜ì‹  ?ì‚°?¤ì˜ ?í™” ê°€ì¹?ë³€?™ì…?ˆë‹¤.")
        else:
            st.subheader("?“ˆ ?„ì¬ ?„ì²´ ?¬íŠ¸?´ë¦¬??ê°€ì¹?ë³€??ì¶”ì´")
            st.caption("?„ì¬ ë³´ìœ ì¤‘ì¸ ?„ì²´ ?ì‚° ?˜ëŸ‰??ê³¼ê±°?ë„ ?™ì¼?˜ê²Œ ë³´ìœ ?ˆë‹¤ê³?ê°€?•í–ˆ???Œì˜ ?í™” ê°€ì¹?ë³€?™ì…?ˆë‹¤.")
        
        unique_tickers = valid_display["Ticker"].unique().tolist()
        unique_tickers.sort() # ?•ë ¬???µí•´ st.cache_dataê°€ ?œì„œ ë³€ê²½ì„ ?ˆë¡œ???”ì²­?¼ë¡œ ì°©ê°?˜ì—¬ ìºì‹œë¥?ê¹¨ëŠ” ?„ìƒ(ë¨¹í†µ) ë°©ì?
        if "USD/KRW" not in unique_tickers:
            unique_tickers.append("USD/KRW")
            
        hist_data = fetch_history_data(tuple(unique_tickers))
        
        if not hist_data.empty and "USD/KRW" in hist_data.columns:
            total_series = pd.Series(0.0, index=hist_data.index)
            
            # ? íƒ???ì‚°???ˆìœ¼ë©??´ë‹¹ ?ì‚°ë§? ?†ìœ¼ë©??„ì²´ ?¬ìš©
            
            for _, r in target_df.iterrows():
                ticker = r["Ticker"]
                qty = r["Quantity"]
                currency = str(r.get("Currency", "USD")).strip().upper()
                if ticker in hist_data.columns:
                    if currency == "USD":
                        total_series += hist_data[ticker] * qty * hist_data["USD/KRW"]
                    else:
                        total_series += hist_data[ticker] * qty
            
            period = st.radio(
                "ê¸°ê°„ ? íƒ",
                ["1D", "1W", "1M", "YTD", "6M", "1Y", "3Y", "5Y"],
                horizontal=True,
                index=5 # ê¸°ë³¸ê°?1Y
            )

            today = get_kst_today()
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
                    st.metric("? íƒ??ê¸°ê°„ ???ì‚° ë³€??, "********", f"{pct_change:+.2f}%")
                    if first_val > 0:
                        chart_df["Total Value (KRW)"] = (chart_df["Total Value (KRW)"] / first_val) * 100
                    fig2 = px.line(chart_df, x="Date", y="Total Value (KRW)", color_discrete_sequence=["#2ca02c"])
                    fig2.update_layout(xaxis_title="", yaxis_title="?ë? ê°€ì¹?(?œì‘??100)", margin=dict(t=10, b=10, l=10, r=10), hovermode="x unified")
                else:
                    st.metric("? íƒ??ê¸°ê°„ ???ì‚° ë³€??, f"??last_val:,.0f}", f"{diff:,.0f} ??({pct_change:+.2f}%)")
                    fig2 = px.line(chart_df, x="Date", y="Total Value (KRW)", color_discrete_sequence=["#2ca02c"])
                    fig2.update_layout(xaxis_title="", yaxis_title="?í™”(??", margin=dict(t=10, b=10, l=10, r=10), hovermode="x unified")
                    
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.warning("? íƒ??ê¸°ê°„???´ë‹¹?˜ëŠ” ?°ì´?°ê? ?†ìŠµ?ˆë‹¤.")

        # ?”ì•½ ?•ë³´ ?œì‹œ (? íƒ???ì‚° ê¸°ì?, ?†ìœ¼ë©??„ì²´)
        calc_df = display_df[display_df["_ID"].isin(selected_ids)] if (has_selection and len(selected_ids) < len(display_df)) else display_df
        
        total_purchase_krw = calc_df["Total Purchase (KRW)"].sum()
        total_current_krw = calc_df["Current Value (KRW)"].sum()
        total_current_usd = calc_df["Current Value (USD)"].sum()
        total_profit_krw = total_current_krw - total_purchase_krw
        total_profit_pct = (total_profit_krw / total_purchase_krw) * 100 if total_purchase_krw > 0 else 0
        total_asset_profit_krw = calc_df["Asset Profit (KRW)"].sum()
        total_fx_profit_krw = calc_df["FX Profit (KRW)"].sum()

        st.markdown("---")
        if has_selection and len(selected_ids) < len(display_df):
            st.subheader("?“Œ ? íƒ???ì‚° ?”ì•½")
        else:
            st.subheader("ì´??ì‚° ?”ì•½")
        
        def display_metric(label, value, is_pct=False, prefix="??):
            if hide_amounts:
                return "********"
            if is_pct:
                return f"{value:,.2f}%"
            if prefix == "$":
                return f"${value:,.2f}"
            return f"{prefix}{value:,.0f}"

        col1, col2, col3 = st.columns(3)
        col1.metric("ì´?ë§¤ìˆ˜ ê¸ˆì•¡ (?í™” ?˜ì‚°)", display_metric("ì´?ë§¤ìˆ˜ ê¸ˆì•¡ (?í™” ?˜ì‚°)", total_purchase_krw))
        col2.metric("?„ì¬ ì´??ì‚° (?í™”)", display_metric("?„ì¬ ì´??ì‚° (?í™”)", total_current_krw), display_metric("?˜ìµ", total_profit_krw, prefix="") if not hide_amounts else None)
        col3.metric("?„ì¬ ì´??ì‚° (?¬ëŸ¬)", display_metric("?„ì¬ ì´??ì‚° (?¬ëŸ¬)", total_current_usd, prefix="$"))
        
        st.write("")
        col4, col5, col6 = st.columns(3)
        col4.metric("ì´??˜ìµë¥?(?í™” ê¸°ì?)", display_metric("ì´??˜ìµë¥?(?í™” ê¸°ì?)", total_profit_pct, is_pct=True))
        col5.metric("ì´??ì‚° ?ìµ (?í™”)", display_metric("ì´??ì‚° ?ìµ (?í™”)", total_asset_profit_krw))
        col6.metric("ì´??˜ì°¨??(?í™”)", display_metric("ì´??˜ì°¨??(?í™”)", total_fx_profit_krw))

        # 1. ?ì‚° ë¶„ë¥˜(?Œë¶„ë¥?ë³?ë¹„ìœ¨ ë¶„ì„
        st.markdown("---")
        
        col_title, col_cash, col_cash_btn = st.columns([1.2, 0.8, 0.2])
        with col_title:
            st.subheader("?“Š ?ì‚° ?¬íŠ¸?´ë¦¬??ë¹„ì¤‘ (?Œë¶„ë¥?")
            
        saved_cash = get_available_cash()
        with col_cash:
            available_cash = st.number_input(
                "?’µ ì¶”ê? ?¬ì ê°€???¬ìœ  ?„ê¸ˆ (??", 
                min_value=0, value=int(saved_cash), step=1000000,
                help="?„ì§ ?ì‚°?¼ë¡œ ë§¤ìˆ˜?˜ì? ?Šì? ?„ê¸ˆ???…ë ¥?˜ë©´, ???„ê¸ˆ???¬í•¨??ì´ì•¡??ê¸°ì??¼ë¡œ ëª©í‘œ ë¹„ì¤‘??ë§ì¶”ê¸??„í•´ ?´ë–¤ ?ì‚°???¼ë§ˆ?????¬ì•¼ ?˜ëŠ”ì§€(ê³¼ë?ì¡?ê¸ˆì•¡) ?ë™ ê³„ì‚°??ì¤ë‹ˆ??"
            )
            if available_cash is None:
                available_cash = 0
                
        with col_cash_btn:
            st.write("<br>", unsafe_allow_html=True)
            if st.button("?€??, key="save_cash_btn"):
                save_available_cash(available_cash)
                st.rerun()
        
        target_weights_df = load_target_weights()
        target_categories = target_weights_df["Category"].tolist()
        
        # ëª©í‘œ ë¹„ì¤‘???•ì˜??ì¹´í…Œê³ ë¦¬???í•œ ?ì‚°ë§??„í„°ë§í•˜??ì´í•© ê³„ì‚°
        filtered_display_df = display_df[display_df["Category"].isin(target_categories)]
        current_invested_krw = filtered_display_df["Current Value (KRW)"].sum()
        
        # ?¬ìœ  ?„ê¸ˆ???¬í•¨???ˆë¡œ???„ì²´ ëª©í‘œ ê¸ˆì•¡
        target_total_krw = current_invested_krw + available_cash
        
        category_df = filtered_display_df.groupby("Category")["Current Value (KRW)"].sum().reset_index()
        # ?„ì¬ ë¹„ì¤‘?€ ?´ë? ?¬ì??ê¸ˆì•¡ë§Œì„ ê¸°ì??¼ë¡œ 100%ë¥?ë³´ì—¬ì¤ë‹ˆ??
        category_df["Ratio (%)"] = (category_df["Current Value (KRW)"] / current_invested_krw) * 100 if current_invested_krw > 0 else 0
        
        # ëª©í‘œ ë¹„ì¤‘ê³?ë¹„êµ?????ˆë„ë¡?ë³‘í•© (?•ì˜??ì¹´í…Œê³ ë¦¬ê°€ ëª¨ë‘ ?˜ì˜¤?„ë¡)
        category_df = pd.merge(target_weights_df, category_df, on="Category", how="left").fillna(0)
        
        col_chart, col_table = st.columns([1, 1.3])
        
        with col_chart:
            # ê°’ì´ 0ë³´ë‹¤ ??ì¹´í…Œê³ ë¦¬ë§?ì°¨íŠ¸???œì‹œ
            plot_df = category_df[category_df["Current Value (KRW)"] > 0]
            if not plot_df.empty:
                fig = px.pie(plot_df, values='Current Value (KRW)', names='Category', hole=0.4, 
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("?¬íŠ¸?´ë¦¬?¤ì— ?ì‚°???†ìŠµ?ˆë‹¤.")
            
        with col_table:
            st.write("<br>", unsafe_allow_html=True)
            
            # ê³¼ë?ì¡?ê³„ì‚° (?„ì²´ ?ì‚°???„ë‹Œ 'ëª©í‘œ???•ì˜???ì‚°?¤ì˜ ì´í•©' ê¸°ì?)
            table_df = category_df.copy()
            table_df["ëª©í‘œ ê¸ˆì•¡"] = (target_total_krw * table_df["Target (%)"] / 100)
            table_df["ê³¼ë?ì¡?ê¸ˆì•¡"] = table_df["Current Value (KRW)"] - table_df["ëª©í‘œ ê¸ˆì•¡"]
            table_df["ë¹„ì¤‘ ì°¨ì´"] = table_df["Ratio (%)"] - table_df["Target (%)"]
            
            # ì¶œë ¥???Œì´ë¸??ì„±
            display_table = table_df[["Category", "Target (%)", "Ratio (%)", "ë¹„ì¤‘ ì°¨ì´", "Current Value (KRW)", "ê³¼ë?ì¡?ê¸ˆì•¡"]].copy()
            display_table.columns = ["?ì‚° ë¶„ë¥˜", "ëª©í‘œ ë¹„ì¤‘ (%)", "?„ì¬ ë¹„ì¤‘ (%)", "ë¹„ì¤‘ ì°¨ì´ (%p)", "?„ì¬ ê¸ˆì•¡ (??", "ê³¼ë?ì¡?ê¸ˆì•¡ (??"]
            
            # ì´ê³„ ??ì¶”ê?
            total_row = pd.DataFrame([{
                "?ì‚° ë¶„ë¥˜": "ì´ê³„",
                "ëª©í‘œ ë¹„ì¤‘ (%)": display_table["ëª©í‘œ ë¹„ì¤‘ (%)"].sum(),
                "?„ì¬ ë¹„ì¤‘ (%)": display_table["?„ì¬ ë¹„ì¤‘ (%)"].sum(),
                "ë¹„ì¤‘ ì°¨ì´ (%p)": display_table["ë¹„ì¤‘ ì°¨ì´ (%p)"].sum(),
                "?„ì¬ ê¸ˆì•¡ (??": display_table["?„ì¬ ê¸ˆì•¡ (??"].sum(),
                "ê³¼ë?ì¡?ê¸ˆì•¡ (??": display_table["ê³¼ë?ì¡?ê¸ˆì•¡ (??"].sum()
            }])
            display_table = pd.concat([display_table, total_row], ignore_index=True)
            
            def style_category(df):
                styles = pd.DataFrame('', index=df.index, columns=df.columns)
                for col in df.columns:
                    if col in ["ë¹„ì¤‘ ì°¨ì´ (%p)", "ê³¼ë?ì¡?ê¸ˆì•¡ (??"]:
                        styles[col] = df.apply(lambda r: ('color: #ff4b4b; ' if r[col] < -0.01 else ('color: #0068c9; ' if r[col] > 0.01 else '')) + 'text-align: right;' + ('font-weight: bold; background-color: rgba(128,128,128,0.2);' if r["?ì‚° ë¶„ë¥˜"] == "ì´ê³„" else ''), axis=1)
                    elif col != "?ì‚° ë¶„ë¥˜":
                        styles[col] = df.apply(lambda r: 'text-align: right;' + ('font-weight: bold; background-color: rgba(128,128,128,0.2);' if r["?ì‚° ë¶„ë¥˜"] == "ì´ê³„" else ''), axis=1)
                    else:
                        styles[col] = df.apply(lambda r: 'font-weight: bold; background-color: rgba(128,128,128,0.2);' if r["?ì‚° ë¶„ë¥˜"] == "ì´ê³„" else '', axis=1)
                return styles
            
            styled_display = display_table.style.format({
                "ëª©í‘œ ë¹„ì¤‘ (%)": "{:.1f}",
                "?„ì¬ ë¹„ì¤‘ (%)": "{:.1f}",
                "ë¹„ì¤‘ ì°¨ì´ (%p)": "{:+.1f}",
                "?„ì¬ ê¸ˆì•¡ (??": "{:,.0f}",
                "ê³¼ë?ì¡?ê¸ˆì•¡ (??": "{:+,.0f}"
            }).apply(style_category, axis=None)
            
            st.dataframe(
                styled_display, 
                use_container_width=True, 
                hide_index=True, 
                height=int((len(display_table) + 1.5) * 38)
            )

        # 2. ê³„ì¢Œ/ì¦ê¶Œ???€ë¶„ë¥˜)ë³?ë¹„ìœ¨ ë¶„ì„
        st.markdown("---")
        st.subheader("?¢ ê³„ì¢Œ/ì¦ê¶Œ?¬ë³„ ë¹„ì¤‘ (?€ë¶„ë¥˜)")
        
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
            g_display.columns = ["ê³„ì¢Œ/ì¦ê¶Œ??(?€ë¶„ë¥˜)", "?„ì¬ ê¸ˆì•¡ (??", "?„ì¬ ë¹„ì¤‘ (%)"]
            g_display = g_display[["ê³„ì¢Œ/ì¦ê¶Œ??(?€ë¶„ë¥˜)", "?„ì¬ ë¹„ì¤‘ (%)", "?„ì¬ ê¸ˆì•¡ (??"]]
            
            # ì´ê³„ ??ì¶”ê?
            total_g_row = pd.DataFrame([{
                "ê³„ì¢Œ/ì¦ê¶Œ??(?€ë¶„ë¥˜)": "ì´ê³„",
                "?„ì¬ ë¹„ì¤‘ (%)": g_display["?„ì¬ ë¹„ì¤‘ (%)"].sum(),
                "?„ì¬ ê¸ˆì•¡ (??": g_display["?„ì¬ ê¸ˆì•¡ (??"].sum()
            }])
            g_display = pd.concat([g_display, total_g_row], ignore_index=True)
            
            def style_group(df):
                styles = pd.DataFrame('', index=df.index, columns=df.columns)
                for col in df.columns:
                    if col != "ê³„ì¢Œ/ì¦ê¶Œ??(?€ë¶„ë¥˜)":
                        styles[col] = df.apply(lambda r: 'text-align: right;' + ('font-weight: bold; background-color: rgba(128,128,128,0.2);' if r["ê³„ì¢Œ/ì¦ê¶Œ??(?€ë¶„ë¥˜)"] == "ì´ê³„" else ''), axis=1)
                    else:
                        styles[col] = df.apply(lambda r: 'font-weight: bold; background-color: rgba(128,128,128,0.2);' if r["ê³„ì¢Œ/ì¦ê¶Œ??(?€ë¶„ë¥˜)"] == "ì´ê³„" else '', axis=1)
                return styles
                
            styled_g = g_display.style.format({
                "?„ì¬ ë¹„ì¤‘ (%)": "{:.1f}",
                "?„ì¬ ê¸ˆì•¡ (??": "{:,.0f}"
            }).apply(style_group, axis=None)
            
            st.dataframe(
                styled_g, 
                use_container_width=True, 
                hide_index=True, 
                height=int((len(g_display) + 1.5) * 38)
            )

        # ?ì‚° ì´ì•¡ ë³€??ê·¸ë˜??



    else:
        st.info("?„ë˜ ?¼ì—???ì‚°??ì¶”ê??˜ê±°??êµ¬ê? ?œíŠ¸?ì„œ ?…ë ¥?´ì£¼?¸ìš”.")

    st.markdown("---")
    st.header("?ˆë¡œ???ì‚° ì¶”ê?")
    with st.form("add_asset_form"):
        target_weights_df = load_target_weights()
        category_options = target_weights_df["Category"].tolist() + ["ë¯¸ë¶„ë¥?]
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            group = st.text_input("ì¦ê¶Œ??ê³„ì¢Œ (?€ë¶„ë¥˜)", "ê¸°ë³¸ê³„ì¢Œ")
            category = st.selectbox("?ì‚° ë¶„ë¥˜ (?Œë¶„ë¥?", category_options)
            ticker_input = st.text_input("?°ì»¤ ?ëŠ” ë©”íŠ¸?¼ì´??ê³µì‹œ URL", "")
            purchase_date_str = st.text_input("êµ¬ë§¤ ?¼ì (YYYY-MM-DD)", get_kst_today().strftime("%Y-%m-%d"))
        with col_f2:
            purchase_price = st.number_input("êµ¬ì… ê¸ˆì•¡ (1ì£¼ë‹¹ ê°€ê²??ëŠ” ê¸°ì?ê°€)", min_value=0.0, format="%.2f")
            currency = st.radio("êµ¬ì… ?µí™”", ["USD (?¬ëŸ¬)", "KRW (?í™”)"], horizontal=True)
            quantity = st.number_input("?˜ëŸ‰", min_value=0.0, format="%.4f")
            
        submit_button = st.form_submit_button(label="ì¶”ê?")

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
                st.success(f"{ticker} ?ì‚°??ì¶”ê??˜ì—ˆ?µë‹ˆ??")
                st.rerun()
            else:
                st.error("ëª¨ë“  ??ª©???¬ë°”ë¥´ê²Œ ?…ë ¥?´ì£¼?¸ìš”. (? ì§œ??YYYY-MM-DD ?•ì‹)")

    st.markdown("---")
    with st.expander("?¯ ?ì‚° ë¶„ë¥˜ ë°?ëª©í‘œ ë¹„ì¤‘ ì»¤ìŠ¤?€ ?¤ì •", expanded=False):
        st.caption("?ˆë¡œ???ì‚° ë¶„ë¥˜ë¥?ì¶”ê??˜ê±°?? ëª©í‘œ ë¹„ì¤‘(%)???˜ì •?????ˆìŠµ?ˆë‹¤. ë³€ê²????„ë˜ '?€?? ë²„íŠ¼???„ë¥´?¸ìš”. (?œë? ?´ë¦­?´ì„œ ë°”ë¡œ ?˜ì •/ì¶”ê?/?? œ ê°€??")
        
        # ?¬ê¸°???¤ì‹œ ë¡œë“œ(?¹ì‹œ ëª¨ë? ?íƒœ ê¼¬ì„ ë°©ì?)
        current_targets_df = load_target_weights()
        edited_targets = st.data_editor(
            current_targets_df,
            num_rows="dynamic",
            use_container_width=True,
            key="target_weights_editor",
            column_config={
                "Category": st.column_config.TextColumn("?ì‚° ë¶„ë¥˜ (Category)", required=True),
                "Target (%)": st.column_config.NumberColumn("ëª©í‘œ ë¹„ì¤‘ (%)", min_value=0.0, max_value=100.0, required=True, format="%.1f")
            }
        )
        
        if st.button("ëª©í‘œ ë¹„ì¤‘ ?€??):
            if abs(edited_targets["Target (%)"].sum() - 100.0) < 0.1:
                cash_amount = get_available_cash()
                if cash_amount > 0:
                    edited_targets = pd.concat([edited_targets, pd.DataFrame([{"Category": "_AVAILABLE_CASH_", "Target (%)": cash_amount}])], ignore_index=True)
                save_target_weights(edited_targets)
                st.success("ëª©í‘œ ë¹„ì¤‘???€?¥ë˜?ˆìŠµ?ˆë‹¤!")
                st.rerun()
            else:
                st.error(f"ë¹„ì¤‘ ?©ê³„ê°€ 100%ê°€ ?„ë‹™?ˆë‹¤! (?„ì¬: {edited_targets['Target (%)'].sum():.1f}%)")

if __name__ == "__main__":
    main()

import streamlit as st
import pandas as pd
import utils
import os
import yfinance as yf

# Fix for "disk I/O error" / "unable to open database file"
# Redirect yfinance cache to a local folder in the workspace
cache_dir = os.path.join(os.getcwd(), "yf_cache")
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)
yf.set_tz_cache_location(cache_dir)
from consts import SET100_TICKERS, LONG_TERM_GROWTH, RISK_FREE_RATE, MARKET_RETURN
import concurrent.futures
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf

# Set Page Configuration
st.set_page_config(
    page_title="โปรแกรมคัดกรองหุ้น VI (Thai Value Investor)",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load Tickers
SET100_TICKERS = utils.load_tickers()

# --- SIDEBAR: VALUATION MODEL ---
st.sidebar.title("🇹🇭 Thai Value Investor")
st.sidebar.markdown("### 🎛️ โมเดลประเมินมูลค่า")
with st.sidebar.expander("ตั้งค่าสมมติฐาน (Assumption)", expanded=False):
    st_rf = st.number_input("อัตราผลตอบแทนพันธบัตร (Risk Free %)", value=RISK_FREE_RATE*100, step=0.1, format="%.2f") / 100
    st_rm = st.number_input("ผลตอบแทนตลาด (Market Return %)", value=MARKET_RETURN*100, step=0.1, format="%.2f") / 100
    st_g = st.number_input("การเติบโตระยะยาว (Terminal Growth %)", value=LONG_TERM_GROWTH*100, step=0.1, format="%.2f") / 100
    
    if st.button("รีเซ็ตค่าเริ่มต้น"):
        st.cache_data.clear() # Optional but good
        st.rerun()

st.sidebar.markdown("### 🔄 อัปเดตข้อมูล")
if st.sidebar.button("อัปเดตข้อมูลราคาและงบการเงิน"):
    with st.spinner("กำลังล้าง Cache และดึงข้อมูลใหม่..."):
        # Clear Streamlit Cache
        st.cache_data.clear()
        
        # Clear yfinance Cache (optional, but ensures fresh data from API)
        # Note: We already redirected cache to local folder, so we can clean it if needed
        # but st.cache_data.clear() is usually enough for the app logic.
        # If we want to force yfinance to re-download, we might need to rely on its internal expiration or clear the folder.
        # For now, clearing app cache is sufficient to trigger fetch_raw_market_data() again.
        
    st.success("อัปเดตข้อมูลเรียบร้อยแล้ว!")
    st.rerun()

# --- DATA FETCHING (Separated) ---
@st.cache_data(ttl=3600)
def fetch_raw_market_data():
    """
    Fetches raw data for all tickers. Cached for performance.
    """
    results = []
    
    # Progress bar setup
    progress_text = "กำลังดึงข้อมูลหุ้น... โปรดรอสักครู่"
    my_bar = st.progress(0, text=progress_text)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Create a dictionary to map futures to tickers
        future_to_ticker = {executor.submit(utils.get_stock_data, ticker): ticker for ticker in SET100_TICKERS}
        
        completed_count = 0
        total_count = len(SET100_TICKERS)
        
        for future in concurrent.futures.as_completed(future_to_ticker):
            data = future.result()
            if data:
                results.append(data)
            
            completed_count += 1
            if total_count > 0:
                my_bar.progress(completed_count / total_count, text=f"กำลังโหลด {future_to_ticker[future]} ({completed_count}/{total_count})")
            
    my_bar.empty()
    return results

def process_valuations(raw_data, rf, rm, g):
    """
    Calculates valuation on raw data with specific parameters.
    """
    results = []
    for item in raw_data:
        # Clone item to avoid modifying cached dict in place across reruns (shallow copy often enough but dict copy is safer)
        data_copy = item.copy()
        evaluated_data = utils.calculate_valuations(data_copy, risk_free_rate=rf, market_return=rm, long_term_growth=g)
        if evaluated_data:
            results.append(evaluated_data)
    return pd.DataFrame(results)

# Load Pipeline
raw_data_list = fetch_raw_market_data()
if not raw_data_list:
    st.error("Failed to fetch data.")
    st.stop()

df = process_valuations(raw_data_list, st_rf, st_rm, st_g)

if not df.empty:
    # --- GLOBAL DATA ENRICHMENT ---
    # Handle NaNs for scoring
    df['debtToEquity'] = df['debtToEquity'].fillna(999) 
    df['returnOnEquity'] = df['returnOnEquity'].fillna(0)
    df['profitMargins'] = df['profitMargins'].fillna(0)
    df['margin_of_safety'] = df['margin_of_safety'].fillna(-100)
    df['marketCap'] = df['marketCap'].fillna(0)
    df['revenueGrowth'] = df['revenueGrowth'].fillna(0)
    df['pegRatio'] = df['pegRatio'].fillna(999)
    df['currentRatio'] = df['currentRatio'].fillna(0)
    df['grossMargins'] = df['grossMargins'].fillna(0)
    df['freeCashflow'] = df['freeCashflow'].fillna(0)
    
    # NOTE: yfinance 'debtToEquity' is usually returned as a percentage (e.g., 150 means 1.5x).
    # We need to divide by 100 for display if we want 'x', but for scoring logic check raw value.
    # Let's fix the dataframe column for display purposes to be 'x' (ratio).
    df['debtToEquityRatio'] = df['debtToEquity'] / 100

    # 1. Base Score (6 Points)
    df['score_debt'] = df['debtToEquity'].apply(lambda x: 1 if x < 200 else 0) # < 200% = < 2.0x
    df['score_roe'] = df['returnOnEquity'].apply(lambda x: 1 if x > 0.15 else 0)
    df['score_npm'] = df['profitMargins'].apply(lambda x: 1 if x > 0.10 else 0)
    df['score_mos'] = df['margin_of_safety'].apply(lambda x: 1 if x > 0 else 0)
    df['score_size'] = df['marketCap'].apply(lambda x: 1 if x > 50_000_000_000 else 0) # > 50B THB
    df['score_growth'] = df['revenueGrowth'].apply(lambda x: 1 if x > 0.05 else 0) # > 5% Growth
    
    # 2. VI Score 2.0 (New 4 Points)
    # 7. Cash Flow Strength: Free Cash Flow > 0 (Real Cash Generation)
    df['score_fcf'] = df['freeCashflow'].apply(lambda x: 1 if x > 0 else 0)
    
    # 8. Valuation Growth (GARP): PEG < 1.5 (Not overpaying for growth)
    df['score_peg'] = df['pegRatio'].apply(lambda x: 1 if x > 0 and x < 1.5 else 0)
    
    # 9. Liquidity: Current Ratio > 1.5 (Can pay short-term debts)
    df['score_liquidity'] = df['currentRatio'].apply(lambda x: 1 if x > 1.5 else 0)
    
    # 10. Competitive Advantage: Gross Margin > 20% (Pricing Power)
    df['score_gm'] = df['grossMargins'].apply(lambda x: 1 if x > 0.20 else 0)

    # Total Scores
    df['Quality Score'] = (df['score_debt'] + df['score_roe'] + df['score_npm'] + 
                           df['score_mos'] + df['score_size'] + df['score_growth'])
                           
    df['VI Score'] = (df['Quality Score'] + 
                      df['score_fcf'] + df['score_peg'] + df['score_liquidity'] + df['score_gm'])


# --- SIDEBAR NAVIGATION ---
st.sidebar.title("เมนูหลัก")
page = st.sidebar.radio("ไปยังหน้า", [
    "แดชบอร์ดภาพรวม", 
    "วิเคราะห์หุ้นรายตัว", 
    "เปรียบเทียบคู่แข่ง", 
    "แนะนำพอร์ตการลงทุน", 
    "พอร์ตของฉัน (My Portfolio)", 
    "จำลองการออมหุ้น (DCA Backtester)",
    "ตั้งค่า"
])

if page == "แดชบอร์ดภาพรวม":
    st.title("📊 โปรแกรมคัดกรองหุ้นคุณค่า (VI)")
    st.markdown("พัฒนาตามหลักการลงทุนของ คุณกวี ชูกิจเกษม")
    
    # Dashboard uses 'df' loaded globally
    
    if not df.empty:
        # Key Metrics
        col1, col2, col3 = st.columns(3)
        undervalued_count = df[df['status'] == 'Undervalued'].shape[0]
        avg_mos = df['margin_of_safety'].mean()
        
        col1.metric("หุ้นที่วิเคราะห์", f"{len(df)}")
        col2.metric("หุ้นราคาถูกกว่ามูลค่า", f"{undervalued_count}")
        col3.metric("ส่วนเผื่อความปลอดภัยเฉลี่ย (MOS)", f"{avg_mos:.2f}%")
        
        # --- QUALITY SCORING (Enhanced Auto 10 Points) ---
        # 1. Low Debt (D/E < 200%)
        # 2. Strong ROE (> 15%)
        # 3. High NPM (> 10%)
        # 4. Undervalued (MOS > 0)
        # 5. Market Leader Proxy (Market Cap > 50 Billion THB)
        # 6. Growth Proxy (Revenue Growth > 0%)
        # 7. Cash Flow Strength (FCF > 0)
        # 8. Valuation Growth (PEG < 1.5)
        # 9. Liquidity (Current Ratio > 1.5)
        # 10. Competitive Advantage (Gross Margin > 20%)
        
        # Sidebar Filter
        st.sidebar.markdown("---")
        st.sidebar.subheader("🔍 ตัวกรองหุ้น (Screener)")
        st.sidebar.info("ℹ️ **ระบบคะแนนใหม่ (VI Score):** เต็ม **10 คะแนน** เพิ่มเกณฑ์ FCF, PEG, สภาพคล่อง, และ Gross Margin")
        
        # Two-step slider or separate? Let's use one slider for VI Score
        min_score = st.sidebar.slider("คะแนนคุณภาพขั้นต่ำ (เต็ม 10)", 0, 10, 6, help="กรองจาก 10 ปัจจัยคุณภาพ (เดิม 6 + ใหม่ 4)")
        
        # Add checkbox for "Cash Flow Positive Only"
        filter_fcf = st.sidebar.checkbox("เฉพาะที่มีกระแสเงินสดอิสระบวก (FCF > 0)", value=False)
        
        filtered_df = df[df['VI Score'] >= min_score].copy()
        
        if filter_fcf:
            filtered_df = filtered_df[filtered_df['freeCashflow'] > 0]

        # --- ADVANCED SCANNING (Magic Formula & F-Score) ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("🚀 วิเคราะห์เชิงลึก")
        
        # Initialize session state for advanced results if not exists
        if 'advanced_results' not in st.session_state:
            st.session_state['advanced_results'] = {}

        if st.sidebar.button("วิเคราะห์ Magic Formula & F-Score"):
            st.toast("กำลังเริ่มวิเคราะห์เชิงลึก... อาจใช้เวลาสักครู่", icon="⏳")
            
            # Filter stocks to analyze (only from the filtered list to save time)
            targets = filtered_df['symbol'].tolist()
            
            progress_bar = st.sidebar.progress(0)
            status_text = st.sidebar.empty()
            
            results_adv = []
            
            # Use ThreadPool but limit workers to avoid rate limit/database lock
            # Since we are fetching deep financials, 5 workers is safe enough with our cache patch
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_ticker = {executor.submit(utils.calculate_magic_formula_and_f_score, ticker): ticker for ticker in targets}
                
                completed = 0
                total = len(targets)
                
                for future in concurrent.futures.as_completed(future_to_ticker):
                    res = future.result()
                    if res:
                        results_adv.append(res)
                    
                    completed += 1
                    progress = completed / total
                    progress_bar.progress(progress)
                    status_text.text(f"วิเคราะห์ {completed}/{total}")
            
            progress_bar.empty()
            status_text.empty()
            
            # Save to session state
            st.session_state['advanced_results'] = {r['symbol']: r for r in results_adv}
            st.success(f"วิเคราะห์เสร็จสิ้น! พบข้อมูล {len(results_adv)} หุ้น")
            st.rerun()

        # Merge Advanced Results if available
        if st.session_state['advanced_results']:
            # Create DataFrame from session state
            adv_df = pd.DataFrame(st.session_state['advanced_results'].values())
            
            # Merge with filtered_df
            if not adv_df.empty:
                # Use left merge to keep filtered_df rows
                filtered_df = filtered_df.merge(adv_df, on='symbol', how='left')
                
                # Fill NaNs for display
                filtered_df['magic_roc'] = filtered_df['magic_roc'].fillna(0)
                filtered_df['magic_ey'] = filtered_df['magic_ey'].fillna(0)
                filtered_df['f_score'] = filtered_df['f_score'].fillna(-1) # -1 means N/A

        
        # --- TOP 10 SUPER STOCKS (Integrated) ---
        st.markdown("---")
        st.subheader("🏆 10 สุดยอดหุ้นแกร่ง (The Super Stocks)")
        st.markdown(f"""
        คัดเลือกจาก **ราคาถูก (MOS > 0)**, **คุณภาพดีเยี่ยม (VI Score > {min_score})**, **กระแสเงินสดแกร่ง**, และ **ความเสี่ยงต่ำ**
        """)
        
        # Calculate yield first (for filtering)
        df['dividendYield_calc'] = df['dividendRate'] / df['price']
        
        # 1. Base Filter (Using VI Score)
        # We relax dividend rule slightly for Growth/Quality focus if Score is high
        super_candidates = df[
            (df['status'] == 'Undervalued') & 
            (df['VI Score'] >= min_score)
        ].copy()
        
        # 2. Advanced Scoring (if available)
        if 'magic_roc' in filtered_df.columns:
            # Join advanced data to candidates if not already joined
            # Note: We added 'graham_num', 'fcf_yield', 'z_score', 'sgr' to utils.py
            
            adv_cols = ['symbol', 'magic_roc', 'magic_ey', 'f_score', 'graham_num', 'fcf_yield', 'z_score', 'sgr']
            # Check if columns exist in filtered_df (in case user hasn't re-run analysis yet)
            adv_cols = [c for c in adv_cols if c in filtered_df.columns or c == 'symbol']
            
            if 'magic_roc' not in super_candidates.columns:
                 super_candidates = super_candidates.merge(filtered_df[adv_cols], on='symbol', how='left')
            
            # Fill N/A for those without deep scan
            super_candidates['magic_roc'] = super_candidates['magic_roc'].fillna(0)
            super_candidates['magic_ey'] = super_candidates['magic_ey'].fillna(0)
            super_candidates['f_score'] = super_candidates['f_score'].fillna(0)
            super_candidates['graham_num'] = super_candidates['graham_num'].fillna(0)
            super_candidates['fcf_yield'] = super_candidates['fcf_yield'].fillna(0)
            super_candidates['z_score'] = super_candidates['z_score'].fillna(0)
            super_candidates['sgr'] = super_candidates['sgr'].fillna(0)

            # Calculate Composite Score (Max 100)
            # MOS (30%) + Dividend (15%) + ROE (15%) + F-Score (20%) + Magic Rank (20%)
            
            # Rank Magic (Lower is better) -> Invert for scoring
            super_candidates['rank_roc'] = super_candidates['magic_roc'].rank(ascending=False)
            super_candidates['rank_ey'] = super_candidates['magic_ey'].rank(ascending=False)
            super_candidates['magic_rank_score'] = 100 - (super_candidates['rank_roc'] + super_candidates['rank_ey']) # Rough inversion
            
            # Normalize scores to 0-1 range for weighting
            def normalize(series):
                return (series - series.min()) / (series.max() - series.min()) if (series.max() - series.min()) > 0 else 0

            norm_mos = normalize(super_candidates['margin_of_safety'])
            norm_div = normalize(super_candidates['dividendYield_calc'])
            norm_roe = normalize(super_candidates['returnOnEquity'])
            norm_f = super_candidates['f_score'] / 9.0 # F-score is 0-9
            norm_magic = normalize(super_candidates['magic_rank_score'])
            norm_fcf = normalize(super_candidates['fcf_yield'])
            norm_z = normalize(super_candidates['z_score'])
            norm_sgr = normalize(super_candidates['sgr'])
            norm_viscore = normalize(super_candidates['VI Score']) # Add VI Score

            # Adjusted weighting for FCF, Z-Score, SGR
            super_candidates['Super_Score'] = (
                (norm_mos * 0.15) + 
                (norm_div * 0.05) + 
                (norm_roe * 0.10) + 
                (norm_f * 0.10) + 
                (norm_magic * 0.10) +
                (norm_fcf * 0.15) +
                (norm_z * 0.10) +
                (norm_sgr * 0.05) +
                (norm_viscore * 0.20) # High weight on VI Score
            ) * 100
            
            # Sort by Super Score
            top_picks = super_candidates.sort_values(by='Super_Score', ascending=False).head(10)
        
        else:
            # Fallback to original sorting if no advanced data yet
            st.info("💡 **Tips:** กดปุ่ม 'วิเคราะห์ Magic Formula & F-Score' ด้านซ้าย เพื่อเพิ่มความแม่นยำในการจัดอันดับ")
            # Sort by VI Score then MOS
            top_picks = super_candidates.sort_values(by=['VI Score', 'margin_of_safety'], ascending=[False, False]).head(10)
        
        
        if not top_picks.empty:
            # Calculate additional ratios for Super Stocks if missing
            top_picks['P/E'] = top_picks.apply(lambda row: row['price'] / row['trailingEps'] if row['trailingEps'] > 0 else 0, axis=1)
            top_picks['P/BV'] = top_picks.apply(lambda row: row['price'] / row['bookValue'] if row['bookValue'] > 0 else 0, axis=1)
            
            # Display Top 10 nicely
            cols_to_show = [
                'symbol', 'VI Score', 'price', 'fair_value'
            ]
            col_names = [
                'หุ้น', 'VI Score', 'ราคา', 'Fair'
            ]
            
            # If advanced analysis is done, insert Graham next to Fair Value
            if 'Super_Score' in top_picks.columns:
                 # Calculate VI Price (Average of Fair and Graham)
                 # Handle cases where Graham is 0 or NaN
                 def calc_vi_price(row):
                     vals = []
                     if row['fair_value'] > 0: vals.append(row['fair_value'])
                     if row['graham_num'] > 0: vals.append(row['graham_num'])
                     return sum(vals) / len(vals) if vals else 0
                 
                 top_picks['vi_price'] = top_picks.apply(calc_vi_price, axis=1)
                 top_picks['vi_mos'] = top_picks.apply(lambda row: ((row['vi_price'] - row['price']) / row['vi_price'] * 100) if row['vi_price'] > 0 else 0, axis=1)
                 
                 cols_to_show.extend(['graham_num', 'vi_price', 'vi_mos'])
                 col_names.extend(['Graham', 'VI Price', 'VI MOS%'])
            else:
                 # Standard MOS if no Graham
                 cols_to_show.append('margin_of_safety')
                 col_names.append('MOS%')

            # Add remaining base columns
            cols_to_show.extend([
                'P/E', 'P/BV', 'trailingEps', 'returnOnAssets',
                'returnOnEquity', 'debtToEquityRatio', 'currentRatio', 'profitMargins',
                'dividendRate', 'dividendYield_calc', 'VI Score'
            ])
            col_names.extend([
                'P/E', 'P/BV', 'EPS', 'ROA%',
                'ROE%', 'D/E', 'Liquidity', 'NPM%',
                'ปันผล(฿)', 'ปันผล(%)', 'VI Score'
            ])
            
            # Add remaining advanced columns
            if 'Super_Score' in top_picks.columns:
                cols_to_show.extend(['fcf_yield', 'z_score', 'sgr', 'f_score', 'magic_roc', 'magic_ey', 'Super_Score'])
                col_names.extend(['FCF%', 'Z-Score', 'SGR%', 'F-Score', 'ROC%', 'EY%', 'Score'])
            
            top_display = top_picks[cols_to_show].copy()
            top_display.columns = col_names
            
            # Remove duplicate columns if any (e.g. VI Score if added multiple times)
            top_display = top_display.loc[:, ~top_display.columns.duplicated()]

            # Dynamic formatting dict
            fmt_dict = {
                'ราคา': '{:.2f}',
                'Fair': '{:.2f}',
                'Graham': '{:.2f}',
                'VI Price': '{:.2f}',
                'VI MOS%': '{:.2f}',
                'MOS%': '{:.2f}',
                'P/E': '{:.2f}',
                'P/BV': '{:.2f}',
                'EPS': '{:.2f}',
                'ROA%': '{:.2%}',
                'ROE%': '{:.2%}',
                'D/E': '{:.2f}',
                'Liquidity': '{:.2f}',
                'NPM%': '{:.2%}',
                'ปันผล(฿)': '{:.2f}',
                'ปันผล(%)': '{:.2%}',
                'ROC%': '{:.2%}',
                'EY%': '{:.2%}',
                'Score': '{:.0f}',
                'F-Score': '{:.0f}',
                'VI Score': '{:.0f}',
                'FCF%': '{:.2%}',
                'Z-Score': '{:.2f}',
                'SGR%': '{:.2%}'
            }
            
            # Determine which MOS column to use for gradient
            mos_col = 'VI MOS%' if 'VI MOS%' in top_display.columns else 'MOS%'
            
            def highlight_vi_price(x):
                # Create a DataFrame of styles
                df_st = pd.DataFrame('', index=x.index, columns=x.columns)
                if 'VI Price' in x.columns:
                    df_st['VI Price'] = 'background-color: #fff9c4; color: black; font-weight: bold' # Light Yellow
                return df_st

            st.dataframe(
                top_display.style.format(fmt_dict)
                .background_gradient(subset=[mos_col], cmap='Greens')
                .apply(highlight_vi_price, axis=None),
                use_container_width=True
            )
        else:
            st.warning("ไม่พบหุ้นที่ผ่านเกณฑ์พื้นฐาน (MOS > 0, ROE > 10%, ปันผล > 3%) ลองปรับเกณฑ์ความเสี่ยงดูครับ")

        # Main Screener Results
        st.markdown("---")
        st.subheader(f"ผลการคัดกรองหุ้นทั้งหมด (พบ: {len(filtered_df)} ตัว)")
        
        # Formatting for display
        
        # Calculate P/E and P/BV
        # P/E = Price / EPS
        # P/BV = Price / Book Value
        filtered_df['P/E'] = filtered_df.apply(lambda row: row['price'] / row['trailingEps'] if row['trailingEps'] > 0 else 0, axis=1)
        filtered_df['P/BV'] = filtered_df.apply(lambda row: row['price'] / row['bookValue'] if row['bookValue'] > 0 else 0, axis=1)
        
        filtered_df['dividendYield_pct'] = filtered_df.apply(lambda row: row['dividendRate'] / row['price'] if row['price'] > 0 else 0, axis=1)
        
        display_df = filtered_df[[
            'symbol', 'price', 'fair_value', 'margin_of_safety', 
            'P/E', 'pegRatio', 'P/BV', 'trailingEps', 
            'returnOnAssets', 'returnOnEquity', 
            'grossMargins', 'operatingMargins', 'profitMargins',
            'debtToEquityRatio', 'currentRatio', 'quickRatio',
            'revenueGrowth', 'enterpriseToEbitda',
            'dividendRate', 'dividendYield_pct', 'Quality Score'
        ]].copy()
        
        # Rename columns for readable headers
        display_df.columns = [
            'หุ้น', 'ราคา', 'Fair', 'MOS%',
            'P/E', 'PEG', 'P/BV', 'EPS',
            'ROA%', 'ROE%',
            'GPM%', 'OPM%', 'NPM%',
            'D/E', 'Liquidity', 'Quick',
            'Growth%', 'EV/EBITDA',
            'ปันผล(฿)', 'ปันผล(%)', 'Q-Score'
        ]
        
        # Apply formatting
        st.dataframe(
            display_df.style.format({
                'ราคา': '{:.2f}', 
                'Fair': '{:.2f}', 
                'MOS%': '{:.2f}',
                'P/E': '{:.2f}',
                'PEG': '{:.2f}',
                'P/BV': '{:.2f}',
                'EPS': '{:.2f}',
                'ROA%': '{:.2%}',
                'ROE%': '{:.2%}',
                'GPM%': '{:.2%}',
                'OPM%': '{:.2%}',
                'NPM%': '{:.2%}',
                'D/E': '{:.2f}',
                'Liquidity': '{:.2f}',
                'Quick': '{:.2f}',
                'Growth%': '{:.2%}',
                'EV/EBITDA': '{:.2f}',
                'ปันผล(฿)': '{:.2f}',
                'ปันผล(%)': '{:.2%}'
            }).apply(lambda x: ['background-color: rgba(16, 185, 129, 0.2)' if x['MOS%'] > 15 else '' for i in x], axis=1),
            use_container_width=True,
            height=600
        )
        
        st.info("💡 **เกร็ดความรู้:** หุ้นที่มี 'MOS (%)' เขียว (> 15%) คือหุ้นที่มีส่วนลดจากมูลค่าจริงมาก")
        
        with st.expander("📖 อธิบายความหมายอัตราส่วนทางการเงิน (Financial Glossary)"):
            st.markdown("""
            *   **P/E (Price-to-Earnings Ratio):** ความถูกแพงของหุ้นเทียบกับกำไรสุทธิ (ค่ายิ่งต่ำยิ่งถูก)
            *   **PEG (P/E to Growth):** P/E เทียบกับการเติบโตของกำไร (ค่า < 1 แสดงว่าหุ้นยังถูกเมื่อเทียบกับการเติบโต)
            *   **P/BV (Price-to-Book Ratio):** ราคาหุ้นเทียบกับมูลค่าทางบัญชี (ค่ายิ่งต่ำยิ่งถูก, < 1 แสดงว่าซื้อต่ำกว่ามูลค่าสินทรัพย์)
            *   **EPS (Earnings Per Share):** กำไรสุทธิต่อหุ้น 1 หุ้น (ยิ่งมากยิ่งดี)
            *   **ROA (Return on Assets):** ความสามารถในการทำกำไรจากสินทรัพย์ที่มี (ยิ่งสูงยิ่งดี, บ่งบอกประสิทธิภาพผู้บริหาร)
            *   **ROE (Return on Equity):** ผลตอบแทนต่อส่วนของผู้ถือหุ้น (ยิ่งสูงยิ่งดี, Warren Buffett ชอบ > 15%)
            *   **GPM (Gross Profit Margin):** อัตรากำไรขั้นต้น (ขายของได้กำไรกี่ % ก่อนหักค่าใช้จ่ายบริหาร)
            *   **OPM (Operating Profit Margin):** อัตรากำไรจากการดำเนินงาน (วัดประสิทธิภาพธุรกิจหลัก)
            *   **NPM (Net Profit Margin):** อัตรากำไรสุทธิ (กำไรบรรทัดสุดท้าย / รายได้, ยิ่งสูงยิ่งดี)
            *   **D/E (Debt-to-Equity Ratio):** หนี้สินต่อทุน (ค่ายิ่งต่ำยิ่งปลอดภัย, ไม่ควรเกิน 2 เท่า)
            *   **Current Ratio:** อัตราส่วนสภาพคล่อง (สินทรัพย์หมุนเวียน / หนี้สินหมุนเวียน, ควร > 1.5 เท่า)
            *   **Quick Ratio:** สภาพคล่องหมุนเวียนเร็ว (ตัดสต็อกสินค้าออก, วัดความสามารถชำระหนี้ระยะสั้นแบบเข้มข้น)
            *   **Rev Growth:** อัตราการเติบโตของรายได้ (เทียบปีต่อปี)
            *   **EV/EBITDA:** มูลค่ากิจการเทียบกับกำไรเงินสด (ใช้ดูความถูกแพงแทน P/E ได้ดีในหุ้นที่มีค่าเสื่อมเยอะ)
            *   **ปันผล (Dividend):** เงินปันผลที่จ่ายให้ผู้ถือหุ้น (บาท)
            *   **F-Score (Piotroski F-Score):** คะแนนสุขภาพทางการเงิน 9 ด้าน (9 = แข็งแกร่งที่สุด, < 4 = อ่อนแอ)
            *   **ROC (Return on Capital):** ผลตอบแทนจากเงินลงทุนดำเนินงาน (หัวใจของ Magic Formula, ยิ่งสูงยิ่งดี)
            *   **E.Yield (Earnings Yield):** ผลตอบแทนกำไรเมื่อเทียบกับมูลค่ากิจการ (ส่วนกลับของ P/E, ยิ่งสูงยิ่งคุ้มค่า)
            *   **Super Score:** คะแนนรวมพิเศษจากโปรแกรมนี้ (เต็ม 100) คำนวณจาก MOS, F-Score, Magic Rank, ROE และปันผล
            *   **Graham Number:** ราคาที่เหมาะสมตามสูตร Benjamin Graham (บิดาแห่ง VI) เน้นสินทรัพย์และกำไร
            *   **FCF Yield (Free Cash Flow Yield):** ผลตอบแทนจากกระแสเงินสดอิสระ (เงินสดจริงที่บริษัททำได้) เทียบกับมูลค่ากิจการ
            *   **Z-Score (Altman Z-Score):** ดัชนีชี้วัดความเสี่ยงล้มละลาย (Safe > 2.99, Distress < 1.81) ช่วยกรองหุ้นเน่า
            *   **SGR (Sustainable Growth Rate):** อัตราการเติบโตที่ยั่งยืนด้วยเงินทุนตัวเอง (ไม่กู้เพิ่ม/ไม่เพิ่มทุน)
            """)
        
        # --- Display Advanced Results if available (Optional: Keep it hidden or move to debug) ---
        # User requested to combine into one table, so we hide the separate Magic Formula table
        # but we keep the logic above to feed the "Super Stocks" table.
        
    else:
        st.error("ไม่สามารถโหลดข้อมูลได้ โปรดตรวจสอบการเชื่อมต่ออินเทอร์เน็ต")


        # Sector Heatmap
        st.markdown("---")
        st.subheader("🗺️ แผนภาพความร้อนรายอุตสาหกรรม (Sector Heatmap)")
        st.markdown("ขนาดกล่อง = มูลค่าตลาด (Market Cap), สี = ความถูกแพง (Margin of Safety)")
        
        # Prepare Data for Heatmap
        # Ignore huge outliers for color scale or clamp them?
        heat_df = df[df['marketCap'] > 0].copy()
        
        fig_treemap = px.treemap(
            heat_df, 
            path=[px.Constant("SET100"), 'sector', 'symbol'], 
            values='marketCap',
            color='margin_of_safety',
            color_continuous_scale='RdYlGn',
            color_continuous_midpoint=0,
            hover_data=['price', 'fair_value']
        )
        fig_treemap.update_layout(height=600)
        st.plotly_chart(fig_treemap, use_container_width=True)

elif page == "วิเคราะห์หุ้นรายตัว":
    st.title("🔎 วิเคราะห์หุ้นเจาะลึก (Pro Stock Analysis)")
    
    # Select Stock
    selected_ticker = st.selectbox("เลือกหุ้นที่ต้องการวิเคราะห์", SET100_TICKERS)
    
    if st.button("เริ่มวิเคราะห์"):
        with st.spinner(f"กำลังวิเคราะห์ {selected_ticker}..."):
            # Get fresh data (or we could use cached if passed, but let's fetch fresh deeper data)
            stock_data = utils.get_stock_data(selected_ticker)
            valuation = utils.calculate_valuations(stock_data)
            fin_hist = utils.get_financial_history(selected_ticker)
            
            if valuation:
                # --- HEADER SECTION ---
                st.markdown(f"## {valuation['longName']} ({valuation['symbol']})")
                st.markdown(f"**อุตสาหกรรม:** {valuation.get('sector')} | **ธุรกิจ:** {valuation.get('summary')[:150]}...")
                
                # Gauge / Recommendation
                rec_val = valuation.get('recommendation', 3.0) # 1=Buy, 5=Sell
                target_price = valuation.get('targetPrice', 0)
                current_price = valuation.get('price', 0)
                fair_val = valuation.get('fair_value', 0)
                
                # Pro Data Fetching
                dupont_data = utils.calculate_dupont(selected_ticker)
                quarterly_data = utils.get_quarterly_financials(selected_ticker)
                
                # --- EXPORT BUTTON ---
                csv_data = fin_hist.to_csv().encode('utf-8')
                st.download_button(
                    label="💾 Download Financial Data (CSV)",
                    data=csv_data,
                    file_name=f'{selected_ticker}_financials.csv',
                    mime='text/csv',
                )
                
                col_head1, col_head2, col_head3 = st.columns([1, 2, 1])
                
                with col_head1:
                    st.metric("ราคาปัจจุบัน", f"฿{current_price:.2f}")
                    
                    # Simple Sentiment Color
                    if rec_val <= 2.0:
                        st.success("นักวิเคราะห์: แนะนำซื้อ (BUY)")
                    elif rec_val >= 4.0:
                        st.error("นักวิเคราะห์: แนะนำขาย (SELL)")
                    else:
                        st.warning("นักวิเคราะห์: แนะนำถือ (HOLD)")
                        
                with col_head2:
                    # Comparison Bar
                    st.markdown("##### ราคาตลาด vs มูลค่าที่เหมาะสม")
                    comp_data = pd.DataFrame({
                        'Type': ['ราคาปัจจุบัน', 'เป้านักวิเคราะห์', 'มูลค่าพื้นฐาน (VI)'],
                        'Price': [current_price, target_price, fair_val]
                    })
                    fig_comp = px.bar(comp_data, x='Price', y='Type', orientation='h', text='Price', 
                                      color='Type', color_discrete_map={'ราคาปัจจุบัน': 'grey', 'เป้านักวิเคราะห์': '#3b82f6', 'มูลค่าพื้นฐาน (VI)': '#10b981'})
                    fig_comp.update_layout(height=200, margin=dict(l=0, r=0, t=0, b=0))
                    fig_comp.update_traces(texttemplate='฿%{text:.2f}')
                    st.plotly_chart(fig_comp, use_container_width=True)

                with col_head3:
                    mos = valuation.get('margin_of_safety', 0)
                    st.metric("MOS (ส่วนเผื่อความปลอดภัย)", f"{mos:.2f}%", 
                              delta="ราคาถูก (Undervalued)" if mos > 0 else "ราคาแพง (Overvalued)",
                              delta_color="normal" if mos > 0 else "inverse")
                
                # --- KEY STATS GRID ---
                st.subheader("📊 อัตราส่วนทางการเงินที่สำคัญ (Key Ratios)")
                k1, k2, k3, k4 = st.columns(4)
                
                with k1:
                    st.markdown("**ความถูกแพง (Valuation)**")
                    st.metric("P/E Ratio", f"{valuation.get('price') / valuation.get('trailingEps') if valuation.get('trailingEps') else 0:.2f}") 
                    st.metric("P/BV Ratio", f"{valuation.get('price') / valuation.get('bookValue') if valuation.get('bookValue') else 0:.2f}")
                    st.metric("PEG Ratio", f"{valuation.get('pegRatio', 0):.2f}")
                
                with k2:
                    st.markdown("**ประสิทธิภาพ (Efficiency)**")
                    st.metric("ROE (ผลตอบแทนส่วนผู้ถือหุ้น)", f"{valuation.get('returnOnEquity', 0)*100:.2f}%")
                    st.metric("ROA (ผลตอบแทนสินทรัพย์)", f"{valuation.get('returnOnAssets', 0)*100:.2f}%")
                    st.metric("Profit Margin (อัตรากำไร)", f"{valuation.get('profitMargins', 0)*100:.2f}%")
                    
                with k3:
                    st.markdown("**สุขภาพการเงิน (Health)**")
                    st.metric("D/E Ratio (หนี้สิน/ทุน)", f"{valuation.get('debtToEquity', 0)/100:.2f}") 
                    st.metric("Current Ratio (สภาพคล่อง)", f"{valuation.get('currentRatio', 0):.2f}")
                    st.metric("Beta (ความผันผวน)", f"{valuation.get('beta', 1.0):.2f}")

                with k4:
                    st.markdown("**ปันผล (Dividend)**")
                    st.metric("Yield (ผลตอบแทน)", f"{(valuation.get('dividendRate',0) / current_price * 100) if current_price else 0:.2f}%")
                    st.metric("Payout Ratio (สัดส่วนจ่าย)", f"{valuation.get('payoutRatio', 0)*100:.2f}%")
                
                # --- FINANCIAL TRENDS & FORECAST ---
                st.markdown("---")
                st.subheader("📈 ผลประกอบการย้อนหลัง & คาดการณ์อนาคต")
                st.info("ℹ️ **หมายเหตุข้อมูล:** ข้อมูลย้อนหลังประมาณ 4 ปีล่าสุด | ตัวเลขคาดการณ์อ้างอิงจากบทวิเคราะห์ (Analyst Estimates)")
                
                # Tabs for different views
                tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs([
                    "📊 การเติบโต", "💪 ประสิทธิภาพ", "🔮 คาดการณ์", "📉 PE Band",
                    "💎 Dupont Analysis", "💰 Earnings Quality", "📅 รายไตรมาส",
                    "⚔️ คู่แข่ง", "🧮 ประเมินมูลค่า", "🕵️ ผู้ถือหุ้น", "🕵️‍♂️ Jea Luk Forensic"
                ])
                
                # General Check for History because Tab 1-4 rely on it
                has_history = not fin_hist.empty
                
                if has_history:
                    with tab1:
                        # Revenue & Profit Combo
                        f1, f2 = st.columns(2)
                        with f1:
                            fig_fin = go.Figure()
                            fig_fin.add_trace(go.Bar(x=fin_hist.index, y=fin_hist['Revenue'], name='รายได้ (Revenue)', marker_color='#60a5fa'))
                            fig_fin.add_trace(go.Scatter(x=fin_hist.index, y=fin_hist['Net Profit'], name='กำไรสุทธิ (Net Profit)', mode='lines+markers', line=dict(color='#10b981', width=3)))
                            fig_fin.update_layout(title="แนวโน้มรายได้ vs กำไรสุทธิ", legend=dict(orientation="h"))
                            st.plotly_chart(fig_fin, use_container_width=True)
                            
                        with f2:
                            # EPS Trend
                            if 'EPS' in fin_hist.columns:
                                fig_eps = px.bar(fin_hist, x=fin_hist.index, y='EPS', title="กำไรต่อหุ้น (EPS)", text_auto='.2f')
                                fig_eps.update_traces(marker_color='#8b5cf6')
                                st.plotly_chart(fig_eps, use_container_width=True)
                                
                    with tab2:
                        # Ratios Triple Chart
                        r1, r2, r3 = st.columns(3)
                        
                        with r1:
                            if 'ROE (%)' in fin_hist.columns:
                                fig_roe = px.line(fin_hist, x=fin_hist.index, y='ROE (%)', markers=True, title="ROE (%)")
                                fig_roe.update_traces(line_color='#ef4444')
                                st.plotly_chart(fig_roe, use_container_width=True)
                        
                        with r2:
                            if 'NPM (%)' in fin_hist.columns:
                                fig_npm = px.line(fin_hist, x=fin_hist.index, y='NPM (%)', markers=True, title="Net Profit Margin (%)")
                                fig_npm.update_traces(line_color='#f59e0b')
                                st.plotly_chart(fig_npm, use_container_width=True)

                        with r3:
                            if 'D/E (x)' in fin_hist.columns:
                                fig_de = px.bar(fin_hist, x=fin_hist.index, y='D/E (x)', title="D/E Ratio (เท่า)", text_auto='.2f')
                                fig_de.update_traces(marker_color='#64748b')
                                st.plotly_chart(fig_de, use_container_width=True)
                


                    with tab3:
                        # Forecast Logic
                        # We have Trailing EPS and Forward EPS.
                        # Let's project 2 years
                        current_year_eps = valuation.get('trailingEps')
                        next_year_eps = valuation.get('forwardEps')
                    
                        if current_year_eps and next_year_eps:
                            # Simple 2-point projection
                            # Avoid div by zero
                            denom = abs(current_year_eps) if current_year_eps != 0 else 1
                            growth = (next_year_eps - current_year_eps) / denom
                            
                            # Project Year+2 with same growth rate (Conservative)
                            year_2_eps = next_year_eps * (1 + (growth * 0.8)) # Decay growth slightly
                            
                            forecast_data = pd.DataFrame({
                                'Year': ['ปีปัจจุบัน (TTM)', 'ปีหน้า (คาดการณ์)', 'ปีถัดไป (คาดการณ์)'],
                                'EPS': [current_year_eps, next_year_eps, year_2_eps],
                                'Type': ['ของจริง', 'คาดการณ์', 'คาดการณ์']
                            })
                            
                            f_col1, f_col2 = st.columns([2, 1])
                            with f_col1:
                                fig_fore = px.line(forecast_data, x='Year', y='EPS', markers=True, title="คาดการณ์กำไรต่อหุ้น (Earnings Forecast)", text='EPS')
                                fig_fore.update_traces(texttemplate='%{text:.2f}', textposition="top center", line=dict(color='#0ea5e9', width=3, dash='dot'))
                                st.plotly_chart(fig_fore, use_container_width=True)
                                
                            with f_col2:
                                st.metric("การเติบโตคาดหวัง (1Y)", f"{growth*100:.2f}%")
                                st.metric("Forward EPS", f"{next_year_eps:.2f}")
                                st.markdown("*(E) = ตัวเลขประมาณการ*")
                        else:
                            st.info("ไม่มีข้อมูลประมาณการจากนักวิเคราะห์")
                    
                    with tab4:
                        st.subheader("📉 Historical PE Band")
                        st.info("กราฟแสดงราคาหุ้นเทียบกับกรอบราคาที่คิดจากค่า PE ย้อนหลัง 5 ปี (ช่วยดูว่าตอนนี้ถูกหรือแพงเมื่อเทียบกับตัวเองในอดีต)")
                        
                        pe_band_data = utils.get_historical_pe_bands(selected_ticker)
                        
                        if pe_band_data:
                            band_df = pe_band_data['data']
                             
                            fig_band = go.Figure()
                             
                            # Price
                            fig_band.add_trace(go.Scatter(x=band_df['Date'], y=band_df['Close'], name='ราคาหุ้น (Price)', line=dict(color='black', width=3)))
                             
                            # Bands
                            fig_band.add_trace(go.Scatter(x=band_df['Date'], y=band_df['Mean PE'], name=f'Avg PE ({pe_band_data["avg_pe"]:.1f}x)', line=dict(color='orange', dash='dash')))
                            fig_band.add_trace(go.Scatter(x=band_df['Date'], y=band_df['+1 SD'], name='+1 SD', line=dict(color='red', width=1)))
                            fig_band.add_trace(go.Scatter(x=band_df['Date'], y=band_df['+2 SD'], name='+2 SD (แพงมาก)', line=dict(color='darkred', width=1, dash='dot')))
                            fig_band.add_trace(go.Scatter(x=band_df['Date'], y=band_df['-1 SD'], name='-1 SD', line=dict(color='green', width=1)))
                            fig_band.add_trace(go.Scatter(x=band_df['Date'], y=band_df['-2 SD'], name='-2 SD (ถูกมาก)', line=dict(color='darkgreen', width=1, dash='dot')))
                             
                            fig_band.update_layout(title=f"PE Band: {selected_ticker}", hovermode="x unified")
                            st.plotly_chart(fig_band, use_container_width=True)
                             
                            st.markdown(f"**ค่าเฉลี่ย PE 5 ปีย้อนหลัง:** {pe_band_data['avg_pe']:.2f} เท่า | **PE ปัจจุบัน:** {pe_band_data['current_pe']:.2f} เท่า")
                        else:
                            st.error("ข้อมูลไม่เพียงพอสำหรับสร้าง PE Band (ต้องการกำไรย้อนหลังต่อเนื่อง)")
                
                else:
                    with tab1: st.warning("ไม่มีข้อมูลย้อนหลัง")
                    with tab2: st.warning("ไม่มีข้อมูลย้อนหลัง")
                    with tab3: st.warning("ไม่มีข้อมูลย้อนหลัง")
                    with tab4: st.warning("ไม่มีข้อมูลย้อนหลัง")

                # --- NEW VI TABS ---
                with tab5:
                    st.subheader("💎 Dupont Analysis (Decompose ROE)")
                    st.info("เจาะลึกที่มาของผลตอบแทนส่วนผู้ถือหุ้น (ROE) ว่ามาจาก 1. กำไรดี (NPM) 2. หมุนรอบสินทรัพย์เร็ว (Asset Turnover) หรือ 3. กู้มาเยอะ (Leverage)")
                    
                    if dupont_data is not None and not dupont_data.empty:
                        # Chart ROE Breakdown
                        fig_dupont = go.Figure()
                        fig_dupont.add_trace(go.Bar(x=dupont_data['Year'], y=dupont_data['Net Margin (%)'], name='Net Margin (%)', marker_color='#10b981'))
                        fig_dupont.add_trace(go.Bar(x=dupont_data['Year'], y=dupont_data['Asset Turnover (x)'], name='Asset Turnover (x)', marker_color='#3b82f6', visible='legendonly')) # Turnover scale is small
                        fig_dupont.add_trace(go.Scatter(x=dupont_data['Year'], y=dupont_data['ROE (%)'], name='ROE (%)', mode='lines+markers', line=dict(color='#ef4444', width=3)))
                        
                        st.plotly_chart(fig_dupont, use_container_width=True)
                        st.dataframe(dupont_data.style.format({
                            'Net Margin (%)': '{:.2f}', 
                            'Asset Turnover (x)': '{:.2f}', 
                            'Equity Multiplier (x)': '{:.2f}', 
                            'ROE (%)': '{:.2f}'
                        }))
                    else:
                        st.warning("ไม่สามารถคำนวณ Dupont Analysis ได้ (ข้อมูลไม่ครบ)")

                with tab6:
                    st.subheader("💰 Quality of Earnings")
                    st.info("ตรวจสอบคุณภาพกำไร: กระแสเงินสดจากการดำเนินงาน (CFO) ควรมากกว่ากำไรสุทธิ (Net Profit)")
                    
                    # Calculate CFO/NI from fin_hist if possible or fetch from utils if not in fin_hist
                    # We can use quarterly data or modify fin_hist to include CFO. 
                    # Let's use quarterly data summed up or just use quarterly trend for this check if annual not available.
                    # Ideally update get_financial_history to include CFO, but here we can try to use quarterly data as proxy if annual missing
                    
                    if quarterly_data is not None and not quarterly_data.empty and 'Operating Cash Flow' in quarterly_data.columns:
                        # Plot CFO vs Net Income (Quarterly)
                        q_chart = quarterly_data.tail(8) # Last 8 Quarters
                        fig_qoe = go.Figure()
                        fig_qoe.add_trace(go.Bar(x=q_chart.index, y=q_chart['Net Profit'], name='Net Profit', marker_color='#ef4444'))
                        fig_qoe.add_trace(go.Bar(x=q_chart.index, y=q_chart['Operating Cash Flow'], name='CFO (Cash Flow)', marker_color='#10b981'))
                        
                        fig_qoe.update_layout(title="กำไรทางบัญชี vs กระแสเงินสดจริง (รายไตรมาส)", barmode='group')
                        st.plotly_chart(fig_qoe, use_container_width=True)
                        
                        # Ratio Check
                        last_q = quarterly_data.iloc[-1]
                        cfo = last_q.get('Operating Cash Flow', 0)
                        ni = last_q.get('Net Profit', 0)
                        if ni > 0:
                            ratio = cfo / ni
                            st.metric("CFO / Net Profit (Latest Q)", f"{ratio:.2f}x", 
                                      delta="คุณภาพดี (Cash > Profit)" if ratio > 1 else "ต้องระวัง (Cash < Profit)",
                                      delta_color="normal" if ratio > 1 else "inverse")
                    else:
                        st.warning("ไม่มีข้อมูลกระแสเงินสดรายไตรมาส")

                with tab7:
                    st.subheader("📅 Quarterly Financial Trends")
                    if quarterly_data is not None and not quarterly_data.empty:
                        st.dataframe(quarterly_data.sort_index(ascending=False).style.format("{:,.2f}"))
                        
                        # Growth Chart
                        if 'Revenue Growth YoY' in quarterly_data.columns:
                            fig_growth = px.bar(quarterly_data.tail(8), x=quarterly_data.tail(8).index, y=['Revenue Growth YoY', 'Profit Growth YoY'], barmode='group', title="การเติบโต YoY (%)")
                            st.plotly_chart(fig_growth, use_container_width=True)
                    else:
                        st.warning("ไม่มีข้อมูลรายไตรมาส")

                # --- PHASE 2 TABS ---
                with tab8:
                    st.subheader("⚔️ Competitor Comparison (Sector Peers)")
                    st.info("เปรียบเทียบกับหุ้นในกลุ่มอุตสาหกรรมเดียวกัน (Top Players)")
                    
                    competitors = utils.get_competitors(selected_ticker)
                    if competitors:
                        comp_list = []
                        # Add Self first
                        competitors.insert(0, selected_ticker.replace('.BK', ''))
                        
                        cols = st.columns(len(competitors))
                        
                        for idx, ticker in enumerate(competitors):
                            with cols[idx]:
                                st.markdown(f"**{ticker}**")
                                c_data = utils.get_stock_data(ticker)
                                if c_data:
                                    c_price = c_data.get('price', 0)
                                    c_pe = c_data.get('price') / c_data.get('trailingEps') if c_data.get('trailingEps') and c_data.get('price') else 0
                                    c_pbv = c_data.get('price') / c_data.get('bookValue') if c_data.get('bookValue') and c_data.get('price') else 0
                                    c_roe = c_data.get('returnOnEquity', 0) * 100
                                    c_yield = c_data.get('dividendRate', 0) / c_price * 100 if c_price else 0
                                    
                                    st.metric("Price", f"{c_price:.2f}")
                                    st.markdown(f"P/E: **{c_pe:.2f}**")
                                    st.markdown(f"P/BV: **{c_pbv:.2f}**")
                                    st.markdown(f"ROE: **{c_roe:.2f}%**")
                                    st.markdown(f"Yield: **{c_yield:.2f}%**")
                    else:
                        st.warning("ไม่พบข้อมูลคู่แข่งในระบบ")

                with tab9:
                    st.subheader("🧮 Valuation Playground (Custom DCF/PE)")
                    st.info("จำลองการประเมินมูลค่าหุ้นด้วยสมมติฐานของคุณเอง (Sensitivity Analysis)")
                    
                    if valuation:
                        col_curr, col_input = st.columns([1, 2])
                        
                        with col_input:
                            st.markdown("##### ปรับสมมติฐาน (Assumptions)")
                            input_growth = st.slider("Growth Rate (%)", min_value=0.0, max_value=20.0, value=float(LONG_TERM_GROWTH*100), step=0.5) / 100
                            input_rf = st.slider("Risk Free Rate (%)", min_value=1.0, max_value=6.0, value=float(RISK_FREE_RATE*100), step=0.1) / 100
                            input_market_ret = st.slider("Market Call (Return) (%)", min_value=5.0, max_value=15.0, value=float(MARKET_RETURN*100), step=0.5) / 100
                            input_pe_terminal = st.number_input("Terminal P/E (สำหรับ PE Method)", value=15.0, step=0.5)
                        
                        # Recalculate
                        # Simple DDM & EPS*PE
                        current_eps = valuation.get('trailingEps', 0)
                        current_div = valuation.get('dividendRate', 0)
                        
                        # CAPM Cost of Equity
                        beta = valuation.get('beta', 1.0)
                        cost_of_equity = input_rf + beta * (input_market_ret - input_rf)
                        
                        # DDM (Infinite Growth)
                        # Value = D1 / (k - g)
                        if (cost_of_equity - input_growth) > 0 and current_div > 0:
                            d1 = current_div * (1 + input_growth)
                            val_ddm_custom = d1 / (cost_of_equity - input_growth)
                        else:
                            val_ddm_custom = 0 # Invalid
                            
                        # PE Valuation
                        # EPS * PE
                        val_pe_custom = current_eps * input_pe_terminal
                        
                        with col_curr:
                            st.markdown("##### ผลลัพธ์ (New Fair Value)")
                            st.metric("Cost of Equity (CAPM)", f"{cost_of_equity*100:.2f}%")
                            
                            st.markdown("---")
                            st.caption("Dividend Discount Model")
                            st.metric("DDM Value", f"฿{val_ddm_custom:.2f}", delta=f"{val_ddm_custom - current_price:.2f}")
                            
                            st.caption(f"P/E Multiple ({input_pe_terminal}x)")
                            st.metric("PE Value", f"฿{val_pe_custom:.2f}", delta=f"{val_pe_custom - current_price:.2f}")

                with tab10:
                    st.subheader("🕵️ ข้อมูลผู้ถือหุ้น (Shareholders)")
                    major_holders, inst_holders = utils.get_shareholders(selected_ticker)
                    
                    sh_col1, sh_col2 = st.columns(2)
                    
                    with sh_col1:
                        st.markdown("##### ผู้ถือหุ้นรายใหญ่ (Major Holders)")
                        if major_holders is not None and not major_holders.empty:
                            st.dataframe(major_holders)
                        else:
                            st.warning("ไม่พบข้อมูลผู้ถือหุ้นรายใหญ่")
                            
                    with sh_col2:
                        st.markdown("##### กองทุน/สถาบัน (Institutional Holders)")
                        if inst_holders is not None and not inst_holders.empty:
                            st.dataframe(inst_holders)
                        else:
                            st.info("ไม่พบข้อมูลการถือครองของสถาบัน (อาจเป็นหุ้นขนาดเล็ก)")

                with tab11:
                    st.subheader("🕵️‍♂️ เจาะลึกคุณภาพ & จับผิดงบ (Forensic & Quality)")
                    
                    with st.spinner("กำลังวิเคราะห์ความผิดปกติของงบการเงิน..."):
                        qual_metrics = utils.calculate_quality_metrics(selected_ticker)
                        forensic_metrics = utils.calculate_forensic_metrics(selected_ticker)
                    
                    if qual_metrics:
                        st.markdown("##### 💎 คุณภาพการเติบโต (Quality Factors)")
                        q1, q2 = st.columns(2)
                        with q1:
                            # ROIC
                            roic = qual_metrics.get('ROIC', 0)
                            st.metric("ROIC (ผลตอบแทนเงินลงทุน)", f"{roic*100:.2f}%", help="EBIT * (1-Tax) / Invested Capital. ยิ่งสูงกว่า WACC ยิ่งดี (ควร > 10-15%)")
                        with q2:
                            # GPM Stability
                            gpm_stab = qual_metrics.get('GPM_Stability', 0)
                            st.metric("GPM Stability (ความนิ่งกำไรขั้นต้น)", f"{gpm_stab*100:.2f}%", help="SD ของ GPM 5 ปีย้อนหลัง. ยิ่งต่ำยิ่งดี (แสดงถึงอำนาจต่อรอง)")
                            
                        # Chart GPM Trend
                        if 'GPM_Trend' in qual_metrics:
                            st.caption("แนวโน้มอัตรากำไรขั้นต้น (GPM Trend)")
                            st.line_chart(qual_metrics['GPM_Trend'])

                    st.markdown("---")
                    
                    if forensic_metrics:
                        st.markdown("##### 🚨 จับผิดงบการเงิน (Forensic Analysis)")
                        f1, f2 = st.columns(2)
                        with f1:
                            # M-Score
                            m_score = forensic_metrics.get('M_Score', -99)
                            m_msg = "Safe"
                            delta_col = "normal"
                            
                            if m_score > -1.78:
                                m_msg = "High Risk (Likely Manipulated)"
                                delta_col = "inverse" # Red
                            elif m_score > -2.22:
                                m_msg = "Grey Area (Caution)"
                                delta_col = "off" # Grey
                            else:
                                m_msg = "Safe (Unlikely)"
                                delta_col = "normal" # Green (interpret inverted manually)
                            
                            # Streamlit delta color 'inverse' means Red for positive delta? 
                            # Actually let's just use text
                            st.metric("Beneish M-Score", f"{m_score:.2f}", delta=m_msg, delta_color="inverse" if m_score > -2.22 else "normal")
                            st.caption("*ค่า > -1.78 มีความเสี่ยงตกแต่งบัญชีสูง*")

                        with f2:
                            # Sloan Ratio
                            sloan = forensic_metrics.get('Sloan_Ratio', 0)
                            s_msg = "Safe"
                            s_col = "normal"
                            if abs(sloan) > 0.25:
                                s_msg = "Poor Quality (High Accruals)"
                                s_col = "inverse"
                            elif abs(sloan) > 0.10:
                                s_msg = "Moderate"
                                s_col = "off"
                            
                            st.metric("Sloan Ratio (Accruals)", f"{sloan:.2%}", delta=s_msg, delta_color="inverse" if abs(sloan)>0.1 else "normal")
                            st.caption("*ช่วงปลอดภัย -10% ถึง +10%. ถ้าสูงแปลว่ากำไรไม่ได้มาจากเงินสด*")
                            
                        with st.expander("รายละเอียดตัวแปร M-Score (Breakdown)"):
                            st.json(forensic_metrics.get('Details', {}))
                            st.markdown("""
                            *   **DSRI (Days Sales in Receivables):** ลูกหนี้โตเร็วกว่ายอดขาย? (>1 ไม่ดี)
                            *   **GMI (Gross Margin):** กำไรขั้นต้นแย่ลง? (>1 ไม่ดี)
                            *   **AQI (Asset Quality):** สินทรัพย์ไม่มีตัวตนเพิ่มขึ้น? (>1 ไม่ดี)
                            *   **SGI (Sales Growth):** ยอดขายโตเร็วผิดปกติ? (>1 น่าสงสัย)
                            *   **DEPI (Depreciation):** ตัดค่าเสื่อมช้าลงเพื่อดันกำไร? (>1 ไม่ดี)
                            *   **SGAI (SG&A):** ค่าใช้จ่ายขายบริหารเพิ่มขึ้น? (>1 ไม่ดี)
                            *   **LVGI (Leverage):** หนี้สินเพิ่มขึ้น? (>1 ไม่ดี)
                            *   **TATA (Total Accruals):** รายการคงค้างเทียบสินทรัพย์
                            """)
                    else:
                        st.warning("ข้อมูลไม่เพียงพอสำหรับคำนวณ Forensic Metrics (ต้องใช้งบย้อนหลังอย่างน้อย 2 ปี)")

                # --- 8 Qualities Checklist (Enhanced) ---
                st.markdown("---")
                
                # --- RAW DATA VERIFICATION (NEW) ---
                with st.expander("🔍 ตรวจสอบความถูกต้องของข้อมูล (Data Verification)", expanded=False):
                    st.markdown("### แหล่งที่มาและเวลาของข้อมูล (Data Source & Timestamp)")
                    
                    # Convert timestamp to readable format
                    last_ts = valuation.get('last_price_time', 0)
                    last_time_str = "N/A"
                    if last_ts > 0:
                        import datetime
                        last_time_str = datetime.datetime.fromtimestamp(last_ts).strftime('%Y-%m-%d %H:%M:%S')
                    
                    st.info(f"""
                    **แหล่งข้อมูล:** Yahoo Finance (Real-time delay 15-20 mins)
                    **เวลาล่าสุดของราคา (Last Price Time):** {last_time_str}
                    **สกุลเงิน (Currency):** {valuation.get('currency', 'THB')}
                    **ตลาด (Exchange):** {valuation.get('exchange', 'SET')}
                    """)

                    st.markdown("### ข้อมูลดิบจากระบบ (Raw Data Inspector)")
                    st.json(valuation)
                    st.caption("*หากพบข้อมูลไม่ตรงกับ SETSMART หรือ Streaming อาจเกิดจากความล่าช้าของ Source หรือรอบบัญชีที่แตกต่างกัน (TTM vs Annual)*")

                st.markdown("---")
                st.subheader("📋 แบบประเมินคุณภาพหุ้น VI (Checklist)")
                
                score = 0
                total = 8
                
                check_col1, check_col2 = st.columns(2)
                
                roe = valuation.get('returnOnEquity', 0)
                npm = valuation.get('profitMargins', 0)
                de = valuation.get('debtToEquity', 0) # yfinance returns e.g. 150 for 1.5 ratio often, need to verify.
                # Usually debtToEquity is a percentage in yfinance (e.g. 221.35 means 2.21)
                
                # Logic helpers
                is_strong_roe = roe > 0.15
                is_strong_npm = npm > 0.10
                is_low_debt = de < 200 # < 2.0 D/E
                is_undervalued = mos > 0
                
                with check_col1:
                    c1 = st.checkbox("1. ผู้นำตลาด / ผูกขาด (Market Leader)", help="บริษัทมีส่วนแบ่งการตลาดสูง อำนาจต่อรองสูง?")
                    c2 = st.checkbox("2. คู่แข่งเข้ามายาก (High Barriers to Entry)", help="ธุรกิจเลียนแบบยาก หรือต้องใช้เงินลงทุนสูงมาก?")
                    c3 = st.checkbox("3. กำหนดราคาเองได้ (Pricing Power)", help="ขึ้นราคาสินค้าได้โดยที่ลูกค้าไม่หนีไปไหน?")
                    c4 = st.checkbox("4. ยังมีโอกาสเติบโต (Growth Potential)", help="อุตสาหกรรมยังไม่ตะวันตกดิน ยังโตได้อีก?")
                    
                with check_col2:
                    c5 = st.checkbox(f"5. คุมต้นทุนดี / หนี้ต่ำ (D/E < 2) [Current: {de/100:.2f}x]", value=is_low_debt, help=f"ค่า D/E ปัจจุบัน: {de/100:.2f} เท่า")
                    c6 = st.checkbox(f"6. การเงินแกร่ง (ROE > 15%) [Current: {roe*100:.2f}%]", value=is_strong_roe, help=f"ค่า ROE ปัจจุบัน: {roe*100:.2f}%")
                    c7 = st.checkbox(f"7. กำไรสูง (NPM > 10%) [Current: {npm*100:.2f}%]", value=is_strong_npm, help=f"ค่า NPM ปัจจุบัน: {npm*100:.2f}%")
                    c8 = st.checkbox(f"8. ราคาถูก (MOS > 0%) [Current: {mos:.2f}%]", value=is_undervalued, disabled=True)
                
                # Manual Score Calculation
                manual_checks = sum([c1, c2, c3, c4])
                auto_checks = sum([is_low_debt, is_strong_roe, is_strong_npm, is_undervalued])
                final_score = manual_checks + auto_checks
                
                st.markdown(f"#### **คะแนนคุณภาพรวม: {final_score} / 8**")
                st.progress(final_score / 8)

            else:
                st.error("ไม่สามารถดึงข้อมูลหุ้นตัวนี้ได้")


elif page == "เปรียบเทียบคู่แข่ง":
    st.title("⚔️ เปรียบเทียบคู่แข่ง (Competitor Analysis)")
    st.markdown("เปรียบเทียบตัวเลขทางการเงินของหุ้นหลายตัวแบบตัวต่อตัว")
    
    # Multiselect
    selected_tickers = st.multiselect("เลือกหุ้นมาชนกัน (สูงสุด 5 ตัว)", SET100_TICKERS, default=["ADVANC", "TRUE"] if "TRUE" in SET100_TICKERS else ["ADVANC"])
    
    if len(selected_tickers) > 0:
        if len(selected_tickers) > 5:
            st.warning("เลือกได้สูงสุด 5 ตัวเท่านั้น")
        else:
            with st.spinner("กำลังดึงข้อมูลเปรียบเทียบ..."):
                # Fetch data directly or via utils
                # Use ThreadPool to fetch detailed history for all selected
                
                # 1. Comparison Table (Current Stats)
                # Filter 'df' (global) for efficiency for current stats
                comp_df = df[df['symbol'].isin(selected_tickers)].set_index('symbol')
                
                # Select interesting columns
                cols_to_show = ['price', 'fair_value', 'margin_of_safety', 'dividendRate', 'returnOnEquity', 'profitMargins', 'debtToEquityRatio', 'valuation_pe']
                comp_table = comp_df[cols_to_show].T
                
                # Rename Index for TH
                comp_table.index = ['ราคา', 'มูลค่าเหมาะสม', 'MOS (%)', 'ปันผล (บาท)', 'ROE (%)', 'NPM (%)', 'D/E (เท่า)', 'P/E (เท่า)']
                
                st.subheader("📊 ตารางวัดพลังพื้นฐาน")
                st.dataframe(comp_table.style.format("{:.2f}").background_gradient(axis=1), use_container_width=True)
                
                # 2. Historical Charts Comparison
                st.subheader("📈 กราฟวัดพลังย้อนหลัง")
                
                # We need to fetch history for each
                hist_data = {}
                metrics = ['Revenue', 'Net Profit', 'ROE (%)', 'NPM (%)']
                
                # Fetch history logic
                # For charts we need a combined dataframe
                combined_hist = pd.DataFrame()
                
                for t in selected_tickers:
                     h = utils.get_financial_history(t)
                     if not h.empty:
                         h['Symbol'] = t
                         combined_hist = pd.concat([combined_hist, h])
                
                if not combined_hist.empty:
                    # Choose Metric to compare
                    metric_choice = st.radio("เลือกหัวข้อเปรียบเทียบ", metrics, horizontal=True)
                    
                    if metric_choice in combined_hist.columns:
                        fig_comp = px.bar(combined_hist, x=combined_hist.index, y=metric_choice, color='Symbol', barmode='group', title=f"เปรียบเทียบ {metric_choice}")
                        st.plotly_chart(fig_comp, use_container_width=True)
                    else:
                        st.info(f"ไม่มีข้อมูล {metric_choice}")
                else:
                    st.error("ไม่สามารถดึงข้อมูลย้อนหลังได้")


                    st.error("ไม่สามารถดึงข้อมูลย้อนหลังได้")


elif page == "แนะนำพอร์ตการลงทุน":
    st.title("🍰 แนะนำพอร์ตการลงทุน (Asset Allocation)")
    
    st.markdown("สร้างพอร์ตการลงทุนที่สมดุล ตามหลักการกระจายความเสี่ยง")
    
    # Input with cleaner integer format (Note: Commas in input fields are not supported by Streamlit for editing, so we show a caption)
    capital = st.number_input("เงินลงทุนตั้งต้น (บาท)", min_value=1000, value=100000, step=1000, format="%d")
    st.caption(f"💰 จำนวนเงินที่ระบุ: **{capital:,.0f}** บาท")
    
    # Portfolio Mix (Thai Keys)
    allocation = {
        "พันธบัตร / ตราสารหนี้ (Fixed Income)": 0.40,
        "หุ้นไทยขนาดใหญ่ (SET50)": 0.15,
        "หุ้นต่างประเทศ (Global Stocks)": 0.15,
        "หุ้นเล็ก / หุ้นเติบโต (Growth)": 0.10,
        "ตลาดเกิดใหม่ (Emerging Markets)": 0.10,
        "กองทุนอสังหาฯ (REITs)": 0.10
    }
    
    if st.button("คำนวณสัดส่วนการลงทุน"):
        amounts = utils.calculate_portfolio(capital, allocation)
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("สัดส่วนที่แนะนำ (Target Allocation)")
            # Create DataFrame with Thai columns
            df_port = pd.DataFrame(list(amounts.items()), columns=['ประเภทสินทรัพย์', 'มูลค่า (บาท)'])
            df_port['สัดส่วน (%)'] = df_port['ประเภทสินทรัพย์'].map(allocation) * 100
            
            # Format numbers with commas
            st.dataframe(
                df_port.style.format({
                    'มูลค่า (บาท)': '{:,.2f}', 
                    'สัดส่วน (%)': '{:.1f}%'
                }),
                use_container_width=True
            )
            
        with col2:
            fig = px.pie(
                values=list(amounts.values()), 
                names=list(amounts.keys()), 
                title="แผนภูมิพอร์ตการลงทุน",
                hole=0.4
            )
            st.plotly_chart(fig)
            
        # --- ASSET RECOMMENDATION EXPANDER ---
        st.markdown("---")
        st.subheader("💡 แนะนำสินทรัพย์น่าลงทุน (Asset Recommendations)")
        st.info("รายชื่อสินทรัพย์ยอดนิยมสำหรับคนไทย (คำเตือน: ไม่ใช่คำแนะนำการลงทุน เป็นเพียงตัวอย่างศึกษา)")
        
        with st.expander("🛡️ ตราสารหนี้ & พันธบัตร (40%)", expanded=True):
             st.markdown("""
             **แนวคิด:** รักษาเงินต้น ความเสี่ยงต่ำ
             *   **พันธบัตรไทย:** `LB296A`, `LB31DA` (ซื้อผ่านแอปเป๋าตัง/ธนาคาร)
             *   **กองทุนตราสารหนี้:** `K-FIXED`, `SCBFIXED`, `TMBABF`
             *   **เงินฝาก:** บัญชีออมทรัพย์ดอกเบี้ยสูง (Kept, Dime, etc.)
             """)
             
        with st.expander("🏢 หุ้นไทยขนาดใหญ่ (15%)", expanded=True):
            st.markdown("""
            **แนวคิด:** เติบโตมั่นคง + ปันผลสม่ำเสมอ
            *   **หุ้นเด่น SET100:** `ADVANC`, `PTT`, `AOT`, `KBANK`, `CPALL`
            *   **กองทุนดัชนี (ETF):** `TDEX` (อ้างอิงดัชนี SET50)
            """)
            
        with st.expander("🌐 หุ้นต่างประเทศ (15%)", expanded=True):
            st.markdown("""
            **แนวคิด:** กระจายความเสี่ยงออกนอกประเทศ (US/Tech/China)
            *   **หุ้นเทคฯ สหรัฐ:** `ONE-ULTRAP` (Growth), `SCBNDQ` (Nasdaq)
            *   **หุ้นโลก:** `K-CHANGE`, `TMBGQG`
            *   **DR (ซื้อผ่านตลาดไทย):** `E1VFVN3001` (เวียดนาม), `CNTECH01` (จีนเทค)
            """)

        with st.expander("🏬 กองทุนอสังหาฯ (10%)", expanded=True):
            st.markdown("""
            **แนวคิด:** รับค่าเช่า (Passive Income)
            *   **ห้าง/ออฟฟิศ:** `CPNREIT`, `ALLY`
            *   **คลังสินค้า/นิคม:** `WHAIR`, `FTREIT`
            *   **โครงสร้างพื้นฐาน:** `DIF` (เสาสัญญาณ), `TFFIF` (ทางด่วน)
            """)
            
        c_grow, c_em = st.columns(2)
        with c_grow:
            st.markdown("##### 🌱 หุ้นเติบโต / หุ้นเล็ก (10%)")
            st.markdown("- **รายตัว:** `JMT`, `FORTH`, `XO`\n- **กองทุน:** `K-STAR`, `SCBSE`")
        with c_em:
            st.markdown("##### 🌍 ตลาดเกิดใหม่ (10%)")
            st.markdown("- **เน้น:** อินเดีย, เวียดนาม, อินโดฯ\n- **กองทุน:** `K-INDX` (อินเดีย), `ASP-VIET`")

        # --- PORTFOLIO SIMULATOR ---
        st.markdown("---")
        st.subheader("🛠️ จำลองพอร์ตหุ้น (Portfolio Simulator)")
        st.caption("จัดพอร์ตตาม Asset Allocation ที่แนะนำ เลือกสินทรัพย์ในแต่ละกลุ่มเพื่อคำนวณผลตอบแทนคาดหวัง")

        # Helper Data for Non-Stock Assets (Estimated Yields & Proxy Prices)
        # Price is dummy 10.0 just for calculating quantity roughly if needed, mostly for amount allocation
        ASSET_PROXY = {
            "BOND": {"price": 10.0, "yield": 0.025}, # 2.5% Yield
            "GLOBAL": {"price": 10.0, "yield": 0.01}, # 1.0% Yield (Growth focus)
            "EM": {"price": 10.0, "yield": 0.02}, # 2.0% Yield
        }

        # Categories mapping to Logic
        # 1. Fixed Income (40%) -> Manual Selection (Mock List)
        # 2. Thai Large (15%) -> SET50 from df
        # 3. Global (15%) -> Manual Selection (Mock List)
        # 4. REITs (10%) -> REITs from df (Filter by name/sector?)
        # 5. Growth (10%) -> Non-SET50 from df
        # 6. Emerging (10%) -> Manual Selection (Mock List)

        sim_budget = st.number_input("เงินลงทุนสำหรับพอร์ตนี้ (บาท)", min_value=1000.0, value=float(capital), step=1000.0)
        
        # --- SELECTION SECTION ---
        st.markdown("#### 1. เลือกสินทรัพย์เข้าพอร์ต")
        
        col_sel1, col_sel2 = st.columns(2)
        
        selected_assets = {} # Store {category: [list of assets]}

        with col_sel1:
            st.markdown("**1. ตราสารหนี้ & พันธบัตร (40%)**")
            opts_bond = ["พันธบัตรรัฐบาล (Gov Bond)", "หุ้นกู้เอกชน (Corp Bond)", "K-FIXED", "SCBFIXED", "TMBABF"]
            selected_assets["Fixed Income"] = st.multiselect("เลือกกองทุน/ตราสารหนี้:", opts_bond, default=["พันธบัตรรัฐบาล (Gov Bond)", "K-FIXED"])
            
            st.markdown("**2. หุ้นไทยขนาดใหญ่ (15%)**")
            # Filter Large Cap (>50B)
            large_cap_list = df[df['marketCap'] > 50_000_000_000]['symbol'].tolist()
            def_large = [x for x in ['ADVANC', 'PTT', 'AOT', 'KBANK', 'CPALL'] if x in large_cap_list]
            selected_assets["Thai Large Cap"] = st.multiselect("เลือกหุ้นขนาดใหญ่ (SET50):", sorted(large_cap_list), default=def_large)
            
            st.markdown("**3. หุ้นต่างประเทศ (15%)**")
            opts_global = ["S&P500 (SPX)", "Nasdaq-100 (NDX)", "ONE-ULTRAP", "SCBNDQ", "K-CHANGE", "TMBGQG"]
            selected_assets["Global Stocks"] = st.multiselect("เลือกกองทุนต่างประเทศ:", opts_global, default=["S&P500 (SPX)", "ONE-ULTRAP"])

        with col_sel2:
            st.markdown("**4. กองทุนอสังหาฯ (10%)**")
            # Filter REITs (Approximate by Name if Sector not clean, or manual list intersection)
            # Let's use a broad filter or manual known list + allow all
            # Try to find Property Fund in df if possible, else use known list
            # For safety, list all but pre-select known REITs
            known_reits = ['CPNREIT', 'WHAIR', 'FTREIT', 'ALLY', 'DIF', 'TFFIF', 'LHHOTEL', 'GVREIT']
            valid_reits = [x for x in known_reits if x in df['symbol'].values]
            selected_assets["REITs"] = st.multiselect("เลือกกองทุนอสังหาฯ (REITs):", sorted(df['symbol'].unique()), default=valid_reits)
            
            st.markdown("**5. หุ้นเติบโต / หุ้นเล็ก (10%)**")
            # Filter Small Cap (<50B)
            small_cap_list = df[df['marketCap'] <= 50_000_000_000]['symbol'].tolist()
            def_small = [x for x in ['JMT', 'FORTH', 'XO', 'SIS', 'COM7'] if x in small_cap_list]
            selected_assets["Growth Stocks"] = st.multiselect("เลือกหุ้นเติบโต/หุ้นเล็ก:", sorted(small_cap_list), default=def_small)
            
            st.markdown("**6. ตลาดเกิดใหม่ (10%)**")
            opts_em = ["Vietnam ETF", "India ETF", "China Tech", "K-INDX", "ASP-VIET", "E1VFVN3001"]
            selected_assets["Emerging Markets"] = st.multiselect("เลือกกองทุนตลาดเกิดใหม่:", opts_em, default=["Vietnam ETF", "K-INDX"])

        # --- CALCULATION ---
        # Allocation Rules
        alloc_rules = {
            "Fixed Income": 0.40,
            "Thai Large Cap": 0.15,
            "Global Stocks": 0.15,
            "REITs": 0.10,
            "Growth Stocks": 0.10,
            "Emerging Markets": 0.10
        }
        
        sim_rows = []
        
        for cat, pct in alloc_rules.items():
            cat_budget = sim_budget * pct
            picks = selected_assets.get(cat, [])
            
            if picks:
                budget_per_asset = cat_budget / len(picks)
                for asset in picks:
                    # Determine Price & Yield
                    price = 0
                    div_yield = 0
                    
                    # Check if it's a real stock in df
                    if asset in df['symbol'].values:
                        row = df[df['symbol'] == asset].iloc[0]
                        price = row.get('price', 0)
                        
                        # Try to get yield from multiple sources
                        div_yield = 0
                        
                        # 1. Try explicit dividendYield
                        y_val = row.get('dividendYield', 0)
                        if pd.notnull(y_val) and y_val > 0:
                            div_yield = y_val
                        
                        # 2. If 0, try dividendRate / price
                        if div_yield == 0 and price > 0:
                            d_rate = row.get('dividendRate', 0)
                            if pd.notnull(d_rate) and d_rate > 0:
                                div_yield = d_rate / price
                    else:
                        # Fallback to Proxy
                        if cat == "Fixed Income":
                            price = ASSET_PROXY["BOND"]["price"]
                            div_yield = ASSET_PROXY["BOND"]["yield"]
                        elif cat == "Global Stocks":
                            price = ASSET_PROXY["GLOBAL"]["price"]
                            div_yield = ASSET_PROXY["GLOBAL"]["yield"]
                        elif cat == "Emerging Markets":
                            price = ASSET_PROXY["EM"]["price"]
                            div_yield = ASSET_PROXY["EM"]["yield"]
                        else:
                             # Default fallback
                            price = 10.0
                            div_yield = 0.0
                    
                    qty = int(budget_per_asset / price) if price > 0 else 0
                    actual_invest = qty * price
                    div_amt = actual_invest * div_yield
                    
                    sim_rows.append({
                        "หมวดหมู่ (Category)": cat,
                        "ชื่อ (Asset)": asset,
                        "จำนวนเงิน (Invested)": actual_invest,
                        "จำนวนหุ้น (Qty)": qty,
                        "%ปันผล (Yield)": div_yield * 100,
                        "ปันผล (บาท)": div_amt
                    })
        
        if sim_rows:
            st.markdown("#### 2. ตารางสรุปพอร์ตโฟลิโอ (Portfolio Summary)")
            df_sim_final = pd.DataFrame(sim_rows)
            
            # Show DataFrame
            st.dataframe(
                df_sim_final.style.format({
                    'จำนวนเงิน (Invested)': '{:,.2f}',
                    'จำนวนหุ้น (Qty)': '{:,}',
                    '%ปันผล (Yield)': '{:.2f}%',
                    'ปันผล (บาท)': '{:,.2f}'
                }),
                use_container_width=True,
                hide_index=True
            )
            
            # Summary Metrics
            total_inv = df_sim_final['จำนวนเงิน (Invested)'].sum()
            total_div = df_sim_final['ปันผล (บาท)'].sum()
            avg_yield_port = (total_div / total_inv * 100) if total_inv > 0 else 0
            
            m1, m2, m3 = st.columns(3)
            m1.metric("มูลค่าพอร์ตคาดการณ์", f"{total_inv:,.0f} บาท")
            m2.metric("เงินปันผลรายปี (โดยประมาณ)", f"{total_div:,.2f} บาท")
            m3.metric("อัตราผลตอบแทนเฉลี่ย (Yield)", f"{avg_yield_port:.2f}%")
            
            st.caption("*หมายเหตุ: ข้อมูลหุ้นไทยอ้างอิงราคาล่าสุด | กองทุนและตราสารหนี้ใช้ราคาและผลตอบแทนสมมติเพื่อการคำนวณเท่านั้น")

elif page == "พอร์ตของฉัน (My Portfolio)":
    st.title("🎒 พอร์ตของฉัน (My Portfolio)")
    st.markdown("บันทึกการซื้อขายและติดตามผลกำไรขาดทุนของพอร์ตโฟลิโอ")
    
    # 1. Add Transaction Form
    with st.expander("➕ เพิ่มรายการซื้อ/ขาย (Add Transaction)", expanded=False):
        t_col1, t_col2, t_col3, t_col4, t_col5 = st.columns(5)
        with t_col1:
            t_open_action = st.selectbox("ทำรายการ", ["Buy", "Sell"])
        with t_col2:
            t_symbol = st.selectbox("หุ้น (Symbol)", SET100_TICKERS)
        with t_col3:
            t_date = st.date_input("วันที่ (Date)")
        with t_col4:
            t_price = st.number_input("ราคา (Price)", min_value=0.01, step=0.05)
        with t_col5:
            t_qty = st.number_input("จำนวน (Qty)", min_value=100, step=100)
            
        if st.button("บันทึกรายการ"):
            utils.save_transaction(t_symbol, t_date, t_price, t_qty, t_open_action)
            st.success(f"บันทึก {t_open_action} {t_symbol} เรียบร้อย!")
            st.rerun()

    # 2. Portfolio View
    # Create price map from loaded df
    if not df.empty:
        price_map = df.set_index('symbol')['price'].to_dict()
    else:
        price_map = {}
        
    port_df, port_val, cost_val = utils.get_portfolio_summary(price_map)
    
    if not port_df.empty:
        # Metrics
        m1, m2, m3 = st.columns(3)
        unrealized_pl = port_val - cost_val
        pl_pct = (unrealized_pl / cost_val * 100) if cost_val > 0 else 0
        
        m1.metric("มูลค่าพอร์ตปัจจุบัน", f"{port_val:,.2f} บาท")
        m2.metric("ทุนรวม", f"{cost_val:,.2f} บาท")
        m3.metric("กำไร/ขาดทุน (Unrealized)", f"{unrealized_pl:,.2f} บาท", f"{pl_pct:.2f}%")
        
        st.subheader("📜 รายการถือครอง (Current Holdings)")
        # Show specific columns
        display_port = port_df[['Symbol', 'Qty', 'Avg Price', 'Market Price', 'Cost Value', 'Market Value', 'P/L %']]
        st.dataframe(display_port.style.format({
            'Qty': '{:,.0f}',
            'Avg Price': '{:,.2f}',
            'Market Price': '{:,.2f}',
            'Cost Value': '{:,.2f}',
            'Market Value': '{:,.2f}',
            'P/L %': '{:+.2f}%'
        }))
        
        # Pie Chart
        st.subheader("🍰 สัดส่วนพอร์ต (Allocation)")
        fig_port = px.pie(port_df, values='Market Value', names='Symbol', title='Portfolio Allocation by Value', hole=0.4)
        st.plotly_chart(fig_port)
    else:
        st.info("ยังไม่มีข้อมูลในพอร์ต กรุณาเพิ่มรายการซื้อขาย")

elif page == "จำลองการออมหุ้น (DCA Backtester)":
    st.title("⏳ จำลองการออมหุ้น (DCA Backtester)")
    st.markdown("ทดสอบผลตอบแทนย้อนหลัง หากเราลงทุนแบบ Dollar Cost Average (DCA) อย่างมีวินัย")
    
    col_d1, col_d2 = st.columns(2)
    
    with col_d1:
        dca_ticker = st.selectbox("เลือกหุ้นที่จะออม", SET100_TICKERS, index=SET100_TICKERS.index('CPALL') if 'CPALL' in SET100_TICKERS else 0)
        dca_amount = st.number_input("เงินออมต่อเดือน (บาท)", value=5000, step=1000)
    
    with col_d2:
        dca_years = st.slider("ระยะเวลาลงทุน (ปี)", 1, 10, 5)
        dca_day = st.slider("วันที่ลงทุนของทุกเดือน", 1, 28, 25)
        
    if st.button("เริ่มการจำลอง (Run Simulation)"):
        with st.spinner("กำลังคำนวณผลตอบแทนย้อนหลัง..."):
            ledger, total_inv, final_val, prof_pct = utils.calculate_dca_simulation(dca_ticker, dca_amount, dca_years, dca_day)
            
            if not ledger.empty:
                st.success("การคำนวณเสร็จสิ้น!")
                
                # Metrics
                r1, r2, r3 = st.columns(3)
                r1.metric("เงินต้นรวม (Total Invested)", f"{total_inv:,.2f} บาท")
                r2.metric("มูลค่าพอร์ตปลายทาง", f"{final_val:,.2f} บาท")
                r3.metric("กำไร/ขาดทุน (%)", f"{prof_pct:+.2f}%", delta_color="normal")
                
                # Chart
                st.subheader("📈 การเติบโตของพอร์ต DCA")
                fig_dca = go.Figure()
                fig_dca.add_trace(go.Scatter(x=ledger['Date'], y=ledger['Value'], fill='tozeroy', name='มูลค่าพอร์ต (Portfolio Value)', line=dict(color='#10b981')))
                fig_dca.add_trace(go.Scatter(x=ledger['Date'], y=ledger['Invested'], name='เงินต้นสะสม (Invested)', line=dict(color='#6b7280', dash='dash')))
                fig_dca.update_layout(title=f"DCA Simulation for {dca_ticker} ({dca_years} Years)", hovermode="x unified")
                st.plotly_chart(fig_dca, use_container_width=True)
                
                # Data Table
                with st.expander("ดูตารางข้อมูลละเอียด (Detailed Ledger)"):
                    st.dataframe(ledger.style.format({'Invested': '{:,.2f}', 'Value': '{:,.2f}', 'Cost': '{:,.2f}'}))
            else:
                st.error("ไม่สามารถดึงข้อมูลย้อนหลังได้ หรือข้อมูลไม่เพียงพอ")
            
elif page == "ตั้งค่า":
    st.title("⚙️ ตั้งค่า (Settings)")
    
    st.subheader("จัดการรายชื่อหุ้น (SET100)")
    st.markdown("เพิ่ม/ลด รายชื่อหุ้นที่ต้องการสแกน (คั่นด้วยเครื่องหมายจุลภาค , หรือขึ้นบรรทัดใหม่)")
    
    current_tickers = ", ".join(SET100_TICKERS)
    new_tickers_text = st.text_area("รายชื่อหุ้น (Ticker Symbols)", value=current_tickers, height=300)
    
    if st.button("บันทึกรายชื่อ"):
        # Process input
        raw_tickers = new_tickers_text.replace("\n", ",").split(",")
        clean_tickers = [t.strip().upper() for t in raw_tickers if t.strip()]
        
        # Save to file
        utils.save_tickers(clean_tickers)
        st.success(f"บันทึกเรียบร้อย! มีหุ้นทั้งหมด {len(clean_tickers)} ตัว (กรุณารีโหลดหน้าเว็บใหม่)")
        
        # Clear cache so new tickers are used next time
        st.cache_data.clear()

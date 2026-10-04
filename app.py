import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# 1. ページ基本設定（一番最初に実行）
st.set_page_config(
    page_title="株式自動スクリーニングダッシュボード",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📈 株式自動スクリーニングダッシュボード")
st.caption("サイドバーで検索条件を設定し、「スクリーニング実行」ボタンを押してください。")

# 2. 監視対象銘柄リスト
DEFAULT_TICKERS = [
    "7203.T",  # トヨタ自動車
    "8306.T",  # 三菱UFJ
    "9432.T",  # NTT
    "8058.T",  # 三菱商事
    "8591.T",  # オリックス
    "6758.T",  # ソニーグループ
    "9984.T",  # ソフトバンクグループ
    "6861.T",  # キーエンス
    "AAPL",    # Apple
    "MSFT",    # Microsoft
    "NVDA",    # NVIDIA
]

# 3. 安全なデータ取得関数
@st.cache_data(ttl=3600)
def fetch_stock_data(tickers):
    results = []
    progress_text = "株価データを取得中..."
    my_bar = st.progress(0, text=progress_text)
    
    for idx, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            # fast_info を使用して高速取得
            price = stock.fast_info.get("lastPrice") or stock.fast_info.get("previousClose")
            
            info = stock.info
            per = info.get("forwardPE") or info.get("trailingPE")
            pbr = info.get("priceToBook")
            div_yield = info.get("dividendYield", 0)
            if div_yield:
                div_yield *= 100
            
            market_cap = (info.get("marketCap") or 0) / 1e8
            name = info.get("shortName", ticker)
            sector = info.get("sector", "その他")

            if price:
                results.append({
                    "コード": ticker,
                    "銘柄名": name,
                    "セクター": sector,
                    "現在値": round(price, 2) if price else None,
                    "PER(倍)": round(per, 2) if per else None,
                    "PBR(倍)": round(pbr, 2) if pbr else None,
                    "配当利回り(%)": round(div_yield, 2) if div_yield else 0.0,
                    "時価総額(億円)": round(market_cap, 1) if market_cap else 0.0
                })
        except Exception as e:
            st.warning(f"{ticker} のデータ取得にスキップされました: {e}")
        
        my_bar.progress((idx + 1) / len(tickers), text=f"データ取得中 ({idx+1}/{len(tickers)}): {ticker}")
        
    my_bar.empty()
    return pd.DataFrame(results)

# 4. サイドバー（設定パネル）
st.sidebar.header("🔍 スクリーニング条件")

per_max = st.sidebar.slider("PER（最大倍率）", min_value=1.0, max_value=50.0, value=25.0, step=0.5)
pbr_max = st.sidebar.slider("PBR（最大倍率）", min_value=0.1, max_value=10.0, value=3.0, step=0.1)
div_min = st.sidebar.slider("最小配当利回り (%)", min_value=0.0, max_value=10.0, value=1.5, step=0.1)

run_button = st.sidebar.button("🚀 スクリーニング実行", type="primary")

# 5. メイン表示エリア
if run_button or "df_data" in st.session_state:
    if run_button:
        with st.spinner("最新データを取得しています..."):
            st.session_state["df_data"] = fetch_stock_data(DEFAULT_TICKERS)
    
    df_raw = st.session_state.get("df_data", pd.DataFrame())

    if not df_raw.empty:
        # フィルター処理（None対策付き）
        df_filtered = df_raw.copy()
        
        if per_max is not None:
            df_filtered = df_filtered[(df_filtered["PER(倍)"].isna()) | (df_filtered["PER(倍)"] <= per_max)]
        if pbr_max is not None:
            df_filtered = df_filtered[(df_filtered["PBR(倍)"].isna()) | (df_filtered["PBR(倍)"] <= pbr_max)]
        if div_min is not None:
            df_filtered = df_filtered[df_filtered["配当利回り(%)"] >= div_min]

        st.subheader(f"📊 該当銘柄リスト ({len(df_filtered)} / {len(df_raw)} 件)")

        tab1, tab2 = st.tabs(["銘柄一覧表", "相関チャート"])

        with tab1:
            st.dataframe(df_filtered, use_container_width=True, hide_index=True)
            csv_data = df_filtered.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 CSVダウンロード", csv_data, "stocks.csv", "text/csv")

        with tab2:
            if not df_filtered.empty:
                fig = px.scatter(
                    df_filtered.dropna(subset=["PER(倍)", "配当利回り(%)"]),
                    x="PER(倍)",
                    y="配当利回り(%)",
                    size="時価総額(億円)",
                    color="セクター",
                    hover_name="銘柄名",
                    title="PER vs 配当利回り"
                )
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("データを取得できませんでした。もう一度実行してください。")
else:
    st.info("👈 左側のサイドバーで条件を設定し、「🚀 スクリーニング実行」ボタンを押してください。")

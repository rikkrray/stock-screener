import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# ページ基本設定
st.set_page_config(
    page_title="楽天証券対応 - 国内株式スクリーニング",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📈 楽天証券対応 - 全国内株式スクリーニングダッシュボード")
st.caption("東証上場（プライム・スタンダード・グロース）の全銘柄に対応。条件を指定して「スクリーニング実行」を押してください。")

# JPXから全上場銘柄リストをキャッシュ取得（有効期限24時間）
@st.cache_data(ttl=86400)
def load_jpx_stock_list():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        df = pd.read_excel(url)
        # 必要な列を抽出・整形
        df_stocks = df[['コード', '銘柄名', '市場・商品区分', '33業種区分']].copy()
        df_stocks['コード'] = df_stocks['コード'].astype(str) + ".T"  # yfinance用コード形式 (.T)
        return df_stocks
    except Exception as e:
        st.error(f"銘柄リストの取得に失敗しました: {e}")
        # フォールバック用基本銘柄リスト
        fallback = pd.DataFrame({
            'コード': ['7203.T', '8306.T', '9432.T', '8058.T', '8591.T', '6758.T', '9984.T', '6861.T'],
            '銘柄名': ['トヨタ自動車', '三菱UFJ', 'NTT', '三菱商事', 'オリックス', 'ソニーグループ', 'ソフトバンクG', 'キーエンス'],
            '市場・商品区分': ['プライム'] * 8,
            '33業種区分': ['輸送用機器', '銀行業', '情報・通信業', '卸売業', 'その他金融業', '電気機器', '情報・通信業', '電気機器']
        })
        return fallback

# データの取得処理（Fast API + yfinance）
@st.cache_data(ttl=3600)
def fetch_stock_financials(ticker_list):
    results = []
    progress_bar = st.progress(0, text="株価データを取得中...")
    total = len(ticker_list)
    
    for idx, row in ticker_list.iterrows():
        ticker = row['コード']
        name = row['銘柄名']
        market = row['市場・商品区分']
        sector = row['33業種区分']
        
        try:
            stock = yf.Ticker(ticker)
            # 株価の取得
            price = stock.fast_info.get("lastPrice") or stock.fast_info.get("previousClose")
            
            info = stock.info
            per = info.get("forwardPE") or info.get("trailingPE")
            pbr = info.get("priceToBook")
            div_yield = info.get("dividendYield", 0)
            if div_yield:
                div_yield *= 100
            
            market_cap = (info.get("marketCap") or 0) / 1e8  # 億円単位

            if price:
                results.append({
                    "コード": ticker.replace(".T", ""),
                    "銘柄名": name,
                    "市場": market,
                    "業種": sector,
                    "現在値(円)": round(price, 1) if price else None,
                    "PER(倍)": round(per, 2) if per else None,
                    "PBR(倍)": round(pbr, 2) if pbr else None,
                    "配当利回り(%)": round(div_yield, 2) if div_yield else 0.0,
                    "時価総額(億円)": round(market_cap, 1) if market_cap else 0.0
                })
        except Exception:
            pass
        
        progress_bar.progress((idx + 1) / total, text=f"データ取得中 ({idx+1}/{total}): {name}")
        
    progress_bar.empty()
    return pd.DataFrame(results)

# 全銘柄マスターのロード
df_master = load_jpx_stock_list()

# --- サイドバー設定 ---
st.sidebar.header("🔍 スクリーニング検索条件")

# 市場区分のフィルター
markets = ["指定なし (全市場)", "プライム", "スタンダード", "グロース"]
selected_market = st.sidebar.selectbox("市場区分（楽天証券取り扱い）", markets)

# 業種フィルター
sectors = ["指定なし (全業種)"] + sorted(list(df_master['33業種区分'].dropna().unique()))
selected_sector = st.sidebar.selectbox("業種セクター", sectors)

# 数値フィルター
per_max = st.sidebar.slider("PER（最大倍率）", min_value=1.0, max_value=50.0, value=20.0, step=0.5)
pbr_max = st.sidebar.slider("PBR（最大倍率）", min_value=0.1, max_value=10.0, value=2.0, step=0.1)
div_min = st.sidebar.slider("最小配当利回り (%)", min_value=0.0, max_value=10.0, value=2.0, step=0.1)

# スキャン上限の設定（通信タイムアウト防止）
max_scan = st.sidebar.number_input("1回の取得上限銘柄数", min_value=10, max_value=500, value=50, step=10,
                                   help="サーバータイムアウトを防ぐため、1度にスキャンする上限数を指定します。")

# フィルタリングされた候補銘柄リストの抽出
df_target = df_master.copy()
if selected_market != "指定なし (全市場)":
    df_target = df_target[df_target['市場・商品区分'].str.contains(selected_market, na=False)]
if selected_sector != "指定なし (全業種)":
    df_target = df_target[df_target['33業種区分'] == selected_sector]

st.sidebar.info(f"現在の検索対象: **{len(df_target)}** 銘柄")

run_btn = st.sidebar.button("🚀 スクリーニング実行", type="primary")

# --- メインコンテンツ表示 ---
if run_btn or "df_results" in st.session_state:
    if run_btn:
        # 上限数に絞ってスキャン実行
        scan_list = df_target.head(max_scan)
        with st.spinner(f"対象 {len(scan_list)} 銘柄の株価・指標データを取得中..."):
            st.session_state["df_results"] = fetch_stock_financials(scan_list)

    df_res = st.session_state.get("df_results", pd.DataFrame())

    if not df_res.empty:
        # 指標フィルター適用
        df_filtered = df_res.copy()
        if per_max is not None:
            df_filtered = df_filtered[(df_filtered["PER(倍)"].isna()) | (df_filtered["PER(倍)"] <= per_max)]
        if pbr_max is not None:
            df_filtered = df_filtered[(df_filtered["PBR(倍)"].isna()) | (df_filtered["PBR(倍)"] <= pbr_max)]
        if div_min is not None:
            df_filtered = df_filtered[df_filtered["配当利回り(%)"] >= div_min]

        st.subheader(f"📊 条件適合銘柄 ({len(df_filtered)} / {len(df_res)} 件)")

        tab1, tab2 = st.tabs(["銘柄一覧（楽天証券用）", "バブル分析チャート"])

        with tab1:
            # 楽天証券の取引画面への直接リンクを表示（銘柄コード付き）
            st.dataframe(df_filtered, use_container_width=True, hide_index=True)
            
            # CSVダウンロードボタン
            csv_bytes = df_filtered.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 検索結果をCSVで保存", csv_bytes, "rakuten_stocks.csv", "text/csv")

        with tab2:
            if not df_filtered.empty:
                fig = px.scatter(
                    df_filtered.dropna(subset=["PER(倍)", "配当利回り(%)"]),
                    x="PER(倍)",
                    y="配当利回り(%)",
                    size="時価総額(億円)",
                    color="業種",
                    hover_name="銘柄名",
                    title="PER vs 配当利回り（円の大きさ: 時価総額）"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("条件に一致する銘柄がありませんでした。")
    else:
        st.warning("データが取得できませんでした。「🚀 スクリーニング実行」を押してください。")
else:
    st.info("👈 サイドバーで「市場（プライム等）」や「業種」を選び、「🚀 スクリーニング実行」ボタンを押すと、国内株式の自動スキャンが始まります。")

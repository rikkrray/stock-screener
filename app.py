import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import requests
from bs4 import BeautifulSoup
import io

# 1. ページ基本設定
st.set_page_config(
    page_title="楽天証券対応 - 国内株式高機能スクリーナー",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSS
st.markdown("""
    <style>
    .stMetric {
        background-color: #f8f9fa;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #e9ecef;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📈 楽天証券対応 - 国内株式プロスクリーナー")
st.caption("東証全銘柄（プライム・スタンダード・グロース）対応。条件を設定してワンクリックでスクリーニングします。")

# 2. JPXから最新の全上場銘柄リストを自動取得
@st.cache_data(ttl=86400)
def load_jpx_stock_list():
    try:
        base_url = "https://www.jpx.co.jp"
        page_url = base_url + "/markets/statistics-equities/misc/01.html"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        
        res = requests.get(page_url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "html.parser")
        
        xls_url = None
        for a in soup.find_all("a"):
            href = a.get("href", "")
            if href.endswith(".xls") or href.endswith(".xlsx"):
                xls_url = base_url + href
                break
                
        if not xls_url:
            raise Exception("エクセルURLが見つかりません。")

        res_xls = requests.get(xls_url, headers=headers, timeout=15)
        res_xls.raise_for_status()
        
        df = pd.read_excel(io.BytesIO(res_xls.content))
        df_stocks = df[['コード', '銘柄名', '市場・商品区分', '33業種区分']].copy()
        df_stocks['コード'] = df_stocks['コード'].astype(str) + ".T"
        
        return df_stocks

    except Exception as e:
        st.error(f"JPX銘柄リストの自動読み込みに失敗しました: {e}")
        fallback = pd.DataFrame({
            'コード': ['7203.T', '8306.T', '9432.T', '8058.T', '8591.T', '6758.T', '9984.T', '6861.T'],
            '銘柄名': ['トヨタ自動車', '三菱UFJ', 'NTT', '三菱商事', 'オリックス', 'ソニーグループ', 'ソフトバンクG', 'キーエンス'],
            '市場・商品区分': ['プライム'] * 8,
            '33業種区分': ['輸送用機器', '銀行業', '情報・通信業', '卸売業', 'その他金融業', '電気機器', '情報・通信業', '電気機器']
        })
        return fallback

# 3. 高速データ取得関数（★ここでエラーの原因を修正しました）
@st.cache_data(ttl=3600)
def fetch_stock_financials(ticker_df):
    results = []
    my_bar = st.progress(0, text="株価データを取得中...")
    total = len(ticker_df)
    
    # enumerate を使い、元の行番号(idx)ではなくループ回数(i)を取得する
    for i, (idx, row) in enumerate(ticker_df.iterrows()):
        ticker = row['コード']
        name = row['銘柄名']
        market = row['市場・商品区分']
        sector = row['33業種区分']
        clean_code = ticker.replace(".T", "")
        
        try:
            stock = yf.Ticker(ticker)
            price = stock.fast_info.get("lastPrice") or stock.fast_info.get("previousClose")
            
            info = stock.info
            per = info.get("forwardPE") or info.get("trailingPE")
            pbr = info.get("priceToBook")
            div_yield = info.get("dividendYield", 0)
            if div_yield:
                div_yield *= 100
            
            market_cap = (info.get("marketCap") or 0) / 1e8

            if price:
                rakuten_url = f"https://www.rakuten-sec.co.jp/web/market/search/quote.html?ric={clean_code}.T"
                
                results.append({
                    "コード": clean_code,
                    "銘柄名": name,
                    "市場": market,
                    "業種": sector,
                    "株価(円)": round(price, 1) if price else None,
                    "PER(倍)": round(per, 2) if per else None,
                    "PBR(倍)": round(pbr, 2) if pbr else None,
                    "配当利回り(%)": round(div_yield, 2) if div_yield else 0.0,
                    "時価総額(億円)": round(market_cap, 1) if market_cap else 0.0,
                    "楽天証券リンク": rakuten_url
                })
        except Exception:
            pass
        
        # (idx + 1) ではなく、正しい進行数である (i + 1) を計算に使用する
        my_bar.progress((i + 1) / total, text=f"データ取得中 ({i+1}/{total}): {name}")
        
    my_bar.empty()
    return pd.DataFrame(results)

# 全銘柄マスターの読み込み
df_master = load_jpx_stock_list()

# --- サイドバー設定エリア ---
st.sidebar.header("🔍 スクリーニング条件")

selected_market = st.sidebar.selectbox(
    "1. ターゲット市場",
    ["指定なし (全市場)", "プライム", "スタンダード", "グロース"]
)

sectors = ["指定なし (全業種)"] + sorted(list(df_master['33業種区分'].dropna().unique()))
selected_sector = st.sidebar.selectbox("2. 業種セクター", sectors)

with st.sidebar.expander("3. 指標条件（PER / PBR / 配当）", expanded=True):
    per_max = st.slider("PER 最大（倍）", min_value=1.0, max_value=50.0, value=20.0, step=0.5)
    pbr_max = st.slider("PBR 最大（倍）", min_value=0.1, max_value=10.0, value=2.0, step=0.1)
    div_min = st.slider("最小配当利回り (%)", min_value=0.0, max_value=10.0, value=2.5, step=0.1)

search_keyword = st.sidebar.text_input("4. 銘柄名・コード直接検索（任意）", placeholder="例: トヨタ, 7203")

max_scan = st.sidebar.number_input(
    "スキャン件数上限", min_value=10, max_value=500, value=50, step=10,
    help="サーバーの応答停止を防ぐため、1度の検索対象数を制限します。"
)

# 絞り込みロジック
df_target = df_master.copy()
if selected_market != "指定なし (全市場)":
    df_target = df_target[df_target['市場・商品区分'].str.contains(selected_market, na=False)]
if selected_sector != "指定なし (全業種)":
    df_target = df_target[df_target['33業種区分'] == selected_sector]
if search_keyword:
    df_target = df_target[
        df_target['銘柄名'].str.contains(search_keyword, na=False) |
        df_target['コード'].str.contains(search_keyword, na=False)
    ]

st.sidebar.caption(f"現在の条件に該当する企業: **{len(df_target)}** 件")
run_btn = st.sidebar.button("🚀 スクリーニング実行", type="primary", use_container_width=True)

# --- メインエリア表示 ---
if run_btn or "df_results" in st.session_state:
    if run_btn:
        scan_list = df_target.head(max_scan)
        if not scan_list.empty:
            with st.spinner(f"対象 {len(scan_list)} 銘柄のリアルタイム株価を取得中..."):
                st.session_state["df_results"] = fetch_stock_financials(scan_list)
        else:
            st.warning("検索条件に該当する銘柄がありませんでした。条件を変更してください。")
            st.session_state["df_results"] = pd.DataFrame()

    df_res = st.session_state.get("df_results", pd.DataFrame())

    if not df_res.empty:
        df_filtered = df_res.copy()
        if per_max is not None:
            df_filtered = df_filtered[(df_filtered["PER(倍)"].isna()) | (df_filtered["PER(倍)"] <= per_max)]
        if pbr_max is not None:
            df_filtered = df_filtered[(df_filtered["PBR(倍)"].isna()) | (df_filtered["PBR(倍)"] <= pbr_max)]
        if div_min is not None:
            df_filtered = df_filtered[df_filtered["配当利回り(%)"] >= div_min]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("抽出銘柄数", f"{len(df_filtered)} / {len(df_res)} 件")
        
        avg_div = df_filtered["配当利回り(%)"].mean() if not df_filtered.empty else 0
        col2.metric("平均配当利回り", f"{avg_div:.2f} %" if not pd.isna(avg_div) else "0 %")
        
        avg_per = df_filtered["PER(倍)"].mean() if not df_filtered.empty else 0
        col3.metric("平均PER", f"{avg_per:.1f} 倍" if not pd.isna(avg_per) else "0 倍")
        
        avg_pbr = df_filtered["PBR(倍)"].mean() if not df_filtered.empty else 0
        col4.metric("平均PBR", f"{avg_pbr:.2f} 倍" if not pd.isna(avg_pbr) else "0 倍")

        st.markdown("---")

        tab1, tab2 = st.tabs(["📋 銘柄リスト (楽天証券リンク付き)", "📊 バブル分析チャート"])

        with tab1:
            st.dataframe(
                df_filtered,
                column_config={
                    "楽天証券リンク": st.column_config.LinkColumn(
                        "楽天証券",
                        display_text="楽天証券で見る ↗"
                    ),
                    "配当利回り(%)": st.column_config.NumberColumn(
                        "配当利回り(%)",
                        format="%.2f %%"
                    ),
                    "時価総額(億円)": st.column_config.NumberColumn(
                        "時価総額(億円)",
                        format="%'.1f 億円"
                    )
                },
                use_container_width=True,
                hide_index=True
            )
            
            csv_data = df_filtered.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 抽出結果をCSVダウンロード", csv_data, "rakuten_stock_screening.csv", "text/csv")

        with tab2:
            if not df_filtered.empty:
                fig = px.scatter(
                    df_filtered.dropna(subset=["PER(倍)", "配当利回り(%)"]),
                    x="PER(倍)",
                    y="配当利回り(%)",
                    size="時価総額(億円)",
                    color="業種",
                    hover_name="銘柄名",
                    title="PER vs 配当利回り 分布図（円の大きさ: 時価総額）",
                    labels={"PER(倍)": "PER (倍) [低いほど割安]", "配当利回り(%)": "配当利回り (%) [高いほどお得]"}
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("条件に一致する銘柄はありませんでした。サイドバーの条件をゆるめてみてください。")
    else:
        st.write("") # データが空の場合はメッセージを抑制
else:
    st.info("👈 左側のサイドバーで条件（市場・業種・指標など）を設定し、「🚀 スクリーニング実行」を押してください。")

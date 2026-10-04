import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import requests
from bs4 import BeautifulSoup
import io

# 1. ページ基本設定
st.set_page_config(
    page_title="楽天証券対応 - 国内株式プロスクリーナー",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 🎨 カスタムCSS (触りたくなるモダンUI化)
# ==========================================
st.markdown("""
    <style>
    /* メトリックカード（KPI）の立体化とホバーアニメーション */
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #f0f2f6;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        transition: all 0.3s ease;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        border-color: #ff4b4b;
    }
    /* プライマリボタンのリッチ化（グラデーションとシャドウ） */
    div.stButton > button:first-child {
        background: linear-gradient(135deg, #ff4b4b 0%, #d40000 100%);
        color: white;
        border-radius: 8px;
        border: none;
        box-shadow: 0 4px 10px rgba(212, 0, 0, 0.3);
        font-weight: bold;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
    }
    div.stButton > button:first-child:hover {
        transform: scale(1.02);
        box-shadow: 0 6px 15px rgba(212, 0, 0, 0.5);
    }
    /* ヘッダー周りの余白調整 */
    .main .block-container {
        padding-top: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

# ヘッダーデザイン
st.title("💎 楽天証券対応 株式スクリーナー")
st.markdown("**あなただけの「お宝銘柄」を発掘しましょう。** 条件を設定してボタンを押すだけです。")
st.divider()

# 2. JPXから全上場銘柄リストを自動取得
@st.cache_data(ttl=86400)
def load_jpx_stock_list():
    try:
        base_url = "https://www.jpx.co.jp"
        page_url = base_url + "/markets/statistics-equities/misc/01.html"
        headers = {"User-Agent": "Mozilla/5.0"}
        
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
            raise Exception("URLが見つかりません。")

        res_xls = requests.get(xls_url, headers=headers, timeout=15)
        res_xls.raise_for_status()
        
        df = pd.read_excel(io.BytesIO(res_xls.content))
        df_stocks = df[['コード', '銘柄名', '市場・商品区分', '33業種区分']].copy()
        df_stocks['コード'] = df_stocks['コード'].astype(str) + ".T"
        return df_stocks

    except Exception as e:
        st.error(f"JPX銘柄リスト自動取得エラー: {e}")
        return pd.DataFrame({
            'コード': ['7203.T', '8306.T', '9432.T', '8058.T', '8591.T'],
            '銘柄名': ['トヨタ自動車', '三菱UFJ', 'NTT', '三菱商事', 'オリックス'],
            '市場・商品区分': ['プライム'] * 5,
            '33業種区分': ['輸送用機器', '銀行業', '情報・通信業', '卸売業', 'その他金融業']
        })

# ==========================================
# 🌟 お宝度（スコア）判定ロジック
# ==========================================
def calculate_score(per, div):
    score = 0
    if per is not None and per > 0 and per < 15:
        score += 1
    if per is not None and per > 0 and per < 10:
        score += 1
    if div is not None and div >= 3.5:
        score += 1
    if div is not None and div >= 4.5:
        score += 1
    
    if score >= 4: return "⭐⭐⭐ 激アツ"
    elif score == 3: return "⭐⭐ 有望"
    elif score == 2: return "⭐ 候補"
    else: return "-"

# 3. 高速データ取得関数
@st.cache_data(ttl=3600)
def fetch_stock_financials(ticker_df):
    results = []
    my_bar = st.progress(0, text="✨ 株価データを高速フェッチ中...")
    total = len(ticker_df)
    
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
            div = info.get("dividendYield", 0)
            if div: div *= 100
            
            market_cap = (info.get("marketCap") or 0) / 1e8

            if price:
                rakuten_url = f"https://www.rakuten-sec.co.jp/web/market/search/quote.html?ric={clean_code}.T"
                score_stars = calculate_score(per, div)
                
                results.append({
                    "お宝度": score_stars,
                    "コード": clean_code,
                    "銘柄名": name,
                    "業種": sector,
                    "株価(円)": round(price, 1),
                    "PER(倍)": round(per, 2) if per else None,
                    "PBR(倍)": round(pbr, 2) if pbr else None,
                    "配当利回り(%)": round(div, 2) if div else 0.0,
                    "時価総額(億円)": round(market_cap, 1) if market_cap else 0.0,
                    "楽天証券リンク": rakuten_url
                })
        except Exception:
            pass
        
        my_bar.progress((i + 1) / total, text=f"データ取得中 ({i+1}/{total}): {name}")
        
    my_bar.empty()
    return pd.DataFrame(results)

df_master = load_jpx_stock_list()

# ==========================================
# 🎛️ サイドバー (美しく整理されたUI)
# ==========================================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/bullish.png", width=60)
    st.header("条件フィルター")
    
    selected_market = st.selectbox("🎯 ターゲット市場", ["指定なし (全市場)", "プライム", "スタンダード", "グロース"])
    
    sectors = ["指定なし (全業種)"] + sorted(list(df_master['33業種区分'].dropna().unique()))
    selected_sector = st.selectbox("🏢 業種セクター", sectors)

    with st.expander("📊 財務・指標プロパティ", expanded=True):
        per_max = st.slider("PER 最大（割安度）", 1.0, 50.0, 15.0, 0.5)
        pbr_max = st.slider("PBR 最大", 0.1, 10.0, 1.5, 0.1)
        div_min = st.slider("配当利回り 最小 (%)", 0.0, 10.0, 3.5, 0.1)

    search_keyword = st.text_input("🔎 銘柄名・コード直接検索", placeholder="例: 7203")
    max_scan = st.number_input("⚡ スキャン上限数", 10, 500, 50, 10, help="API負荷軽減のための上限数")

    st.markdown("<br>", unsafe_allow_html=True)
    run_btn = st.button("🚀 スクリーニングを実行する", use_container_width=True)

# 絞り込み
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

# ==========================================
# 🖥️ メインコンテンツ表示エリア
# ==========================================
if run_btn or "df_results" in st.session_state:
    if run_btn:
        scan_list = df_target.head(max_scan)
        if not scan_list.empty:
            with st.spinner("データを分析しています..."):
                st.session_state["df_results"] = fetch_stock_financials(scan_list)
                st.toast('スクリーニングが完了しました！', icon='🎉') # 成功ポップアップ
        else:
            st.warning("条件に該当する銘柄が見つかりません。")
            st.session_state["df_results"] = pd.DataFrame()

    df_res = st.session_state.get("df_results", pd.DataFrame())

    if not df_res.empty:
        # 指標フィルタ適用
        df_filtered = df_res.copy()
        if per_max: df_filtered = df_filtered[(df_filtered["PER(倍)"].isna()) | (df_filtered["PER(倍)"] <= per_max)]
        if pbr_max: df_filtered = df_filtered[(df_filtered["PBR(倍)"].isna()) | (df_filtered["PBR(倍)"] <= pbr_max)]
        if div_min: df_filtered = df_filtered[df_filtered["配当利回り(%)"] >= div_min]

        # 1. 浮き上がるKPIカード
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📌 抽出銘柄数", f"{len(df_filtered)} 件")
        
        avg_div = df_filtered["配当利回り(%)"].mean() if not df_filtered.empty else 0
        col2.metric("💰 平均配当利回り", f"{avg_div:.2f} %")
        
        avg_per = df_filtered["PER(倍)"].mean() if not df_filtered.empty else 0
        col3.metric("📉 平均PER", f"{avg_per:.1f} 倍")
        
        avg_pbr = df_filtered["PBR(倍)"].mean() if not df_filtered.empty else 0
        col4.metric("🏢 平均PBR", f"{avg_pbr:.2f} 倍")

        st.markdown("<br>", unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["📋 インタラクティブリスト", "📊 ビジュアルマッピング"])

        with tab1:
            st.markdown("##### 🔍 抽出結果 (列のクリックで並び替えが可能です)")
            
            # ビジュアルプログレスバーを適用したリッチなテーブル表示
            st.dataframe(
                df_filtered,
                column_config={
                    "お宝度": st.column_config.TextColumn("お宝度", width="small"),
                    "楽天証券リンク": st.column_config.LinkColumn("楽天証券", display_text="表示する ↗"),
                    "配当利回り(%)": st.column_config.ProgressColumn(
                        "配当利回り(%)",
                        help="配当利回りの高さをバーで視覚化",
                        format="%.2f %%",
                        min_value=0.0,
                        max_value=8.0,
                    ),
                    "時価総額(億円)": st.column_config.NumberColumn("時価総額(億円)", format="%'.1f 億円")
                },
                use_container_width=True,
                hide_index=True,
                height=400
            )

        with tab2:
            if not df_filtered.empty:
                st.markdown("##### 🌐 PER vs 配当利回り ポジショニングマップ")
                fig = px.scatter(
                    df_filtered.dropna(subset=["PER(倍)", "配当利回り(%)"]),
                    x="PER(倍)",
                    y="配当利回り(%)",
                    size="時価総額(億円)",
                    color="業種",
                    hover_name="銘柄名",
                    hover_data={"お宝度": True},
                    template="plotly_white", # よりモダンな白背景テーマ
                )
                # グラフの見た目調整
                fig.update_layout(
                    plot_bgcolor="rgba(240,242,246,0.5)",
                    margin=dict(l=20, r=20, t=30, b=20)
                )
                st.plotly_chart(fig, use_container_width=True)
else:
    st.info("👈 左側のサイドバーで条件を設定し、**「🚀 スクリーニングを実行する」** ボタンを押してください。")

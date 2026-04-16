import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.db import query, latest_date

VERDE = "#0a2300"; MARROM = "#cdaa82"; PALHA = "#fff0dc"
PLOT_BG = "rgba(0,0,0,0)"; GRID = "rgba(255,240,220,0.08)"

st.set_page_config(page_title="Mercado | Bocaina", page_icon="🔍", layout="wide")
st.markdown(f'<h3 style="color:{MARROM}">🔍 Mercado do Dia — Ativos</h3>', unsafe_allow_html=True)

# ── Carregar dados ────────────────────────────────────────────────────────────
data_max = latest_date("fato_debentures")

@st.cache_data(ttl=300)
def load_ativos(data_ref: str) -> pd.DataFrame:
    df = query(
        "vw_ativos_enriquecido",
        select="ticker,emissor,setor,grupo_economico,indexador,rating,faixa_rating,"
               "taxa_mtm_pct,sob_pct,cdi_plus_pct,duration_anos,infra,tipo_debenture,"
               "vencimento,status_call,faixa_duration",
        filters={"data_ref": f"eq.{data_ref}"},
        order="sob_pct.desc.nullslast",
    )
    for c in ["taxa_mtm_pct", "sob_pct", "cdi_plus_pct", "duration_anos"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

df_all = load_ativos(data_max)
if df_all.empty:
    st.error("Sem dados."); st.stop()

# ── Sidebar: filtros ──────────────────────────────────────────────────────────
st.sidebar.markdown(f'<b style="color:{MARROM}">Filtros</b>', unsafe_allow_html=True)
st.sidebar.caption(f"Ref: {data_max}")

idx_opts  = ["Todos"] + sorted(df_all["indexador"].dropna().unique())
set_opts  = ["Todos"] + sorted(df_all["setor"].dropna().unique())
rat_opts  = ["Todos"] + sorted(df_all["faixa_rating"].dropna().unique())
dur_opts  = ["Todos"] + sorted(df_all["faixa_duration"].dropna().unique())

idx_sel  = st.sidebar.selectbox("Indexador", idx_opts)
set_sel  = st.sidebar.selectbox("Setor", set_opts)
rat_sel  = st.sidebar.selectbox("Rating", rat_opts)
dur_sel  = st.sidebar.selectbox("Duration", dur_opts)
infra_sel = st.sidebar.checkbox("Apenas Infra (incentivadas)")

df = df_all.copy()
if idx_sel  != "Todos": df = df[df["indexador"]     == idx_sel]
if set_sel  != "Todos": df = df[df["setor"]          == set_sel]
if rat_sel  != "Todos": df = df[df["faixa_rating"]   == rat_sel]
if dur_sel  != "Todos": df = df[df["faixa_duration"] == dur_sel]
if infra_sel:           df = df[df["infra"] == True]

# ── KPIs ─────────────────────────────────────────────────────────────────────
df_ipca = df[df["indexador"] == "IPCA +"]
df_cdi  = df[df["indexador"] == "CDI +"]

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total ativos",    len(df))
k2.metric("Ativos IPCA+",    len(df_ipca))
k3.metric("Ativos CDI+",     len(df_cdi))
k4.metric(
    "Spread médio IPCA+ s/ NTN-B",
    f"{df_ipca['sob_pct'].dropna().mean():.2f}%" if not df_ipca.empty else "—",
)
k5.metric(
    "CDI+ spread médio",
    f"{df_cdi['cdi_plus_pct'].dropna().mean():.2f}%" if not df_cdi.empty else "—",
)

st.divider()

# ── Scatter duration × spread ─────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📊 Scatter Duration × Spread", "📋 Tabela Completa"])

with tab1:
    col_sc, col_cfg = st.columns([4, 1])
    with col_cfg:
        cor_por = st.radio("Colorir por", ["setor", "faixa_rating", "tipo_debenture"], index=0)
        apenas_ipca = st.checkbox("Só IPCA+", value=True)

    df_sc = df.copy()
    if apenas_ipca:
        df_sc = df_sc[df_sc["indexador"] == "IPCA +"]

    df_sc = df_sc.dropna(subset=["duration_anos", "sob_pct"])

    with col_sc:
        if df_sc.empty:
            st.info("Sem dados suficientes para o scatter.")
        else:
            fig = px.scatter(
                df_sc,
                x="duration_anos", y="sob_pct",
                color=cor_por,
                hover_data=["ticker", "emissor", "rating", "taxa_mtm_pct"],
                labels={
                    "duration_anos": "Duration (anos)",
                    "sob_pct": "Spread s/ NTN-B (%)",
                    cor_por: cor_por.replace("_"," ").title(),
                },
                height=480,
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig.update_traces(marker=dict(size=7, opacity=0.8))
            fig.update_layout(
                paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG,
                font=dict(color=PALHA, size=11),
                xaxis=dict(gridcolor=GRID, zeroline=False),
                yaxis=dict(gridcolor=GRID, zeroline=False),
                legend=dict(font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
                margin=dict(t=20, b=40, l=55, r=20),
            )
            st.plotly_chart(fig, use_container_width=True)

with tab2:
    cols = ["ticker","emissor","setor","indexador","rating","faixa_rating",
            "taxa_mtm_pct","sob_pct","cdi_plus_pct","duration_anos",
            "tipo_debenture","vencimento","status_call"]
    cols = [c for c in cols if c in df.columns]
    df_show = df[cols].copy()
    for c in ["taxa_mtm_pct","sob_pct","cdi_plus_pct","duration_anos"]:
        if c in df_show.columns:
            df_show[c] = pd.to_numeric(df_show[c], errors="coerce").round(4)

    st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ticker":         "Ticker",
            "emissor":        "Emissor",
            "setor":          "Setor",
            "indexador":      "Indexador",
            "rating":         "Rating",
            "faixa_rating":   "Faixa",
            "taxa_mtm_pct":   st.column_config.NumberColumn("IPCA+ Nominal (%)", format="%.4f"),
            "sob_pct":        st.column_config.NumberColumn("Spread s/ NTN-B (%)", format="%.4f"),
            "cdi_plus_pct":   st.column_config.NumberColumn("CDI+ (%)", format="%.4f"),
            "duration_anos":  st.column_config.NumberColumn("Duration (a)", format="%.2f"),
            "tipo_debenture": "Tipo",
            "vencimento":     "Vencimento",
            "status_call":    "Call",
        },
    )

    # Download
    csv = df_show.to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Baixar CSV", csv, f"mercado_{data_max}.csv", "text/csv")

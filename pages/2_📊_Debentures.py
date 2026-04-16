import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.db import query, latest_date

st.set_page_config(page_title="Debêntures", page_icon="📊", layout="wide")
st.title("📊 Debêntures — Ativos Enriquecidos")

# ── Data de referência ───────────────────────────────────────────────────────
data_max = latest_date("vw_ativos_enriquecido")
st.sidebar.subheader("Filtros")
data_sel = st.sidebar.date_input("Data de referência", value=pd.to_datetime(data_max))

# ── Carregar dados ───────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_debentures(data_ref: str) -> pd.DataFrame:
    df = query(
        "vw_ativos_enriquecido",
        select=(
            "data_ref,ticker,emissor,vencimento,indexador,curva,"
            "taxa_mtm,taxa_mtm_pct,sob,sob_pct,cdi_plus,cdi_plus_pct,"
            "pu,duration,duration_anos,setor,grupo_economico,"
            "rating,faixa_rating,infra,tipo_debenture,"
            "status_call,be,be_pct,faixa_duration"
        ),
        filters={"data_ref": f"eq.{data_ref}"},
        order="sob_pct.desc.nullslast",
    )
    return df.apply(pd.to_numeric, errors="ignore")

df = load_debentures(str(data_sel))

if df.empty:
    st.warning(f"Sem dados para {data_sel}. Tente outra data.")
    st.stop()

st.caption(f"Referência: {data_sel} — {len(df)} ativos")

# ── Filtros laterais ─────────────────────────────────────────────────────────
indexadores = ["Todos"] + sorted(df["indexador"].dropna().unique().tolist())
setores = ["Todos"] + sorted(df["setor"].dropna().unique().tolist())
ratings = ["Todos"] + sorted(df["faixa_rating"].dropna().unique().tolist())

idx_sel = st.sidebar.selectbox("Indexador", indexadores)
set_sel = st.sidebar.selectbox("Setor", setores)
rat_sel = st.sidebar.selectbox("Faixa de Rating", ratings)
infra_sel = st.sidebar.checkbox("Apenas Infraestrutura (debêntures incentivadas)")

df_f = df.copy()
if idx_sel != "Todos":
    df_f = df_f[df_f["indexador"] == idx_sel]
if set_sel != "Todos":
    df_f = df_f[df_f["setor"] == set_sel]
if rat_sel != "Todos":
    df_f = df_f[df_f["faixa_rating"] == rat_sel]
if infra_sel:
    df_f = df_f[df_f["infra"] == True]

st.subheader(f"Ativos ({len(df_f)} encontrados)")

# ── KPIs ─────────────────────────────────────────────────────────────────────
df_ipca = df_f[df_f["indexador"] == "IPCA +"]
df_cdi = df_f[df_f["indexador"] == "CDI +"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total ativos", len(df_f))
c2.metric("Ativos IPCA+", len(df_ipca))
c3.metric(
    "SOB médio IPCA+",
    f"{df_ipca['sob'].dropna().mean():.4f}%" if not df_ipca.empty else "—",
)
c4.metric(
    "SOB médio CDI+",
    f"{df_cdi['cdi_plus'].dropna().mean():.4f}%" if not df_cdi.empty else "—",
)

st.divider()

# ── Scatter: Duration x SOB ──────────────────────────────────────────────────
st.subheader("Duration × SOB")

df_scatter = df_f.dropna(subset=["duration_anos", "sob_pct"]).copy()
if not df_scatter.empty:
    fig = px.scatter(
        df_scatter,
        x="duration_anos",
        y="sob_pct",
        color="setor",
        size_max=12,
        hover_data=["ticker", "emissor", "rating", "faixa_rating", "indexador"],
        labels={"duration_anos": "Duration (anos)", "sob_pct": "SOB (%)"},
        height=450,
    )
    fig.update_layout(legend=dict(orientation="h", y=-0.3))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Sem dados suficientes para o scatter.")

# ── Boxplot SOB por Setor ────────────────────────────────────────────────────
st.subheader("Distribuição de SOB por Setor")

df_box = df_f.dropna(subset=["sob_pct", "setor"]).copy()
if not df_box.empty:
    fig2 = px.box(
        df_box.sort_values("setor"),
        x="setor",
        y="sob_pct",
        color="faixa_rating",
        labels={"setor": "Setor", "sob_pct": "SOB (%)"},
        height=400,
    )
    fig2.update_layout(legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig2, use_container_width=True)

# ── Tabela de ativos ─────────────────────────────────────────────────────────
st.subheader("Tabela de Ativos")

cols_show = [
    "ticker", "emissor", "setor", "indexador", "rating", "faixa_rating",
    "taxa_mtm_pct", "sob_pct", "cdi_plus_pct", "duration_anos",
    "vencimento", "infra", "status_call",
]
cols_show = [c for c in cols_show if c in df_f.columns]
df_table = df_f[cols_show].copy()

# Formatar colunas numéricas
for col in ["taxa_mtm_pct", "sob_pct", "cdi_plus_pct", "duration_anos"]:
    if col in df_table.columns:
        df_table[col] = pd.to_numeric(df_table[col], errors="coerce").round(4)

st.dataframe(
    df_table,
    use_container_width=True,
    column_config={
        "ticker": "Ticker",
        "emissor": "Emissor",
        "setor": "Setor",
        "indexador": "Indexador",
        "rating": "Rating",
        "faixa_rating": "Faixa Rating",
        "taxa_mtm_pct": st.column_config.NumberColumn("Taxa MTM (%)", format="%.4f"),
        "sob_pct": st.column_config.NumberColumn("SOB (%)", format="%.4f"),
        "cdi_plus_pct": st.column_config.NumberColumn("CDI+ (%)", format="%.4f"),
        "duration_anos": st.column_config.NumberColumn("Duration (anos)", format="%.2f"),
        "vencimento": "Vencimento",
        "infra": st.column_config.CheckboxColumn("Infra"),
        "status_call": "Status Call",
    },
    hide_index=True,
)

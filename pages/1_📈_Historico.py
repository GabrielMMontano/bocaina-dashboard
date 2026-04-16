import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from utils.db import query

VERDE = "#0a2300"; MARROM = "#cdaa82"; PALHA = "#fff0dc"
PLOT_BG = "rgba(0,0,0,0)"; GRID = "rgba(255,240,220,0.08)"

st.set_page_config(page_title="Histórico | Bocaina", page_icon="📈", layout="wide")
st.markdown(f'<h3 style="color:{MARROM}">📈 Série Histórica de Spreads</h3>', unsafe_allow_html=True)
st.caption("5 anos de dados · 2021–2026")

# ── Período ──────────────────────────────────────────────────────────────────
periodo = st.sidebar.radio(
    "Período",
    ["30 dias", "90 dias", "180 dias", "1 ano", "2 anos", "5 anos"],
    index=3,
)
lim = {"30 dias":30,"90 dias":90,"180 dias":180,"1 ano":252,"2 anos":504,"5 anos":9999}[periodo]

@st.cache_data(ttl=300)
def load(lim):
    df = query("vw_series_historico",
        select="data_ref,cdi_sob_pct,cdi_qtd_ativos,ipca_sob_todos_pct,ipca_qtd_todos,"
               "ipca_sob_aaa_aa_pct,ipca_sob_ex_cptm_pct,gap_pct,gap2_pct,"
               "var_dia_sob_todos,var_dia_gap",
        order="data_ref.desc", limit=lim)
    if df.empty or "data_ref" not in df.columns:
        return df
    df["data_ref"] = pd.to_datetime(df["data_ref"])
    num_cols = [c for c in df.columns if c != "data_ref"]
    df[num_cols] = df[num_cols].apply(lambda c: pd.to_numeric(c, errors="coerce"))
    return df.sort_values("data_ref").reset_index(drop=True)

df = load(lim)
if df.empty:
    st.error("Sem dados."); st.stop()

ultimo = df.iloc[-1]

def layout(title="", h=320):
    return dict(
        title=dict(text=title, font=dict(color=MARROM, size=13)),
        paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG,
        font=dict(color=PALHA, size=11),
        xaxis=dict(gridcolor=GRID, showgrid=True, zeroline=False),
        yaxis=dict(gridcolor=GRID, showgrid=True, zeroline=False),
        legend=dict(orientation="h", y=1.15, font=dict(size=10)),
        margin=dict(t=40,b=30,l=55,r=20), height=h,
    )

# ── KPIs ─────────────────────────────────────────────────────────────────────
k1,k2,k3,k4 = st.columns(4)
k1.metric("IPCA+ Nominal",      f"{float(ultimo['ipca_sob_todos_pct']):.2f}%")
k2.metric("Spread s/ NTN-B",    f"{float(ultimo['gap_pct']):.2f}%",
          f"{float(ultimo['var_dia_gap']):+.2f}pp (dia)" if pd.notna(ultimo['var_dia_gap']) else None)
k3.metric("Spread AAA–AA",      f"{float(ultimo['ipca_sob_aaa_aa_pct']):.2f}%")
k4.metric("CDI+ Spread",        f"{float(ultimo['cdi_sob_pct']):.2f}%")
st.divider()

# ── Gráfico 1: IPCA+ Nominal ──────────────────────────────────────────────────
fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df["data_ref"], y=df["ipca_sob_todos_pct"],
    name="IPCA+ Nominal", mode="lines", line=dict(color=MARROM, width=2),
    fill="tozeroy", fillcolor="rgba(205,170,130,0.10)"))
fig1.update_layout(**layout("IPCA+ Nominal — Taxa média do mercado (%)", 300))
st.plotly_chart(fig1, use_container_width=True)

# ── Gráfico 2: Spreads sobre NTN-B ──────────────────────────────────────────
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=df["data_ref"], y=df["gap_pct"],
    name="Spread Todos s/ NTN-B", mode="lines", line=dict(color=PALHA, width=2.5)))
fig2.add_trace(go.Scatter(x=df["data_ref"], y=df["ipca_sob_aaa_aa_pct"],
    name="Spread AAA–AA", mode="lines", line=dict(color=MARROM, width=2, dash="dot")))
fig2.add_trace(go.Scatter(x=df["data_ref"], y=df["ipca_sob_ex_cptm_pct"],
    name="Spread AA–A (ex-CPTM)", mode="lines", line=dict(color="#7ec8a0", width=1.5, dash="dash")))
fig2.update_layout(**layout("Spread s/ NTN-B por Segmento (%)", 350))
st.plotly_chart(fig2, use_container_width=True)

# ── Gráfico 3: CDI+ e N° Ativos ──────────────────────────────────────────────
fig3 = make_subplots(specs=[[{"secondary_y": True}]])
fig3.add_trace(go.Scatter(x=df["data_ref"], y=df["cdi_sob_pct"],
    name="CDI+ Spread", mode="lines", line=dict(color="#7ec8a0", width=2)),
    secondary_y=False)
fig3.add_trace(go.Scatter(x=df["data_ref"], y=df["ipca_qtd_todos"],
    name="N° Ativos IPCA+", mode="lines",
    line=dict(color=MARROM, width=1.5, dash="dot")),
    secondary_y=True)
fig3.update_yaxes(title_text="CDI+ Spread (%)", gridcolor=GRID, color=PALHA, secondary_y=False)
fig3.update_yaxes(title_text="N° Ativos",       gridcolor=GRID, color=PALHA, secondary_y=True)
fig3.update_layout(
    paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG,
    font=dict(color=PALHA, size=11),
    xaxis=dict(gridcolor=GRID, showgrid=True, zeroline=False),
    legend=dict(orientation="h", y=1.15, font=dict(size=10)),
    margin=dict(t=40,b=30,l=55,r=55), height=300,
    title=dict(text="CDI+ Spread e N° Ativos IPCA+", font=dict(color=MARROM, size=13)),
)
st.plotly_chart(fig3, use_container_width=True)

# ── Dados brutos ─────────────────────────────────────────────────────────────
with st.expander("Ver dados brutos"):
    show = df.sort_values("data_ref", ascending=False).copy()
    show["data_ref"] = show["data_ref"].dt.strftime("%d/%m/%Y")
    st.dataframe(show, use_container_width=True, hide_index=True)

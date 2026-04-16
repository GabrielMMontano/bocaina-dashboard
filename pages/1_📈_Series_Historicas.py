import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from utils.db import query

st.set_page_config(page_title="Séries Históricas", page_icon="📈", layout="wide")
st.title("📈 Séries Históricas de Spread")
st.caption("Evolução diária dos spreads de crédito CDI+ e IPCA+")

# ── Filtro de período ────────────────────────────────────────────────────────
periodo = st.sidebar.selectbox(
    "Período",
    ["30 dias", "90 dias", "180 dias", "1 ano", "2 anos", "Tudo"],
    index=2,
)
limite_map = {
    "30 dias": 30, "90 dias": 90, "180 dias": 180,
    "1 ano": 252, "2 anos": 504, "Tudo": 10000,
}
limite = limite_map[periodo]

# ── Dados ────────────────────────────────────────────────────────────────────
df = query(
    "vw_series_historico",
    select=(
        "data_ref,cdi_sob_pct,cdi_qtd_ativos,"
        "ipca_sob_todos_pct,ipca_qtd_todos,"
        "ipca_sob_aaa_aa_pct,ipca_qtd_aaa_aa,"
        "ipca_sob_aa_a_pct,ipca_qtd_aa_a,"
        "ipca_sob_ex_cptm_pct,ipca_qtd_ex_cptm,"
        "gap_pct,gap2_pct,var_dia_sob_todos,var_dia_gap"
    ),
    order="data_ref.desc",
    limit=limite,
)
df = df.apply(pd.to_numeric, errors="ignore")
df["data_ref"] = pd.to_datetime(df["data_ref"])
df = df.sort_values("data_ref")

if df.empty:
    st.error("Sem dados disponíveis.")
    st.stop()

# ── KPIs do último dia ───────────────────────────────────────────────────────
ultimo = df.iloc[-1]
st.subheader(f"Último dia: {ultimo['data_ref'].strftime('%d/%m/%Y')}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("IPCA+ SOB (todos)", f"{float(ultimo['ipca_sob_todos_pct']):.2f}%",
          f"{float(ultimo.get('var_dia_sob_todos', 0)):.2f}pp (dia)")
c2.metric("CDI+ SOB", f"{float(ultimo['cdi_sob_pct']):.2f}%")
c3.metric("Gap (IPCA+ vs NTN-B)", f"{float(ultimo['gap_pct']):.2f}%",
          f"{float(ultimo.get('var_dia_gap', 0)):.2f}pp (dia)")
c4.metric("N° Ativos IPCA+", int(ultimo["ipca_qtd_todos"]))

st.divider()

# ── Gráfico 1: SOB por segmento ──────────────────────────────────────────────
st.subheader("SOB por Segmento (IPCA+)")

fig1 = go.Figure()
fig1.add_trace(go.Scatter(
    x=df["data_ref"], y=df["ipca_sob_todos_pct"],
    name="Todos", mode="lines", line=dict(width=2, color="#1f77b4"),
))
fig1.add_trace(go.Scatter(
    x=df["data_ref"], y=df["ipca_sob_aaa_aa_pct"],
    name="AAA–AA", mode="lines", line=dict(width=2, color="#2ca02c"),
))
fig1.add_trace(go.Scatter(
    x=df["data_ref"], y=df["ipca_sob_aa_a_pct"],
    name="AA–A", mode="lines", line=dict(width=2, color="#ff7f0e"),
))
fig1.add_trace(go.Scatter(
    x=df["data_ref"], y=df["ipca_sob_ex_cptm_pct"],
    name="Ex-CPTM", mode="lines", line=dict(width=2, dash="dot", color="#9467bd"),
))
fig1.update_layout(
    height=380, xaxis_title="Data", yaxis_title="SOB (%)",
    legend=dict(orientation="h", y=1.1),
    margin=dict(t=10, b=40),
)
st.plotly_chart(fig1, use_container_width=True)

# ── Gráfico 2: Gap e CDI+ SOB ────────────────────────────────────────────────
st.subheader("Gap (IPCA+ vs NTN-B) e CDI+ SOB")

fig2 = make_subplots(specs=[[{"secondary_y": True}]])
fig2.add_trace(go.Scatter(
    x=df["data_ref"], y=df["gap_pct"],
    name="Gap", mode="lines", line=dict(width=2, color="#d62728"),
), secondary_y=False)
fig2.add_trace(go.Scatter(
    x=df["data_ref"], y=df["gap2_pct"],
    name="Gap2", mode="lines", line=dict(width=2, dash="dot", color="#e377c2"),
), secondary_y=False)
fig2.add_trace(go.Scatter(
    x=df["data_ref"], y=df["cdi_sob_pct"],
    name="CDI+ SOB", mode="lines", line=dict(width=2, color="#17becf"),
), secondary_y=True)
fig2.update_yaxes(title_text="Gap (%)", secondary_y=False)
fig2.update_yaxes(title_text="CDI+ SOB (%)", secondary_y=True)
fig2.update_layout(
    height=380, xaxis_title="Data",
    legend=dict(orientation="h", y=1.1),
    margin=dict(t=10, b=40),
)
st.plotly_chart(fig2, use_container_width=True)

# ── Gráfico 3: Quantidade de ativos ─────────────────────────────────────────
st.subheader("Quantidade de Ativos")

fig3 = go.Figure()
fig3.add_trace(go.Scatter(
    x=df["data_ref"], y=df["ipca_qtd_todos"],
    name="IPCA+ (todos)", mode="lines", fill="tozeroy",
    line=dict(width=1.5, color="#1f77b4"), fillcolor="rgba(31,119,180,0.15)",
))
fig3.add_trace(go.Scatter(
    x=df["data_ref"], y=df["cdi_qtd_ativos"],
    name="CDI+", mode="lines", fill="tozeroy",
    line=dict(width=1.5, color="#ff7f0e"), fillcolor="rgba(255,127,14,0.15)",
))
fig3.update_layout(
    height=300, xaxis_title="Data", yaxis_title="N° ativos",
    legend=dict(orientation="h", y=1.1),
    margin=dict(t=10, b=40),
)
st.plotly_chart(fig3, use_container_width=True)

# ── Tabela de dados ──────────────────────────────────────────────────────────
with st.expander("Ver dados brutos"):
    df_show = df.sort_values("data_ref", ascending=False).copy()
    df_show["data_ref"] = df_show["data_ref"].dt.strftime("%d/%m/%Y")
    st.dataframe(df_show, use_container_width=True)

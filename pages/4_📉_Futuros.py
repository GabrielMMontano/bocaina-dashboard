import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from utils.db import query, latest_date

st.set_page_config(page_title="Futuros", page_icon="📉", layout="wide")
st.title("📉 Curva de Juros — Futuros DI")
st.caption("DI1 e outros contratos negociados na B3")

# ── Dados ────────────────────────────────────────────────────────────────────
df = query(
    "vw_futuros_curva",
    select="data_ref,tipo_data,contrato,instrumento,vencimento_label,sort_vencimento,ajuste,preco_fechamento,preco_medio,qtd_contratos,volume_financeiro",
    order="data_ref.desc",
)
df = df.apply(pd.to_numeric, errors="ignore")
df["data_ref"] = pd.to_datetime(df["data_ref"])

if df.empty:
    st.error("Sem dados disponíveis.")
    st.stop()

datas = sorted(df["data_ref"].unique(), reverse=True)
contratos = sorted(df["contrato"].dropna().unique().tolist())

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.subheader("Filtros")
data_sel = st.sidebar.selectbox(
    "Data de referência",
    [d.strftime("%Y-%m-%d") for d in datas],
    index=0,
)
contrato_sel = st.sidebar.selectbox("Contrato", contratos, index=0 if "DI1" not in contratos else contratos.index("DI1"))
data_comp = st.sidebar.selectbox(
    "Data comparação (opcional)",
    ["—"] + [d.strftime("%Y-%m-%d") for d in datas[1:]],
    index=0,
)

df_dia = df[
    (df["data_ref"] == pd.to_datetime(data_sel)) &
    (df["contrato"] == contrato_sel)
].sort_values("sort_vencimento")

# Deduplica: mantém o registro de maior volume por vencimento
df_dia = (
    df_dia.sort_values("volume_financeiro", ascending=False)
    .drop_duplicates(subset="vencimento_label", keep="first")
    .sort_values("sort_vencimento")
)

if df_dia.empty:
    st.warning("Sem dados para o filtro selecionado.")
    st.stop()

# ── KPIs ─────────────────────────────────────────────────────────────────────
st.subheader(f"Curva {contrato_sel} — {pd.to_datetime(data_sel).strftime('%d/%m/%Y')}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("N° vértices", len(df_dia))
c2.metric(
    "Ajuste curto (1° vértice)",
    f"{df_dia.iloc[0]['ajuste']:,.0f}" if pd.notna(df_dia.iloc[0]["ajuste"]) else "—",
)
c3.metric(
    "Ajuste longo (último vértice)",
    f"{df_dia.iloc[-1]['ajuste']:,.0f}" if pd.notna(df_dia.iloc[-1]["ajuste"]) else "—",
)
c4.metric(
    "Volume total (R$ mi)",
    f"R$ {df_dia['volume_financeiro'].sum()/1e6:,.0f}M" if df_dia["volume_financeiro"].notna().any() else "—",
)

st.divider()

# ── Curva de ajuste ──────────────────────────────────────────────────────────
st.subheader("Curva de Ajuste (Preço → Taxa implícita)")

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=df_dia["vencimento_label"],
    y=df_dia["ajuste"],
    mode="lines+markers",
    name=pd.to_datetime(data_sel).strftime("%d/%m/%Y"),
    line=dict(width=2.5, color="#1f77b4"),
    marker=dict(size=8),
))

if data_comp != "—":
    df_comp = df[
        (df["data_ref"] == pd.to_datetime(data_comp)) &
        (df["contrato"] == contrato_sel)
    ].sort_values("sort_vencimento")
    df_comp = (
        df_comp.sort_values("volume_financeiro", ascending=False)
        .drop_duplicates(subset="vencimento_label", keep="first")
        .sort_values("sort_vencimento")
    )
    if not df_comp.empty:
        fig.add_trace(go.Scatter(
            x=df_comp["vencimento_label"],
            y=df_comp["ajuste"],
            mode="lines+markers",
            name=pd.to_datetime(data_comp).strftime("%d/%m/%Y"),
            line=dict(width=2, dash="dash", color="#ff7f0e"),
            marker=dict(size=6),
        ))

fig.update_layout(
    height=420,
    xaxis_title="Vencimento",
    yaxis_title="Preço de Ajuste",
    legend=dict(orientation="h", y=1.1),
    margin=dict(t=10, b=60),
)
st.plotly_chart(fig, use_container_width=True)

# ── Liquidez (volume por vértice) ────────────────────────────────────────────
st.subheader("Liquidez por Vértice")

df_liq = df_dia.dropna(subset=["volume_financeiro"])
if not df_liq.empty:
    fig2 = make_subplots(specs=[[{"secondary_y": True}]])
    fig2.add_trace(go.Bar(
        x=df_liq["vencimento_label"],
        y=df_liq["volume_financeiro"] / 1e6,
        name="Volume (R$ mi)",
        marker_color="rgba(31,119,180,0.7)",
    ), secondary_y=False)
    fig2.add_trace(go.Scatter(
        x=df_liq["vencimento_label"],
        y=df_liq["qtd_contratos"],
        name="Qtd Contratos",
        mode="lines+markers",
        line=dict(color="#ff7f0e", width=2),
    ), secondary_y=True)
    fig2.update_yaxes(title_text="Volume (R$ mi)", secondary_y=False)
    fig2.update_yaxes(title_text="Qtd Contratos", secondary_y=True)
    fig2.update_layout(
        height=360,
        xaxis_title="Vencimento",
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=10, b=60),
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Tabela ────────────────────────────────────────────────────────────────────
with st.expander("Ver tabela"):
    df_show = df_dia[["vencimento_label", "instrumento", "ajuste", "preco_fechamento",
                       "preco_medio", "qtd_contratos", "volume_financeiro"]].copy()
    for col in ["ajuste", "preco_fechamento", "preco_medio"]:
        if col in df_show.columns:
            df_show[col] = pd.to_numeric(df_show[col], errors="coerce").round(3)
    df_show["volume_financeiro"] = (
        pd.to_numeric(df_show["volume_financeiro"], errors="coerce") / 1e6
    ).round(1)
    st.dataframe(df_show, use_container_width=True, hide_index=True,
                 column_config={"volume_financeiro": st.column_config.NumberColumn("Volume (R$ mi)", format="%.1f")})

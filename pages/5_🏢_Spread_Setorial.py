import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.db import query, latest_date

st.set_page_config(page_title="Spread Setorial", page_icon="🏢", layout="wide")
st.title("🏢 Spread por Setor")
st.caption("SOB médio por setor e faixa de rating — IPCA+ e CDI+")

# ── Dados ────────────────────────────────────────────────────────────────────
df = query(
    "vw_spread_por_setor",
    select="setor,indexador,faixa_rating,qtd_ativos,sob_medio_pct,sob_min_pct,sob_max_pct,duration_media,data_ref",
    order="data_ref.desc",
)
df = df.apply(pd.to_numeric, errors="ignore")
df["data_ref"] = pd.to_datetime(df["data_ref"])

if df.empty:
    st.error("Sem dados disponíveis.")
    st.stop()

data_max = df["data_ref"].max()
st.sidebar.subheader("Filtros")
data_sel = st.sidebar.selectbox(
    "Data de referência",
    sorted(df["data_ref"].unique(), reverse=True),
    format_func=lambda d: pd.to_datetime(d).strftime("%d/%m/%Y"),
    index=0,
)
indexador_sel = st.sidebar.selectbox(
    "Indexador",
    ["IPCA +", "CDI +", "% CDI", "Todos"],
    index=0,
)

df_dia = df[df["data_ref"] == pd.to_datetime(data_sel)].copy()
if indexador_sel != "Todos":
    df_dia = df_dia[df_dia["indexador"] == indexador_sel]

st.subheader(f"Referência: {pd.to_datetime(data_sel).strftime('%d/%m/%Y')} — {indexador_sel}")

if df_dia.empty:
    st.warning("Sem dados para os filtros selecionados.")
    st.stop()

# ── KPIs ─────────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Setores", df_dia["setor"].nunique())
c2.metric("Total de ativos", int(df_dia["qtd_ativos"].sum()))
c3.metric("SOB médio geral (%)",
          f"{(df_dia['sob_medio_pct'] * df_dia['qtd_ativos']).sum() / df_dia['qtd_ativos'].sum():.2f}%")
c4.metric("Duration média (anos)", f"{df_dia['duration_media'].mean():.2f}")

st.divider()

# ── Heatmap: Setor x Faixa de Rating ────────────────────────────────────────
st.subheader("Heatmap — SOB por Setor × Faixa de Rating")

pivot = df_dia.pivot_table(
    index="setor", columns="faixa_rating", values="sob_medio_pct", aggfunc="mean"
)
if not pivot.empty:
    fig_heat = px.imshow(
        pivot,
        color_continuous_scale="RdYlGn",
        text_auto=".2f",
        aspect="auto",
        labels={"color": "SOB (%)"},
        height=max(300, len(pivot) * 35 + 100),
    )
    fig_heat.update_layout(margin=dict(t=10, b=40))
    st.plotly_chart(fig_heat, use_container_width=True)

# ── Barras: SOB por Setor ────────────────────────────────────────────────────
st.subheader("SOB Médio por Setor (agrupado por rating)")

df_bar = df_dia.sort_values("sob_medio_pct", ascending=False)
fig_bar = px.bar(
    df_bar,
    x="setor",
    y="sob_medio_pct",
    color="faixa_rating",
    barmode="group",
    error_y=df_bar["sob_max_pct"] - df_bar["sob_medio_pct"],
    error_y_minus=df_bar["sob_medio_pct"] - df_bar["sob_min_pct"],
    labels={"setor": "Setor", "sob_medio_pct": "SOB Médio (%)"},
    height=430,
)
fig_bar.update_layout(
    legend=dict(orientation="h", y=1.1),
    margin=dict(t=10, b=80),
)
st.plotly_chart(fig_bar, use_container_width=True)

# ── Bubble: Duration x SOB x Qtd ativos ─────────────────────────────────────
st.subheader("Duration × SOB × Volume de Ativos")

df_bubble = df_dia.dropna(subset=["duration_media", "sob_medio_pct"])
if not df_bubble.empty:
    fig_bub = px.scatter(
        df_bubble,
        x="duration_media",
        y="sob_medio_pct",
        size="qtd_ativos",
        color="setor",
        text="setor",
        hover_data=["faixa_rating", "qtd_ativos", "sob_min_pct", "sob_max_pct"],
        labels={"duration_media": "Duration Média (anos)", "sob_medio_pct": "SOB Médio (%)"},
        height=450,
        size_max=40,
    )
    fig_bub.update_traces(textposition="top center")
    fig_bub.update_layout(showlegend=False, margin=dict(t=10, b=50))
    st.plotly_chart(fig_bub, use_container_width=True)

# ── Tabela ────────────────────────────────────────────────────────────────────
with st.expander("Ver tabela"):
    df_show = df_dia.drop(columns=["data_ref"]).sort_values(
        "sob_medio_pct", ascending=False
    ).copy()
    for col in ["sob_medio_pct", "sob_min_pct", "sob_max_pct", "duration_media"]:
        if col in df_show.columns:
            df_show[col] = pd.to_numeric(df_show[col], errors="coerce").round(4)
    st.dataframe(df_show, use_container_width=True, hide_index=True)

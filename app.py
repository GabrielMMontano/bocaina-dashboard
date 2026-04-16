import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.db import query, latest_date

st.set_page_config(
    page_title="Bocaina | Dashboard Renda Fixa",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Bocaina Capital — Dashboard Renda Fixa")
st.caption("Visão geral do mercado de crédito privado e curvas de juros")

# ── Datas de referência ──────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

with col1:
    data_series = latest_date("vw_series_historico")
    st.metric("Última data (Séries)", data_series)

with col2:
    data_deb = latest_date("vw_ativos_enriquecido")
    st.metric("Última data (Debentures)", data_deb)

with col3:
    data_ntnb = latest_date("vw_ntnb_comparativo")
    st.metric("Última data (NTN-B)", data_ntnb)

with col4:
    data_fut = latest_date("vw_futuros_curva")
    st.metric("Última data (Futuros)", data_fut)

st.divider()

# ── KPIs do dia (Séries) ─────────────────────────────────────────────────────
st.subheader("Mercado de Crédito — Indicadores do Dia")

df_series = query(
    "vw_series_historico",
    select="data_ref,cdi_sob_pct,ipca_sob_todos_pct,gap_pct,ipca_qtd_todos,cdi_qtd_ativos",
    order="data_ref.desc",
    limit=2,
)
df_series = df_series.apply(pd.to_numeric, errors="ignore")

if not df_series.empty:
    hoje = df_series.iloc[0]
    ontem = df_series.iloc[1] if len(df_series) > 1 else hoje

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "SOB CDI+",
        f"{float(hoje['cdi_sob_pct']):.2f}%",
        f"{float(hoje['cdi_sob_pct']) - float(ontem['cdi_sob_pct']):.2f}pp",
    )
    k2.metric(
        "SOB IPCA+ (todos)",
        f"{float(hoje['ipca_sob_todos_pct']):.2f}%",
        f"{float(hoje['ipca_sob_todos_pct']) - float(ontem['ipca_sob_todos_pct']):.2f}pp",
    )
    k3.metric(
        "Gap (IPCA+ vs NTN-B)",
        f"{float(hoje['gap_pct']):.2f}%",
        f"{float(hoje['gap_pct']) - float(ontem['gap_pct']):.2f}pp",
    )
    k4.metric(
        "N° Ativos IPCA+",
        int(hoje["ipca_qtd_todos"]),
    )
    k5.metric(
        "N° Ativos CDI+",
        int(hoje["cdi_qtd_ativos"]),
    )

st.divider()

# ── Spread por Setor (última data) ───────────────────────────────────────────
st.subheader("Spread por Setor — IPCA+")

df_spread = query(
    "vw_spread_por_setor",
    select="setor,indexador,faixa_rating,qtd_ativos,sob_medio_pct,sob_min_pct,sob_max_pct,duration_media,data_ref",
    order="data_ref.desc",
)
df_spread = df_spread.apply(pd.to_numeric, errors="ignore")

if not df_spread.empty:
    data_spread_max = df_spread["data_ref"].max()
    df_spread_dia = df_spread[
        (df_spread["data_ref"] == data_spread_max) & (df_spread["indexador"] == "IPCA +")
    ].copy()
    df_spread_dia = df_spread_dia.sort_values("sob_medio_pct", ascending=False)

    if not df_spread_dia.empty:
        fig = go.Figure()
        for faixa in df_spread_dia["faixa_rating"].unique():
            sub = df_spread_dia[df_spread_dia["faixa_rating"] == faixa]
            fig.add_trace(go.Bar(
                x=sub["setor"],
                y=sub["sob_medio_pct"],
                name=faixa,
                text=sub["sob_medio_pct"].apply(lambda v: f"{v:.2f}%"),
                textposition="outside",
            ))

        fig.update_layout(
            barmode="group",
            height=420,
            xaxis_title="Setor",
            yaxis_title="SOB Médio (%)",
            legend_title="Faixa de Rating",
            margin=dict(t=30, b=60),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Referência: {data_spread_max}")

st.divider()

# ── Mini série histórica de SOB ──────────────────────────────────────────────
st.subheader("Evolução do Spread (últimos 60 dias)")

df_hist = query(
    "vw_series_historico",
    select="data_ref,cdi_sob_pct,ipca_sob_todos_pct,gap_pct",
    order="data_ref.desc",
    limit=60,
)
df_hist = df_hist.apply(pd.to_numeric, errors="ignore")
df_hist["data_ref"] = pd.to_datetime(df_hist["data_ref"])
df_hist = df_hist.sort_values("data_ref")

if not df_hist.empty:
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=df_hist["data_ref"], y=df_hist["ipca_sob_todos_pct"],
        name="IPCA+ SOB", mode="lines", line=dict(width=2, color="#1f77b4"),
    ))
    fig2.add_trace(go.Scatter(
        x=df_hist["data_ref"], y=df_hist["cdi_sob_pct"],
        name="CDI+ SOB", mode="lines", line=dict(width=2, color="#ff7f0e"),
    ))
    fig2.add_trace(go.Scatter(
        x=df_hist["data_ref"], y=df_hist["gap_pct"],
        name="Gap", mode="lines", line=dict(width=2, dash="dot", color="#2ca02c"),
    ))
    fig2.update_layout(
        height=320,
        xaxis_title="Data",
        yaxis_title="%",
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=10, b=40),
    )
    st.plotly_chart(fig2, use_container_width=True)

st.caption("Bocaina Capital Gestora de Recursos Ltda")

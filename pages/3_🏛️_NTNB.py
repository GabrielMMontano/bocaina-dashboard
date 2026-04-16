import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.db import query, latest_date

st.set_page_config(page_title="NTN-B", page_icon="🏛️", layout="wide")
st.title("🏛️ NTN-B — Tesouro IPCA+")
st.caption("Curvas de taxa indicativa e comparativo histórico")

# ── Dados ────────────────────────────────────────────────────────────────────
df = query(
    "vw_ntnb_comparativo",
    select="data_ref,tipo_data,data_vencimento,tx_indicativa,prazo_anos,pu,tx_compra,tx_venda,int_min_d0,int_max_d0",
    order="data_ref.desc",
)
df = df.apply(pd.to_numeric, errors="ignore")
df["data_ref"] = pd.to_datetime(df["data_ref"])
df["data_vencimento"] = pd.to_datetime(df["data_vencimento"])

if df.empty:
    st.error("Sem dados disponíveis.")
    st.stop()

datas_uteis = sorted(df["data_ref"].unique(), reverse=True)

# ── Sidebar: seleção de datas ────────────────────────────────────────────────
st.sidebar.subheader("Comparativo de curvas")
d1 = st.sidebar.selectbox(
    "Data 1 (atual)",
    [d.strftime("%Y-%m-%d") for d in datas_uteis],
    index=0,
)
d2 = st.sidebar.selectbox(
    "Data 2 (comparação)",
    [d.strftime("%Y-%m-%d") for d in datas_uteis],
    index=min(5, len(datas_uteis) - 1),
)

df1 = df[df["data_ref"] == pd.to_datetime(d1)].sort_values("prazo_anos")
df2 = df[df["data_ref"] == pd.to_datetime(d2)].sort_values("prazo_anos")

# ── KPIs ─────────────────────────────────────────────────────────────────────
st.subheader(f"Curva em {pd.to_datetime(d1).strftime('%d/%m/%Y')}")

if not df1.empty:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("N° vértices", len(df1))
    c2.metric("Taxa mín.", f"{df1['tx_indicativa'].min():.4f}%")
    c3.metric("Taxa máx.", f"{df1['tx_indicativa'].max():.4f}%")
    c4.metric(
        "Taxa longa (maior prazo)",
        f"{df1.sort_values('prazo_anos').iloc[-1]['tx_indicativa']:.4f}%",
    )

st.divider()

# ── Gráfico: Curva NTN-B (comparativo) ───────────────────────────────────────
st.subheader("Curva NTN-B — Comparativo")

fig = go.Figure()

if not df1.empty:
    fig.add_trace(go.Scatter(
        x=df1["prazo_anos"],
        y=df1["tx_indicativa"],
        mode="lines+markers",
        name=f"Atual ({pd.to_datetime(d1).strftime('%d/%m/%Y')})",
        line=dict(width=2.5, color="#1f77b4"),
        marker=dict(size=8),
        text=df1["data_vencimento"].dt.strftime("%b/%Y"),
        hovertemplate="<b>%{text}</b><br>Prazo: %{x:.2f}a<br>Taxa: %{y:.4f}%<extra></extra>",
    ))

if not df2.empty and d2 != d1:
    fig.add_trace(go.Scatter(
        x=df2["prazo_anos"],
        y=df2["tx_indicativa"],
        mode="lines+markers",
        name=f"Comparação ({pd.to_datetime(d2).strftime('%d/%m/%Y')})",
        line=dict(width=2, color="#ff7f0e", dash="dash"),
        marker=dict(size=6),
        text=df2["data_vencimento"].dt.strftime("%b/%Y"),
        hovertemplate="<b>%{text}</b><br>Prazo: %{x:.2f}a<br>Taxa: %{y:.4f}%<extra></extra>",
    ))

fig.update_layout(
    height=450,
    xaxis_title="Prazo (anos)",
    yaxis_title="Taxa Indicativa (% a.a.)",
    legend=dict(orientation="h", y=1.1),
    margin=dict(t=10, b=50),
)
st.plotly_chart(fig, use_container_width=True)

# ── Gráfico: Banda bid/ask ────────────────────────────────────────────────────
st.subheader("Banda Bid/Ask — Intervalo do Dia")

df1_band = df1.dropna(subset=["int_min_d0", "int_max_d0"]).sort_values("prazo_anos")
if not df1_band.empty:
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=pd.concat([df1_band["prazo_anos"], df1_band["prazo_anos"][::-1]]),
        y=pd.concat([df1_band["int_max_d0"], df1_band["int_min_d0"][::-1]]),
        fill="toself",
        fillcolor="rgba(31,119,180,0.2)",
        line=dict(color="rgba(255,255,255,0)"),
        name="Banda int. d0",
        showlegend=True,
    ))
    fig2.add_trace(go.Scatter(
        x=df1_band["prazo_anos"],
        y=df1_band["tx_indicativa"],
        mode="lines+markers",
        name="Taxa indicativa",
        line=dict(width=2, color="#1f77b4"),
    ))
    fig2.update_layout(
        height=360,
        xaxis_title="Prazo (anos)",
        yaxis_title="Taxa (% a.a.)",
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=10, b=50),
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Evolução histórica de um vértice ────────────────────────────────────────
st.subheader("Evolução histórica por vértice")

vencimentos = sorted(df["data_vencimento"].dropna().unique())
vert_labels = [v.strftime("%b/%Y") for v in vencimentos]
vert_sel = st.selectbox("Escolha o vencimento", vert_labels)
vert_date = vencimentos[vert_labels.index(vert_sel)]

df_vert = df[df["data_vencimento"] == vert_date].sort_values("data_ref")

if not df_vert.empty:
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=df_vert["data_ref"],
        y=df_vert["tx_indicativa"],
        mode="lines",
        name="Taxa indicativa",
        line=dict(width=2, color="#1f77b4"),
    ))
    fig3.update_layout(
        height=320,
        xaxis_title="Data",
        yaxis_title="Taxa (% a.a.)",
        margin=dict(t=10, b=40),
    )
    st.plotly_chart(fig3, use_container_width=True)

# ── Tabela ────────────────────────────────────────────────────────────────────
with st.expander("Ver tabela completa"):
    df_show = df1.copy()
    df_show["data_vencimento"] = df_show["data_vencimento"].dt.strftime("%d/%m/%Y")
    for col in ["tx_indicativa", "tx_compra", "tx_venda", "prazo_anos"]:
        if col in df_show.columns:
            df_show[col] = pd.to_numeric(df_show[col], errors="coerce").round(4)
    st.dataframe(df_show.drop(columns=["data_ref"], errors="ignore"),
                 use_container_width=True, hide_index=True)

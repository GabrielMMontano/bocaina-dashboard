import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.db import query

VERDE = "#0a2300"; MARROM = "#cdaa82"; PALHA = "#fff0dc"
PLOT_BG = "rgba(0,0,0,0)"; GRID = "rgba(255,240,220,0.08)"

st.set_page_config(page_title="Setores | Bocaina", page_icon="🏢", layout="wide")
st.markdown(f'<h3 style="color:{MARROM}">🏢 Spread por Setor</h3>', unsafe_allow_html=True)

@st.cache_data(ttl=300)
def load():
    df = query(
        "vw_spread_por_setor",
        select="setor,indexador,faixa_rating,qtd_ativos,sob_medio_pct,sob_min_pct,sob_max_pct,duration_media,data_ref",
        order="data_ref.desc",
    )
    df["data_ref"] = pd.to_datetime(df["data_ref"])
    num_cols = [c for c in df.columns if c not in ("data_ref", "setor", "indexador", "faixa_rating")]
    df[num_cols] = df[num_cols].apply(lambda c: pd.to_numeric(c, errors="coerce"))
    return df

df_raw = load()
if df_raw.empty:
    st.error("Sem dados."); st.stop()

datas = sorted(df_raw["data_ref"].unique(), reverse=True)

st.sidebar.markdown(f'<b style="color:{MARROM}">Filtros</b>', unsafe_allow_html=True)
data_sel = st.sidebar.selectbox("Data", datas,
    format_func=lambda d: pd.to_datetime(d).strftime("%d/%m/%Y"))
idx_sel  = st.sidebar.selectbox("Indexador", ["IPCA +", "CDI +", "% CDI", "Todos"])

df = df_raw[df_raw["data_ref"] == pd.to_datetime(data_sel)].copy()
if idx_sel != "Todos":
    df = df[df["indexador"] == idx_sel]

if df.empty:
    st.warning("Sem dados para o filtro."); st.stop()

# ── KPIs ─────────────────────────────────────────────────────────────────────
c1,c2,c3,c4 = st.columns(4)
c1.metric("Setores", df["setor"].nunique())
c2.metric("N° Ativos", int(df["qtd_ativos"].sum()))
w = (df["sob_medio_pct"] * df["qtd_ativos"]).sum() / df["qtd_ativos"].sum()
c3.metric("Spread médio pond. (%)", f"{w:.2f}%")
c4.metric("Duration média (anos)", f"{df['duration_media'].mean():.2f}")
st.divider()

tab1, tab2, tab3 = st.tabs(["📊 Barras por Setor", "🟥 Heatmap Setor × Rating", "⚫ Bubble Duration × Spread"])

with tab1:
    df_bar = df.sort_values("sob_medio_pct", ascending=False)
    fig = px.bar(
        df_bar, x="setor", y="sob_medio_pct", color="faixa_rating",
        barmode="group",
        error_y=      (df_bar["sob_max_pct"] - df_bar["sob_medio_pct"]).clip(lower=0),
        error_y_minus=(df_bar["sob_medio_pct"] - df_bar["sob_min_pct"]).clip(lower=0),
        labels={"setor":"Setor","sob_medio_pct":"Spread s/ NTN-B (%)","faixa_rating":"Rating"},
        height=450,
        color_discrete_sequence=[MARROM, PALHA, "#7ec8a0", "#e8b86d", "#a8c8a0"],
    )
    fig.update_layout(
        paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG,
        font=dict(color=PALHA, size=11),
        xaxis=dict(gridcolor=GRID, zeroline=False, tickangle=-35),
        yaxis=dict(gridcolor=GRID, zeroline=False),
        legend=dict(orientation="h", y=1.1, bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=20,b=100,l=55,r=20),
    )
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    pivot = df.pivot_table(index="setor", columns="faixa_rating",
                           values="sob_medio_pct", aggfunc="mean")
    if pivot.empty:
        st.info("Sem dados.")
    else:
        fig2 = px.imshow(
            pivot, text_auto=".2f",
            color_continuous_scale=[[0,"#0a2300"],[0.5,"#cdaa82"],[1,"#fff0dc"]],
            aspect="auto", labels={"color":"Spread (%)"},
            height=max(300, len(pivot)*35+100),
        )
        fig2.update_layout(
            paper_bgcolor=PLOT_BG, font=dict(color=PALHA, size=11),
            margin=dict(t=20,b=40,l=100,r=20),
        )
        st.plotly_chart(fig2, use_container_width=True)

with tab3:
    df_b = df.dropna(subset=["duration_media","sob_medio_pct"])
    if df_b.empty:
        st.info("Sem dados.")
    else:
        fig3 = px.scatter(
            df_b, x="duration_media", y="sob_medio_pct",
            size="qtd_ativos", color="setor", text="setor",
            hover_data=["faixa_rating","qtd_ativos","sob_min_pct","sob_max_pct"],
            labels={"duration_media":"Duration Média (anos)","sob_medio_pct":"Spread s/ NTN-B (%)"},
            height=480, size_max=45,
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig3.update_traces(textposition="top center", marker=dict(opacity=0.8))
        fig3.update_layout(
            paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG,
            font=dict(color=PALHA, size=11),
            xaxis=dict(gridcolor=GRID, zeroline=False),
            yaxis=dict(gridcolor=GRID, zeroline=False),
            showlegend=False, margin=dict(t=20,b=40,l=55,r=20),
        )
        st.plotly_chart(fig3, use_container_width=True)

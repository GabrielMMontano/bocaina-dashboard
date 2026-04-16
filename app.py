import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import base64, os
from utils.db import query, latest_date

# ── Cores Bocaina ────────────────────────────────────────────────────────────
VERDE  = "#0a2300"
MARROM = "#cdaa82"
PALHA  = "#fff0dc"
VERDE2 = "#1a4a00"

st.set_page_config(
    page_title="Bocaina | Screening Crédito",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Logo no topo ─────────────────────────────────────────────────────────────
def _logo_b64():
    p = os.path.join(os.path.dirname(__file__), "assets", "logo_bocaina.png")
    if os.path.exists(p):
        with open(p, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

logo = _logo_b64()
col_logo, col_title = st.columns([1, 5])
with col_logo:
    if logo:
        st.markdown(
            f'<img src="data:image/png;base64,{logo}" style="height:60px;margin-top:4px">',
            unsafe_allow_html=True,
        )
with col_title:
    st.markdown(
        f'<h2 style="color:{MARROM};margin:0;font-family:Helvetica">Screening de Crédito Privado</h2>'
        f'<p style="color:{PALHA};opacity:.7;margin:0;font-size:13px">Mercado de Debêntures · IPCA+ · CDI+</p>',
        unsafe_allow_html=True,
    )

st.divider()

# ── Carregar série histórica ─────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_series(limit: int = 252) -> pd.DataFrame:
    df = query(
        "vw_series_historico",
        select="data_ref,cdi_sob_pct,cdi_qtd_ativos,ipca_sob_todos_pct,ipca_qtd_todos,"
               "ipca_sob_aaa_aa_pct,gap_pct,gap2_pct,var_dia_sob_todos,var_dia_gap",
        order="data_ref.desc",
        limit=limit,
    )
    df["data_ref"] = pd.to_datetime(df["data_ref"])
    num_cols = [c for c in df.columns if c != "data_ref"]
    df[num_cols] = df[num_cols].apply(lambda c: pd.to_numeric(c, errors="coerce"))
    return df.sort_values("data_ref").reset_index(drop=True)

df = load_series()
if df.empty:
    st.error("Sem dados. Verifique a conexão com o Supabase.")
    st.stop()

hoje   = df.iloc[-1]
ontem  = df.iloc[-2] if len(df) > 1 else hoje
data_s = hoje["data_ref"].strftime("%d/%m/%Y")

# ── Cabeçalho de data ────────────────────────────────────────────────────────
st.markdown(
    f'<p style="color:{PALHA};opacity:.6;font-size:13px;margin-bottom:4px">'
    f'Última atualização: <strong style="color:{MARROM}">{data_s}</strong></p>',
    unsafe_allow_html=True,
)

# ── KPIs principais ──────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)

def _delta(a, b): return round(float(a) - float(b), 4)

k1.metric(
    "IPCA+ Nominal",
    f"{float(hoje['ipca_sob_todos_pct']):.2f}%",
    f"{_delta(hoje['ipca_sob_todos_pct'], ontem['ipca_sob_todos_pct']):+.2f}pp",
    help="Taxa nominal média dos ativos IPCA+",
)
k2.metric(
    "Spread s/ NTN-B (Todos)",
    f"{float(hoje['gap_pct']):.2f}%",
    f"{_delta(hoje['gap_pct'], ontem['gap_pct']):+.2f}pp",
    help="Spread médio IPCA+ acima da NTN-B equivalente",
)
k3.metric(
    "Spread s/ NTN-B (AAA–AA)",
    f"{float(hoje['ipca_sob_aaa_aa_pct']):.2f}%",
    f"{_delta(hoje['ipca_sob_aaa_aa_pct'], ontem['ipca_sob_aaa_aa_pct']):+.2f}pp",
    help="Spread s/ NTN-B apenas para ativos AAA e AA",
)
k4.metric(
    "CDI+ Spread",
    f"{float(hoje['cdi_sob_pct']):.2f}%",
    f"{_delta(hoje['cdi_sob_pct'], ontem['cdi_sob_pct']):+.2f}pp",
    help="Spread médio dos ativos CDI+ acima do CDI",
)
k5.metric(
    "Ativos IPCA+",
    f"{int(hoje['ipca_qtd_todos'])}",
    f"{int(hoje['ipca_qtd_todos']) - int(ontem['ipca_qtd_todos']):+d}",
)

st.divider()

# ── Gráficos — últimos 60 dias ───────────────────────────────────────────────
df60 = df.tail(60).copy()

PLOT_BG   = "rgba(0,0,0,0)"
GRID_COL  = "rgba(255,240,220,0.08)"
FONT_COL  = PALHA

def base_layout(title="", h=300):
    return dict(
        title=dict(text=title, font=dict(color=MARROM, size=13)),
        paper_bgcolor=PLOT_BG, plot_bgcolor=PLOT_BG,
        font=dict(color=FONT_COL, size=11),
        xaxis=dict(gridcolor=GRID_COL, showgrid=True, zeroline=False),
        yaxis=dict(gridcolor=GRID_COL, showgrid=True, zeroline=False),
        legend=dict(orientation="h", y=1.15, font=dict(size=10)),
        margin=dict(t=40, b=30, l=50, r=20),
        height=h,
    )

col_a, col_b = st.columns(2)

with col_a:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df60["data_ref"], y=df60["ipca_sob_todos_pct"],
        name="IPCA+ Nominal", mode="lines",
        line=dict(color=MARROM, width=2.5),
        fill="tozeroy", fillcolor="rgba(205,170,130,0.10)",
    ))
    fig.update_layout(**base_layout("IPCA+ Nominal (%)"))
    st.plotly_chart(fig, use_container_width=True)

with col_b:
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=df60["data_ref"], y=df60["gap_pct"],
        name="Spread s/ NTN-B (Todos)", mode="lines",
        line=dict(color=PALHA, width=2.5),
    ))
    fig2.add_trace(go.Scatter(
        x=df60["data_ref"], y=df60["ipca_sob_aaa_aa_pct"],
        name="Spread AAA–AA", mode="lines",
        line=dict(color=MARROM, width=2, dash="dot"),
    ))
    fig2.update_layout(**base_layout("Spread s/ NTN-B (%)"))
    st.plotly_chart(fig2, use_container_width=True)

col_c, col_d = st.columns(2)

with col_c:
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=df60["data_ref"], y=df60["cdi_sob_pct"],
        name="CDI+ Spread", mode="lines",
        line=dict(color="#7ec8a0", width=2.5),
        fill="tozeroy", fillcolor="rgba(126,200,160,0.08)",
    ))
    fig3.update_layout(**base_layout("CDI+ Spread (%)"))
    st.plotly_chart(fig3, use_container_width=True)

with col_d:
    fig4 = go.Figure()
    fig4.add_trace(go.Bar(
        x=df60["data_ref"], y=df60["ipca_qtd_todos"],
        name="N° Ativos IPCA+",
        marker_color=MARROM, opacity=0.7,
    ))
    fig4.update_layout(**base_layout("N° Ativos IPCA+"))
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

# ── Top 10 maior spread do dia ───────────────────────────────────────────────
st.markdown(f'<h4 style="color:{MARROM}">Top 10 — Maior Spread s/ NTN-B (hoje)</h4>',
            unsafe_allow_html=True)

data_deb = latest_date("fato_debentures")

@st.cache_data(ttl=300)
def load_top10(data_ref: str) -> pd.DataFrame:
    df = query(
        "vw_ativos_enriquecido",
        select="ticker,emissor,setor,indexador,rating,faixa_rating,taxa_mtm_pct,sob_pct,duration_anos,infra,vencimento",
        filters={"data_ref": f"eq.{data_ref}", "indexador": "eq.IPCA +"},
        order="sob_pct.desc.nullslast",
        limit=10,
    )
    return df.apply(lambda c: pd.to_numeric(c, errors="coerce"))

df_top = load_top10(data_deb)

if not df_top.empty:
    df_top["taxa_mtm_pct"] = pd.to_numeric(df_top["taxa_mtm_pct"], errors="coerce").round(2)
    df_top["sob_pct"]      = pd.to_numeric(df_top["sob_pct"],      errors="coerce").round(2)
    df_top["duration_anos"]= pd.to_numeric(df_top["duration_anos"],errors="coerce").round(2)
    st.dataframe(
        df_top[["ticker","emissor","setor","rating","faixa_rating","taxa_mtm_pct","sob_pct","duration_anos","infra","vencimento"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "ticker":        "Ticker",
            "emissor":       "Emissor",
            "setor":         "Setor",
            "rating":        "Rating",
            "faixa_rating":  "Faixa",
            "taxa_mtm_pct":  st.column_config.NumberColumn("IPCA+ Nominal (%)", format="%.2f"),
            "sob_pct":       st.column_config.NumberColumn("Spread s/ NTN-B (%)", format="%.2f"),
            "duration_anos": st.column_config.NumberColumn("Duration (a)", format="%.2f"),
            "infra":         st.column_config.CheckboxColumn("Infra"),
            "vencimento":    "Vencimento",
        },
    )

st.caption(
    f'Dados: Supabase · Ref. debentures {data_deb} · Ref. séries {data_s}  |  '
    f'Bocaina Capital Gestora de Recursos Ltda'
)

import subprocess, sys

for pkg in ["dash", "plotly", "pandas"]:
    try:
        __import__(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import sqlite3, os, base64, json
from datetime import datetime, timedelta
from collections import OrderedDict

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, dash_table, Input, Output, State, callback_context


# ──────────────────────────────────────────────────────────────────────────────
# Helper: DataTable com export automatico (XLSX). Substitui dash_table.DataTable
# em todo o app via replace _DataTable(...) abaixo.
# ──────────────────────────────────────────────────────────────────────────────
_RAW_DATATABLE = dash_table.DataTable

def _DataTable(**kwargs):
    """Wrapper que adiciona export_format/export_headers por padrao."""
    kwargs.setdefault("export_format", "xlsx")
    kwargs.setdefault("export_headers", "display")
    return _RAW_DATATABLE(**kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "data", "carteiras_btg.db"))

PALHA  = "#fff0dc"
VERDE  = "#0a2300"
MARROM = "#cdaa82"
FONT   = "'Gotham HTF', Helvetica, Arial, sans-serif"

PIE_COLORS = [VERDE, MARROM, "#f5e6cd", "#0a0f00", PALHA,
              "#1a3d0a", "#a68b5b", "#d4c4a8", "#2e5c14", "#8b7355"]

VERMELHO_ALERTA = "#b22222"

# ══════════════════════════════════════════════════════════════════════════════
# ENQUADRAMENTO — REGULATORY RULES CONFIG (FI-INFRA / Lei 12.431)
# ══════════════════════════════════════════════════════════════════════════════

REGRAS_ENQUADRAMENTO = {
    "R01": {
        "name": "Ativos Elegíveis",
        "limit_type": "min",
        "limit_value": 0.85,
        "warning_threshold": 0.87,
        "rolling_days": 252,
    },
    "R02": {
        "name": "Fora Elegíveis",
        "limit_type": "max",
        "limit_value": 0.15,
        "warning_threshold": 0.13,
        "rolling_days": 252,
    },
    "R03": {
        "name": "Deb. NI Cap. Fechado",
        "limit_type": "max",
        "limit_value": 0.10,
        "warning_threshold": 0.08,
        "rolling_days": 252,
    },
    "R04": {
        "name": "Conc. Emissor",
        "limit_type": "max_per_group",
        "limit_value": 0.20,
        "warning_threshold": 0.17,
        "rolling_days": 252,
    },
}

# Tipos de ativo que são elegíveis sem restrição de prazo
_TIPOS_ELEGIVEL_SEMPRE = {"Deb. Incentivada", "CRI", "FIDC"}
# Tipos elegíveis apenas se prazo residual > 2 anos
_TIPOS_ELEGIVEL_COM_PRAZO = {
    "Deb. Não incentivada (capital Aberto)",
    "Deb. Não incentivada (capital fechado)",
}
_TIPO_DEB_NAO_INC_FECHADO = "Deb. Não incentivada (capital fechado)"

_ELEGIBILIDADE_LABELS = {
    "elegivel_deb_incentivada": "Elegível (Incentivada)",
    "elegivel_cri": "Elegível (CRI)",
    "elegivel_fidc": "Elegível (FIDC)",
    "elegivel_nao_inc_aberto": "Elegível (NI Cap. Aberto)",
    "elegivel_nao_inc_fechado": "Elegível (NI Cap. Fechado)",
    "nao_elegivel_prazo": "Não Elegível (Prazo ≤ 2a)",
    "nao_elegivel_tipo": "Não Elegível (Tipo)",
    "sem_classificacao": "Sem Classificação",
}


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE CONNECTION
# ══════════════════════════════════════════════════════════════════════════════

def _conn():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


# ══════════════════════════════════════════════════════════════════════════════
# FUND CONFIGURATION — built dynamically from ref_fundos + ref_fic_master
# ══════════════════════════════════════════════════════════════════════════════

# URL key overrides for known funds (preserves existing URLs)
_URL_KEYS = {
    "BOCAINA_STB_RF_INFRA": "STB",
    "BOCAINA_60_CDI_FCRF": "D60_CDI",
    "BOCAINA_IPCA_60_FCRF": "D60_IPCA",
    "BOCAINA_60_INST_FCRF": "D60_INST",
    "BOCAINA_FC_RF_INFRA": "BODB",
    "BOCAINA_FIC_INFRA_RF": "BODI",
    "BOCAINA_INFR_FICRF": "INC",
    "BOCAINA_INFRA_DI_RENDA_MAIS": "RENDAMAIS",
}

# Funds to exclude from dashboard (present in DB but shouldn't be displayed)
_EXCLUDE_FUNDS = {
    "BOCAINA_CL_A_I_FC_RF",
    "BOCAINA_I_FC_RF_CL_A",   # Classe A aparece sob o botão "Incentivadas (EQI)"
}

# Display labels for navigation buttons
_NAV_LABELS = {
    "STB":       "STB D360",
    "D60_CDI":   "D60 CDI",
    "D60_IPCA":  "D60 IPCA",
    "D60_INST":  "D60 Institucional",
    "BODB":      "BODB11",
    "BODI":      "BODI11",
    "INC":       "Incentivadas (EQI)",
    "RENDAMAIS": "RENDA Mais",
}

# Landing page section structure — order and groupings shown to the user
# Each tuple: (section_title, [fund_keys], layout)
# layout: "row" = side by side | "col" = stacked vertically
_LANDING_SECTIONS = [
    ("LISTADOS E PRAZO INDETERMINADO", ["BODB", "BODI", "INC"],  "row"),
    ("ABERTOS",                        ["D60_CDI", "D60_IPCA", "D60_INST", "STB"], "col"),
    ("PRAZO DETERMINADO",              ["RENDAMAIS"],            "row"),
]

# Mapping fund_key -> nomes em fact_trades/fact_perfatt/fact_pl_diario (ControleGeral)
# Primeira entrada e sempre o "FIC top-level" usado para attribution
_NEW_TABLE_FUND_MAP = {
    "BODB":     ["BODB11", "Master1", "Master2", "Master3", "Master4", "Master5"],
    "BODI":     ["BODI", "MasterBODI"],
    "D60_CDI":  ["CDI FIC", "CDI MST"],
    "D60_IPCA": ["FIC IPCA", "IPCA MST"],
    "D60_INST": ["FIC INST", "INST MST"],
}


def _auto_key(fundo_name):
    """Generate a URL-safe key from a fund name."""
    return fundo_name.replace("BOCAINA_", "").replace(" ", "_").upper()


def _build_funds():
    """Build FUNDS dict from database ref_fundos + ref_fic_master at startup."""
    con = _conn()
    try:
        fundos = pd.read_sql("SELECT fundo, tipo, produto, display FROM ref_fundos", con)
        fic_master = pd.read_sql("SELECT fic_fundo, master_fundo FROM ref_fic_master", con)
        rent_set = set(
            pd.read_sql("SELECT DISTINCT fundo FROM fact_rentabilidade", con)["fundo"]
        )
    finally:
        con.close()

    funds = {}
    for _, row in fundos.iterrows():
        fundo = row["fundo"]
        tipo = row["tipo"]
        produto = row["produto"]
        display = row["display"]
        if fundo in _EXCLUDE_FUNDS:
            continue  # explicitly excluded
        if fundo not in rent_set:
            continue  # skip funds with no rentabilidade data

        if tipo == "FIC":
            masters = fic_master[fic_master["fic_fundo"] == fundo]["master_fundo"].tolist()
            if not masters:
                continue
        elif tipo == "STANDALONE":
            masters = [fundo]
        else:
            continue  # skip MASTER-only entries

        key = _URL_KEYS.get(fundo, _auto_key(fundo))
        funds[key] = {
            "display": display,
            "rent_fundo": fundo,
            "carteira_fundos": masters,
            "produto": produto,
        }

    return funds


try:
    FUNDS = _build_funds()
except Exception as e:
    print(f"[WARN] DB indisponível em {DB_PATH}: {e}. Iniciando com FUNDS vazio.", flush=True)
    FUNDS = {}


# ══════════════════════════════════════════════════════════════════════════════
# LOGO
# ══════════════════════════════════════════════════════════════════════════════

def _encode_logo():
    logo_path = os.path.join(BASE_DIR, "assets", "logo_bocaina.png")
    if not os.path.exists(logo_path):
        logo_path = os.path.join(BASE_DIR, "logo_bocaina.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f"data:image/png;base64,{b64}"
    return None

LOGO_SRC = _encode_logo()


# ══════════════════════════════════════════════════════════════════════════════
# SQL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _in_clause(items):
    """Return (placeholder_string, params_tuple) for SQL IN (...)."""
    return ",".join(["?"] * len(items)), tuple(items)


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADERS (parametrizados por fundo — multi-master)
# ══════════════════════════════════════════════════════════════════════════════

def load_rent(fund_key):
    """Rentabilidade do FIC (para D60/BODB/etc.) ou fundo direto (STB)."""
    cfg = FUNDS[fund_key]
    con = _conn()
    df = pd.read_sql(
        "SELECT data, patrimonio, cota_liquida, rent_dia, pct_cdi_dia "
        "FROM fact_rentabilidade WHERE fundo=? ORDER BY data",
        con, params=(cfg["rent_fundo"],))
    con.close()
    df["data"] = pd.to_datetime(df["data"])
    df = df.sort_values("data").drop_duplicates("data").reset_index(drop=True)
    return df


def load_titulos(data, fund_key):
    """Carrega titulos privados dos Master(s). GROUP BY isin para multi-master."""
    cfg = FUNDS[fund_key]
    masters = cfg["carteira_fundos"]
    ph, params = _in_clause(masters)
    con = _conn()
    df = pd.read_sql(
        f"SELECT MAX(t.emissor) as emissor, MAX(t.titulo) as titulo, t.isin, "
        f"       SUM(t.financeiro) as financeiro, "
        f"       SUM(t.quantidade) as quantidade, "
        f"       MAX(t.coupon) as coupon, "
        f"       MAX(sr.setor) as setor, MAX(sr.rating) as rating, "
        f"       MAX(sr.indexador) as sr_indexador "
        f"FROM fact_titulos_privados t "
        f"LEFT JOIN ref_setor_rating sr "
        f"  ON sr.codigo = UPPER(SUBSTR(t.titulo, 1, 6)) "
        f"WHERE t.data=? AND t.fundo IN ({ph}) "
        f"GROUP BY t.isin "
        f"ORDER BY financeiro DESC",
        con, params=(data, *params))
    con.close()
    return df


def load_titulos_raw(data, fund_key):
    """Titulos privados sem aggregacao (raw). Usado no mapa mensal."""
    cfg = FUNDS[fund_key]
    masters = cfg["carteira_fundos"]
    ph, params = _in_clause(masters)
    con = _conn()
    df = pd.read_sql(
        f"SELECT t.isin, t.titulo, t.emissor, t.quantidade, t.financeiro, "
        f"       t.pct_pl, t.ganho, t.rent_cdi, t.estrategia "
        f"FROM fact_titulos_privados t "
        f"WHERE t.data=? AND t.fundo IN ({ph})",
        con, params=(data, *params))
    con.close()
    return df


def load_caixa(data, fund_key):
    """Caixa = compromissada + titulos publicos. Soma multi-master."""
    cfg = FUNDS[fund_key]
    masters = cfg["carteira_fundos"]
    ph, params = _in_clause(masters)
    con = _conn()
    comp = pd.read_sql(
        f"SELECT SUM(financeiro) as total FROM fact_compromissada "
        f"WHERE data=? AND fundo IN ({ph})", con, params=(data, *params))
    pub = pd.read_sql(
        f"SELECT SUM(financeiro) as total FROM fact_titulos_publicos "
        f"WHERE data=? AND fundo IN ({ph})", con, params=(data, *params))
    con.close()
    c = (comp["total"].iloc[0] or 0) + (pub["total"].iloc[0] or 0)
    return c


def load_despesas(data, fund_key):
    """Despesas somadas dos Masters."""
    cfg = FUNDS[fund_key]
    masters = cfg["carteira_fundos"]
    ph, params = _in_clause(masters)
    con = _conn()
    df = pd.read_sql(
        f"SELECT SUM(valor) as total FROM fact_despesas "
        f"WHERE data=? AND fundo IN ({ph})",
        con, params=(data, *params))
    con.close()
    return df["total"].iloc[0] or 0


# ── ControleGeral / ETL step 8 (fact_perfatt, fact_trades, fact_pu_deb_bocaina)

def _cg_top_fundo(fund_key):
    """Nome canonico do FIC top-level no ControleGeral (1a entrada do map)."""
    lst = _NEW_TABLE_FUND_MAP.get(fund_key, [])
    return lst[0] if lst else None


def load_perfatt_resumo(fund_key):
    """Serie diaria de P&L decomposto. Agrega todas as linhas (Ativo + Compromissadas + Outros + PFee + Taxas Recorrentes) por data, pois fact_perfatt particiona o dia em multiplas linhas tipo."""
    fic = _cg_top_fundo(fund_key)
    if not fic:
        return pd.DataFrame()
    con = _conn()
    try:
        df = pd.read_sql(
            "SELECT data, "
            "SUM(pnl_carrego_index) AS pnl_carrego_index, "
            "SUM(pnl_carrego_yield) AS pnl_carrego_yield, "
            "SUM(pnl_curva) AS pnl_curva, "
            "SUM(pnl_spread) AS pnl_spread, "
            "SUM(pnl_trading) AS pnl_trading, "
            "SUM(pnl_total) AS pnl_total, "
            "SUM(ret_carrego_inflacao) AS ret_carrego_inflacao, "
            "SUM(ret_carrego_yield) AS ret_carrego_yield, "
            "SUM(ret_curva) AS ret_curva, "
            "SUM(ret_spread) AS ret_spread, "
            "SUM(ret_trading) AS ret_trading, "
            "SUM(ret_total) AS ret_total "
            "FROM fact_perfatt "
            "WHERE fundo = ? AND tipo IN ('Ativo','Compromissadas','Outros','PFee','Taxas Recorrentes','Despesas') "
            "GROUP BY data "
            "ORDER BY data",
            con, params=(fic,))
    finally:
        con.close()
    return df


def load_perfatt_ativos(fund_key, data):
    """P&L por ativo num dia especifico (top-level fund)."""
    fic = _cg_top_fundo(fund_key)
    if not fic:
        return pd.DataFrame()
    con = _conn()
    try:
        df = pd.read_sql(
            "SELECT ativo_subtipo as ativo, pnl_carrego_index, pnl_carrego_yield, "
            "pnl_curva, pnl_spread, pnl_trading, pnl_total "
            "FROM fact_perfatt "
            "WHERE fundo = ? AND tipo = 'Ativo' AND data = ? "
            "ORDER BY pnl_total DESC",
            con, params=(fic, data))
    finally:
        con.close()
    return df


def load_trades(fund_key):
    """Lista de trades do fundo (estrutura top-level)."""
    fic = _cg_top_fundo(fund_key)
    if not fic:
        return pd.DataFrame()
    con = _conn()
    try:
        df = pd.read_sql(
            "SELECT data_trade, data_settle, fundo, titulo, side, quantidade, "
            "trade_yield, pu, net_amount, spread_negociado, spread_liquidado, "
            "vertice, mtm_pnl, par_pnl, comentario "
            "FROM fact_trades "
            "WHERE estrutura = ? "
            "ORDER BY data_trade DESC",
            con, params=(fic,))
    finally:
        con.close()
    return df


def load_pu_deb_ticker(ticker):
    """Historico Bocaina (PU/Taxa/Spread) por ticker."""
    con = _conn()
    try:
        df = pd.read_sql(
            "SELECT data, tipo, vna, pu, taxa, duration, spread, curva, referencia "
            "FROM fact_pu_deb_bocaina "
            "WHERE ticker = ? "
            "ORDER BY data",
            con, params=(ticker,))
    finally:
        con.close()
    return df


def load_anbima_ticker(ticker):
    """Historico ANBIMA (todas as abas indexador) por ticker."""
    con = _conn()
    try:
        df = pd.read_sql(
            "SELECT data, indexador_tipo, tx_indicativa, duration, pu, ref_ntnb "
            "FROM fact_deb_anbima "
            "WHERE codigo = ? "
            "ORDER BY data",
            con, params=(ticker,))
    finally:
        con.close()
    return df


def load_tickers_carteira(fund_key):
    """Tickers presentes na carteira mais recente do fundo (para dropdown)."""
    datas = get_datas(fund_key)
    if not datas:
        return []
    df = load_titulos(datas[0], fund_key)
    if df.empty:
        return []
    return sorted(df["titulo"].astype(str).str[:6].str.upper().unique().tolist())


def get_datas(fund_key):
    """Datas disponíveis de títulos privados para os Masters deste fundo."""
    cfg = FUNDS[fund_key]
    masters = cfg["carteira_fundos"]
    ph, params = _in_clause(masters)
    con = _conn()
    df = pd.read_sql(
        f"SELECT DISTINCT data FROM fact_titulos_privados "
        f"WHERE fundo IN ({ph}) ORDER BY data DESC",
        con, params=params)
    con.close()
    return df["data"].tolist()


def load_patrimonio_carteira(data, fund_key):
    """Patrimonio dos Masters (somado). Usado para calculos de % PL."""
    cfg = FUNDS[fund_key]
    masters = cfg["carteira_fundos"]
    ph, params = _in_clause(masters)
    con = _conn()
    df = pd.read_sql(
        f"SELECT SUM(patrimonio) as patrimonio FROM fact_rentabilidade "
        f"WHERE data=? AND fundo IN ({ph})",
        con, params=(data, *params))
    con.close()
    if df.empty or df["patrimonio"].iloc[0] is None:
        return None
    return df["patrimonio"].iloc[0]


def _get_indexador(sr_indexador, titulo):
    """Get indexador from ref_setor_rating first, fallback to title parsing."""
    if sr_indexador is not None and pd.notna(sr_indexador):
        ix = str(sr_indexador).strip().upper()
        if ix and ix not in ("-", "NONE", "NAN", ""):
            if ix in ("CDI",):
                return "CDI+"
            if ix in ("IPCA",):
                return "IPCA+"
            if ix in ("IGP",):
                return "IGP-M+"
            if ix in ("PRE", "PRÉ"):
                return "Prefixado"
            return ix
    # Fallback: pattern match on titulo
    if titulo is None or (hasattr(titulo, '__class__') and pd.isna(titulo)) or str(titulo).strip() == "":
        return "CDI+"
    u = str(titulo).upper()
    if "IPCA" in u:
        return "IPCA+"
    if "CDI" in u:
        return "CDI+"
    if "IGP" in u:
        return "IGP-M+"
    if "PRE" in u or "PRÉ" in u:
        return "Prefixado"
    return "Outros"


# ══════════════════════════════════════════════════════════════════════════════
# ENQUADRAMENTO ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _load_pl_serie(fund_key):
    """Load full PL time-series for the FIC/STANDALONE (rent_fundo)."""
    cfg = FUNDS[fund_key]
    con = _conn()
    df = pd.read_sql(
        "SELECT data, patrimonio FROM fact_rentabilidade "
        "WHERE fundo=? ORDER BY data",
        con, params=(cfg["rent_fundo"],))
    con.close()
    df["data"] = pd.to_datetime(df["data"])
    return df.dropna(subset=["patrimonio"]).drop_duplicates("data").sort_values("data")


def _calcular_pl_medio(fund_key, data_ref, janela=252):
    """Return (pl_dia, pl_medio, dias_disponiveis) for fund at data_ref."""
    df = _load_pl_serie(fund_key)
    if df.empty:
        return None, None, 0
    data_ref_ts = pd.Timestamp(data_ref)
    row = df[df["data"] == data_ref_ts]
    pl_dia = row["patrimonio"].iloc[0] if not row.empty else None
    mask = df["data"] <= data_ref_ts
    df_window = df[mask].tail(janela)
    dias = len(df_window)
    pl_medio = df_window["patrimonio"].mean() if dias > 0 else None
    return pl_dia, pl_medio, dias


def _load_enquadramento_ativos(fund_key, data_ref):
    """Load all private credit positions with classification for a date.

    Returns a DataFrame with columns:
        isin, titulo, ticker, emissor_fact, financeiro, vencimento,
        tipo_ref, emissor_ref, setor, rating,
        prazo_anos, prazo_bucket, elegibilidade,
        emissor_enquadramento, qualidade_tipo, qualidade_emissor
    """
    cfg = FUNDS[fund_key]
    masters = cfg["carteira_fundos"]
    ph, params = _in_clause(masters)
    con = _conn()
    df = pd.read_sql(
        f"SELECT t.isin, t.titulo, t.emissor AS emissor_fact, "
        f"       t.financeiro, t.vencimento "
        f"FROM fact_titulos_privados t "
        f"WHERE t.data=? AND t.fundo IN ({ph})",
        con, params=(data_ref, *params))
    # Load ref_setor_rating separately for flexible matching (handles
    # short codes like CRI, FIDC that are < 6 chars)
    ref = pd.read_sql("SELECT * FROM ref_setor_rating", con)
    con.close()

    if df.empty:
        return df

    # Build lookup: codigo -> row dict
    ref_lookup = {}
    for _, rr in ref.iterrows():
        ref_lookup[rr["codigo"].upper().strip()] = rr.to_dict()

    # Match: try 6-char prefix first, then shorter prefixes down to 3
    def _match_ref(titulo):
        if not titulo or pd.isna(titulo):
            return None
        t = str(titulo).upper().strip()
        for length in (6, 5, 4, 3):
            prefix = t[:length]
            if prefix in ref_lookup:
                return ref_lookup[prefix]
        return None

    matches = df["titulo"].apply(_match_ref)
    df["tipo_ref"] = matches.apply(lambda m: m["tipo"] if m is not None else None)
    df["emissor_ref"] = matches.apply(lambda m: m["emissor"] if m is not None else None)
    df["setor"] = matches.apply(lambda m: m["setor"] if m is not None else None)
    df["rating"] = matches.apply(lambda m: m["rating"] if m is not None else None)

    if df.empty:
        return df

    data_ref_dt = pd.Timestamp(data_ref)

    # Ticker (first 6 chars of titulo)
    df["ticker"] = df["titulo"].str[:6].str.upper()

    # Prazo residual
    df["vencimento_dt"] = pd.to_datetime(df["vencimento"], errors="coerce")
    df["prazo_anos"] = (df["vencimento_dt"] - data_ref_dt).dt.days / 365.25
    df["prazo_bucket"] = df["prazo_anos"].apply(
        lambda x: ">2a" if pd.notna(x) and x > 2 else "<=2a"
    )

    # Classificação de elegibilidade
    def _classificar(row):
        tipo = row["tipo_ref"]
        if pd.isna(tipo) or tipo is None or str(tipo).strip() == "":
            return "sem_classificacao"
        tipo = str(tipo).strip()
        if tipo in _TIPOS_ELEGIVEL_SEMPRE:
            return f"elegivel_{tipo.lower().replace(' ', '_').replace('.', '')}"
        if tipo in _TIPOS_ELEGIVEL_COM_PRAZO:
            if row["prazo_bucket"] == ">2a":
                if tipo == _TIPO_DEB_NAO_INC_FECHADO:
                    return "elegivel_nao_inc_fechado"
                return "elegivel_nao_inc_aberto"
            return "nao_elegivel_prazo"
        return "nao_elegivel_tipo"

    df["elegibilidade"] = df.apply(_classificar, axis=1)
    df["is_elegivel"] = df["elegibilidade"].str.startswith("elegivel")

    # Emissor consolidado
    def _emissor_enq(row):
        if pd.notna(row["emissor_ref"]) and str(row["emissor_ref"]).strip():
            return str(row["emissor_ref"]).strip(), "ref_padronizado"
        if pd.notna(row["emissor_fact"]) and str(row["emissor_fact"]).strip():
            return str(row["emissor_fact"]).strip(), "fallback_fato"
        return "SEM EMISSOR", "sem_emissor"

    emissor_data = df.apply(_emissor_enq, axis=1, result_type="expand")
    df["emissor_enquadramento"] = emissor_data[0]
    df["qualidade_emissor"] = emissor_data[1]

    # Quality flag for tipo
    df["qualidade_tipo"] = df["tipo_ref"].apply(
        lambda x: "ref_classificado" if pd.notna(x) and str(x).strip() else "sem_classificacao"
    )

    return df


def _calcular_enquadramento(fund_key, data_ref, usar_pl_medio=True):
    """Run all rules for a fund at a specific date.

    Returns dict with:
        pl_dia, pl_medio, pl_usado, dias_pl,
        ativos (DataFrame),
        regras: {rule_id: {valor, limite, pct, status, detalhe}}
    """
    pl_dia, pl_medio, dias_pl = _calcular_pl_medio(fund_key, data_ref)
    pl_usado = pl_medio if (usar_pl_medio and pl_medio) else pl_dia
    if not pl_usado or pl_usado <= 0:
        return None

    df = _load_enquadramento_ativos(fund_key, data_ref)
    if df.empty:
        return None

    total_carteira = df["financeiro"].sum()
    total_elegivel = df.loc[df["is_elegivel"], "financeiro"].sum()
    total_nao_elegivel = max(total_carteira - total_elegivel, 0)
    total_deb_fechado = df.loc[
        df["elegibilidade"] == "elegivel_nao_inc_fechado", "financeiro"
    ].sum()

    regras = {}

    # R01 — Mínimo elegíveis
    r01_pct = total_elegivel / pl_usado
    r01_cfg = REGRAS_ENQUADRAMENTO["R01"]
    if r01_pct < r01_cfg["limit_value"]:
        r01_status = "VIOLADO"
    elif r01_pct < r01_cfg["warning_threshold"]:
        r01_status = "ALERTA"
    else:
        r01_status = "CONFORME"
    regras["R01"] = {
        "valor": total_elegivel, "pct": r01_pct,
        "limite": r01_cfg["limit_value"], "status": r01_status,
    }

    # R02 — Máximo fora dos elegíveis (complementar a R01, usa PL - elegíveis)
    r02_nao_eleg = max(pl_usado - total_elegivel, 0)
    r02_pct = r02_nao_eleg / pl_usado
    r02_cfg = REGRAS_ENQUADRAMENTO["R02"]
    if r02_pct > r02_cfg["limit_value"]:
        r02_status = "VIOLADO"
    elif r02_pct > r02_cfg["warning_threshold"]:
        r02_status = "ALERTA"
    else:
        r02_status = "CONFORME"
    regras["R02"] = {
        "valor": r02_nao_eleg, "pct": r02_pct,
        "limite": r02_cfg["limit_value"], "status": r02_status,
    }

    # R03 — Sub-limite deb não inc capital fechado
    r03_pct = total_deb_fechado / pl_usado
    r03_cfg = REGRAS_ENQUADRAMENTO["R03"]
    if r03_pct > r03_cfg["limit_value"]:
        r03_status = "VIOLADO"
    elif r03_pct > r03_cfg["warning_threshold"]:
        r03_status = "ALERTA"
    else:
        r03_status = "CONFORME"
    regras["R03"] = {
        "valor": total_deb_fechado, "pct": r03_pct,
        "limite": r03_cfg["limit_value"], "status": r03_status,
    }

    # R04 — Concentração por emissor
    emissor_agg = df.groupby("emissor_enquadramento")["financeiro"].sum().reset_index()
    emissor_agg["pct"] = emissor_agg["financeiro"] / pl_usado
    r04_cfg = REGRAS_ENQUADRAMENTO["R04"]
    emissor_agg["status"] = emissor_agg["pct"].apply(
        lambda p: "VIOLADO" if p > r04_cfg["limit_value"]
        else ("ALERTA" if p > r04_cfg["warning_threshold"] else "CONFORME")
    )
    emissor_agg = emissor_agg.sort_values("financeiro", ascending=False)
    worst = emissor_agg["status"].tolist()
    if "VIOLADO" in worst:
        r04_status = "VIOLADO"
    elif "ALERTA" in worst:
        r04_status = "ALERTA"
    else:
        r04_status = "CONFORME"
    regras["R04"] = {
        "status": r04_status,
        "limite": r04_cfg["limit_value"],
        "detalhe": emissor_agg,
    }

    return {
        "pl_dia": pl_dia,
        "pl_medio": pl_medio,
        "pl_usado": pl_usado,
        "dias_pl": dias_pl,
        "ativos": df,
        "regras": regras,
    }


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def filter_df(df, period):
    if period == "inicio" or df.empty:
        return df
    last = df["data"].max()
    if period == "ano":
        start = pd.Timestamp(last.year, 1, 1)
    elif period == "12m":
        start = last - pd.DateOffset(months=12)
    elif period == "1m":
        start = last - pd.DateOffset(months=1)
    else:
        return df
    return df[df["data"] >= start].reset_index(drop=True)


def _base(title, height, legend=False):
    return dict(
        title=dict(text=title, font=dict(size=15, color=VERDE, family=FONT),
                   x=0.01, y=0.97),
        plot_bgcolor=PALHA,
        paper_bgcolor=PALHA,
        font=dict(family=FONT, size=12, color=VERDE),
        height=height,
        margin=dict(t=55, b=45, l=70, r=30),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(size=11)),
    )


def _period_buttons(id_prefix):
    buttons = [
        ("Desde o Início", "inicio"),
        ("Ano", "ano"),
        ("Últimos 12 meses", "12m"),
        ("Último Mês", "1m"),
    ]
    return html.Div([
        html.Button(
            label,
            id={"type": f"{id_prefix}-btn", "index": val},
            n_clicks=0,
            style={
                "backgroundColor": VERDE, "color": PALHA,
                "border": f"2px solid {VERDE}", "borderRadius": "6px",
                "padding": "8px 20px", "cursor": "pointer",
                "fontFamily": FONT, "fontWeight": "bold", "fontSize": "13px",
                "marginRight": "8px",
            },
        ) for label, val in buttons
    ], style={"display": "flex", "gap": "4px", "flexWrap": "wrap"})


def _card(title, value):
    return html.Div([
        html.Div(title, style={
            "fontSize": "12px", "fontWeight": "bold",
            "marginBottom": "6px", "opacity": "0.85",
            "whiteSpace": "nowrap",
        }),
        html.Div(value, style={
            "fontSize": "22px", "fontWeight": "bold",
            "whiteSpace": "nowrap",
        }),
    ], style={
        "backgroundColor": VERDE, "color": PALHA,
        "border": f"2px solid {MARROM}", "borderRadius": "8px",
        "padding": "16px 24px", "flex": "1", "textAlign": "center",
        "fontFamily": FONT, "minWidth": "fit-content",
    })


def _section_title(text):
    return html.Div([
        html.H4(text, style={
            "color": VERDE, "fontSize": "15px", "fontWeight": "bold",
            "fontFamily": FONT, "margin": "0",
        }),
        html.Hr(style={"borderColor": MARROM, "borderWidth": "1px",
                        "margin": "4px 0 12px 0"}),
    ], style={"marginTop": "28px"})


MESES = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
         7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}

MESES_NOME = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}

def _fmt_brl(v):
    """Format number as R$ X,XX MM (Brazilian style)."""
    return (f"R$ {v / 1e6:,.2f} MM"
            .replace(",", "X").replace(".", ",").replace("X", "."))

def _fmt_pct(v):
    return f"{v:.2f}%".replace(".", ",")

def _fmt_fin_mil(v):
    v_mil = v / 1000
    return f"{v_mil:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ══════════════════════════════════════════════════════════════════════════════
# APP + LAYOUT
# ══════════════════════════════════════════════════════════════════════════════

app = Dash(__name__, suppress_callback_exceptions=True)
server = app.server
app.title = "Debêntures Incentivadas — Bocaina Capital"

tab_style = {
    "fontFamily": FONT, "fontWeight": "bold", "fontSize": "14px",
    "backgroundColor": PALHA, "color": VERDE,
    "border": f"1px solid {VERDE}", "borderBottom": "none",
    "padding": "12px 24px", "borderRadius": "6px 6px 0 0",
}
tab_sel = {
    **tab_style,
    "backgroundColor": VERDE, "color": PALHA,
}

# Layout principal usa dcc.Location para roteamento por URL
app.layout = html.Div(style={
    "backgroundColor": PALHA, "fontFamily": FONT,
    "padding": "30px 40px", "minHeight": "100vh",
}, children=[
    dcc.Location(id="url", refresh=False),
    dcc.Store(id="pat-period", data="inicio"),
    dcc.Store(id="rent-period", data="inicio"),
    html.Div(id="page-content"),
])


# ══════════════════════════════════════════════════════════════════════════════
# ROUTING — Landing page vs Fund page vs Consolidado
# ══════════════════════════════════════════════════════════════════════════════

def _get_fund_key(pathname):
    """Extrai o fund_key do pathname. Retorna None se invalido."""
    if not pathname:
        return None
    key = pathname.strip("/")
    return key if key in FUNDS else None


@app.callback(Output("page-content", "children"), Input("url", "pathname"))
def display_page(pathname):
    fund_key = _get_fund_key(pathname)
    if fund_key:
        return _render_fund_page(fund_key)
    if pathname and pathname.strip("/").upper() == "CONSOLIDADO":
        return _render_consolidado_page()
    return _render_landing_page()


# ── Landing page ─────────────────────────────────────────────────────────────

def _fund_card_row(key, label):
    """Card horizontal (layout 'col') — fundo com prazo aberto."""
    return dcc.Link(
        html.Div([
            html.Span(label, style={
                "fontFamily": FONT, "fontWeight": "bold",
                "fontSize": "16px", "letterSpacing": "1px",
            }),
            html.Span("→", style={
                "marginLeft": "auto", "fontSize": "18px", "opacity": "0.6",
            }),
        ], style={
            "display": "flex", "alignItems": "center",
            "backgroundColor": VERDE, "color": PALHA,
            "border": f"2px solid {MARROM}", "borderRadius": "10px",
            "padding": "16px 28px", "cursor": "pointer",
            "width": "340px",
        }),
        href=f"/{key}",
        style={"textDecoration": "none"},
    )


def _fund_card_tile(key, label):
    """Card quadrado (layout 'row') — fundo listado / incentivado."""
    return dcc.Link(
        html.Div([
            html.Div(label, style={
                "fontFamily": FONT, "fontWeight": "bold",
                "fontSize": "18px", "letterSpacing": "0.5px",
                "textAlign": "center",
            }),
        ], style={
            "backgroundColor": VERDE, "color": PALHA,
            "border": f"2px solid {MARROM}", "borderRadius": "14px",
            "padding": "32px 36px", "cursor": "pointer",
            "minWidth": "180px", "textAlign": "center",
        }),
        href=f"/{key}",
        style={"textDecoration": "none"},
    )


def _section_header_landing(text):
    return html.Div([
        html.Div(text, style={
            "fontFamily": FONT, "fontWeight": "bold",
            "fontSize": "22px", "color": VERDE,
            "letterSpacing": "3px",
        }),
        html.Div(style={
            "height": "3px", "backgroundColor": MARROM,
            "borderRadius": "2px", "marginTop": "8px", "marginBottom": "20px",
        }),
    ])


def _render_landing_page():
    # ── Header ────────────────────────────────────────────────────────────────
    header_children = []
    if LOGO_SRC:
        header_children.append(
            html.Img(src=LOGO_SRC, style={"height": "64px", "marginRight": "28px"})
        )
    header_children.append(html.Div([
        html.Div("DEBÊNTURES INCENTIVADAS", style={
            "fontFamily": FONT, "fontWeight": "bold",
            "fontSize": "30px", "color": VERDE,
            "letterSpacing": "4px", "lineHeight": "1",
        }),
        html.Div("Estratégia de Crédito Privado", style={
            "fontFamily": FONT, "fontWeight": "normal",
            "fontSize": "13px", "color": MARROM,
            "letterSpacing": "2px", "marginTop": "4px",
        }),
    ]))

    body_sections = []

    # ── Seção 1 — Listados e Prazo Indeterminado ─────────────────────────────
    body_sections.append(_section_header_landing("LISTADOS E PRAZO INDETERMINADO"))
    tiles_listados = []
    for key in ["BODB", "BODI", "INC"]:
        if key in FUNDS:
            label = _NAV_LABELS.get(key, FUNDS[key]["display"])
            tiles_listados.append(_fund_card_tile(key, label))
    body_sections.append(html.Div(tiles_listados, style={
        "display": "flex", "gap": "20px", "flexWrap": "wrap",
        "marginBottom": "44px",
    }))

    # ── Seção 2 — Abertos ─────────────────────────────────────────────────────
    body_sections.append(_section_header_landing("ABERTOS"))
    cards_abertos = []
    for key in ["D60_CDI", "D60_IPCA", "D60_INST", "STB"]:
        if key in FUNDS:
            label = _NAV_LABELS.get(key, FUNDS[key]["display"])
            cards_abertos.append(_fund_card_row(key, label))
    body_sections.append(html.Div(cards_abertos, style={
        "display": "flex", "flexDirection": "column", "gap": "12px",
        "marginBottom": "44px",
    }))

    # ── Seção 3 — Prazo Determinado ───────────────────────────────────────────
    body_sections.append(_section_header_landing("PRAZO DETERMINADO"))
    tiles_pd = []
    for key in ["RENDAMAIS"]:
        if key in FUNDS:
            label = _NAV_LABELS.get(key, FUNDS[key]["display"])
            tiles_pd.append(_fund_card_tile(key, label))
    body_sections.append(html.Div(tiles_pd, style={
        "display": "flex", "gap": "20px", "flexWrap": "wrap",
        "marginBottom": "52px",
    }))

    # ── Consolidado ───────────────────────────────────────────────────────────
    body_sections.append(
        dcc.Link(
            html.Div([
                html.Span("Visão Consolidada", style={
                    "fontFamily": FONT, "fontWeight": "bold",
                    "fontSize": "14px", "letterSpacing": "2px",
                }),
                html.Span("  →", style={"opacity": "0.7"}),
            ]),
            href="/CONSOLIDADO",
            style={
                "display": "inline-flex", "alignItems": "center", "gap": "8px",
                "backgroundColor": MARROM, "color": VERDE,
                "border": f"2px solid {VERDE}", "borderRadius": "8px",
                "padding": "12px 28px", "textDecoration": "none", "cursor": "pointer",
            },
        )
    )

    return html.Div([
        html.Div(header_children, style={
            "display": "flex", "alignItems": "center", "marginBottom": "12px",
        }),
        html.Div(style={
            "height": "2px", "backgroundColor": VERDE,
            "borderRadius": "1px", "marginBottom": "44px",
        }),
        html.Div(body_sections),
    ])


# ── Fund page ────────────────────────────────────────────────────────────────

def _render_fund_page(fund_key):
    cfg = FUNDS[fund_key]

    header_children = []
    if LOGO_SRC:
        header_children.append(
            html.Img(src=LOGO_SRC, style={"height": "50px", "marginRight": "20px"})
        )
    header_children.append(
        html.H2(cfg["display"], style={
            "color": VERDE, "letterSpacing": "3px", "margin": "0",
            "fontSize": "24px", "fontWeight": "bold", "fontFamily": FONT,
        })
    )

    return html.Div([
        # Botao voltar
        dcc.Link("\u2190 Voltar", href="/", style={
            "color": VERDE, "fontFamily": FONT, "fontWeight": "bold",
            "fontSize": "14px", "textDecoration": "none",
            "marginBottom": "12px", "display": "inline-block",
        }),
        html.Div(header_children, style={
            "display": "flex", "alignItems": "center", "marginBottom": "8px",
        }),
        html.Hr(style={"borderColor": VERDE, "borderWidth": "2px",
                        "marginBottom": "0"}),
        dcc.Tabs(id="tabs", value="patrimonio", style={"marginTop": "16px"}, children=[
            dcc.Tab(label="Patrimônio", value="patrimonio",
                    style=tab_style, selected_style=tab_sel),
            dcc.Tab(label="Rentabilidade", value="rentabilidade",
                    style=tab_style, selected_style=tab_sel),
            dcc.Tab(label="Carteira", value="carteira",
                    style=tab_style, selected_style=tab_sel),
            dcc.Tab(label="Mapa Mensal", value="mapa_mensal",
                    style=tab_style, selected_style=tab_sel),
            dcc.Tab(label="Enquadramento", value="enquadramento",
                    style=tab_style, selected_style=tab_sel),
            dcc.Tab(label="P&L Attribution", value="attribution",
                    style=tab_style, selected_style=tab_sel),
            dcc.Tab(label="Trades", value="trades",
                    style=tab_style, selected_style=tab_sel),
            dcc.Tab(label="Spread Histórico", value="spread_hist",
                    style=tab_style, selected_style=tab_sel),
        ]),
        html.Div(id="tab-content", style={"marginTop": "24px"}),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# TAB CONTENT CALLBACK
# ══════════════════════════════════════════════════════════════════════════════

@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "value"),
    State("url", "pathname"),
)
def render_tab(tab, pathname):
    fund_key = _get_fund_key(pathname)
    if not fund_key:
        return html.P("Selecione um fundo.", style={"color": VERDE})

    if tab == "patrimonio":
        return _tab_patrimonio_layout()
    elif tab == "rentabilidade":
        return _tab_rentabilidade_layout()
    elif tab == "mapa_mensal":
        return _tab_mapa_mensal_layout(fund_key)
    elif tab == "enquadramento":
        return _tab_enquadramento_layout(fund_key)
    elif tab == "attribution":
        return _tab_attribution_layout(fund_key)
    elif tab == "trades":
        return _tab_trades_layout(fund_key)
    elif tab == "spread_hist":
        return _tab_spread_hist_layout(fund_key)
    return _tab_carteira_layout(fund_key)


# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 — PATRIMÔNIO
# ══════════════════════════════════════════════════════════════════════════════

def _tab_patrimonio_layout():
    return html.Div([
        _period_buttons("pat"),
        dcc.Store(id="pat-period", data="inicio"),
        html.Div(id="pat-cards", style={
            "display": "flex", "gap": "16px", "margin": "20px 0",
        }),
        dcc.Graph(id="graph-pl", config={"displayModeBar": False}),
        dcc.Graph(id="graph-cap", config={"displayModeBar": False}),
    ])


@app.callback(
    Output("pat-period", "data"),
    [Input({"type": "pat-btn", "index": v}, "n_clicks") for v in
     ["inicio", "ano", "12m", "1m"]],
    prevent_initial_call=True,
)
def pat_set_period(*clicks):
    ctx = callback_context
    if not ctx.triggered:
        return "inicio"
    prop = ctx.triggered[0]["prop_id"]
    key = json.loads(prop.split(".")[0])
    return key["index"]


@app.callback(
    [Output("pat-cards", "children"),
     Output("graph-pl", "figure"),
     Output("graph-cap", "figure")],
    [Input("pat-period", "data"),
     Input("graph-pl", "relayoutData"),
     Input("graph-cap", "relayoutData")],
    State("url", "pathname"),
)
def update_patrimonio(period, relay_pl, relay_cap, pathname):
    fund_key = _get_fund_key(pathname)
    if not fund_key:
        empty = go.Figure()
        empty.update_layout(**_base("Sem dados", 300))
        return [], empty, empty

    df_all = load_rent(fund_key)
    df = filter_df(df_all, period)
    if df.empty:
        empty = go.Figure()
        empty.update_layout(**_base("Sem dados", 300))
        return [], empty, empty

    df = df.copy()
    df["pl_mm"] = df["patrimonio"] / 1e6

    caps = [None]
    for i in range(1, len(df)):
        c = (df.iloc[i]["patrimonio"]
             - df.iloc[i - 1]["patrimonio"] * (1 + df.iloc[i]["rent_dia"] / 100))
        caps.append(c / 1e6)
    df["cap_mm"] = caps

    # ── Cards
    pl_atual = df["pl_mm"].iloc[-1]
    pl_atual_str = f"R$ {pl_atual:,.2f} MM".replace(",", "X").replace(".", ",").replace("X", ".")

    if len(df) >= 2:
        var_dia = df["pl_mm"].iloc[-1] - df["pl_mm"].iloc[-2]
    else:
        var_dia = 0.0
    sinal = "+" if var_dia >= 0 else ""
    var_dia_str = f"{sinal}R$ {var_dia:,.2f} MM".replace(",", "X").replace(".", ",").replace("X", ".")

    df_c = df.dropna(subset=["cap_mm"])
    cap_total = df_c["cap_mm"].sum()
    sinal_cap = "+" if cap_total >= 0 else ""
    cap_total_str = f"{sinal_cap}R$ {cap_total:,.2f} MM".replace(",", "X").replace(".", ",").replace("X", ".")

    cards = html.Div([
        _card("PL Atual", pl_atual_str),
        _card("Variação do Dia", var_dia_str),
        _card("Captação Total no Período", cap_total_str),
    ], style={"display": "flex", "gap": "16px"})

    # ── PL chart
    fig_pl = go.Figure(go.Scatter(
        x=df["data"], y=df["pl_mm"], mode="lines",
        line=dict(color=VERDE, width=2.5),
        fill="tozeroy", fillcolor="rgba(10,35,0,0.08)",
        hovertemplate="%{x|%d/%m/%Y}<br><b>R$ %{y:.2f} MM</b><extra></extra>",
    ))
    fig_pl.update_layout(**_base("Evolução do Patrimônio Líquido (R$ MM)", 380))
    fig_pl.update_xaxes(tickformat="%d/%m/%y", showgrid=True,
                        gridcolor=MARROM, gridwidth=0.5)
    fig_pl.update_yaxes(tickprefix="R$ ", ticksuffix=" MM",
                        showgrid=True, gridcolor=MARROM, gridwidth=0.5)

    # ── Captacao chart
    colors = ["#2ca44e" if v >= 0 else "#d93025" for v in df_c["cap_mm"]]
    fig_cap = go.Figure(go.Bar(
        x=df_c["data"], y=df_c["cap_mm"], marker_color=colors,
        hovertemplate="%{x|%d/%m/%Y}<br><b>R$ %{y:.2f} MM</b><extra></extra>",
    ))
    fig_cap.add_hline(y=0, line_width=0.8, line_color=VERDE)
    fig_cap.update_layout(**_base("Captação Líquida Estimada Diária (R$ MM)", 300))
    fig_cap.update_xaxes(tickformat="%d/%m/%y", showgrid=True,
                         gridcolor=MARROM, gridwidth=0.5)
    fig_cap.update_yaxes(tickprefix="R$ ", ticksuffix=" MM",
                         showgrid=True, gridcolor=MARROM, gridwidth=0.5)

    # ── Sync zoom
    ctx = callback_context
    triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""

    x_range = None
    if "graph-pl.relayoutData" in triggered and relay_pl:
        x_range = (relay_pl.get("xaxis.range[0]"), relay_pl.get("xaxis.range[1]"))
    elif "graph-cap.relayoutData" in triggered and relay_cap:
        x_range = (relay_cap.get("xaxis.range[0]"), relay_cap.get("xaxis.range[1]"))

    if x_range and x_range[0] and x_range[1]:
        fig_pl.update_xaxes(range=[x_range[0], x_range[1]])
        fig_cap.update_xaxes(range=[x_range[0], x_range[1]])

    return cards, fig_pl, fig_cap


# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 — RENTABILIDADE
# ══════════════════════════════════════════════════════════════════════════════

def _tab_rentabilidade_layout():
    return html.Div([
        _period_buttons("rent"),
        dcc.Store(id="rent-period", data="inicio"),
        dcc.Graph(id="graph-rent", config={"displayModeBar": False}),
        html.H4("Rentabilidade Mensal", style={
            "color": VERDE, "marginTop": "32px", "marginBottom": "14px",
            "fontSize": "16px", "fontFamily": FONT, "fontWeight": "bold",
        }),
        html.Div(id="rent-table-container"),
    ])


@app.callback(
    Output("rent-period", "data"),
    [Input({"type": "rent-btn", "index": v}, "n_clicks") for v in
     ["inicio", "ano", "12m", "1m"]],
    prevent_initial_call=True,
)
def rent_set_period(*clicks):
    ctx = callback_context
    if not ctx.triggered:
        return "inicio"
    prop = ctx.triggered[0]["prop_id"]
    key = json.loads(prop.split(".")[0])
    return key["index"]


def _cdi_diario(r):
    if pd.notna(r["pct_cdi_dia"]) and abs(r["pct_cdi_dia"]) > 1e-9:
        return r["rent_dia"] / (r["pct_cdi_dia"] / 100)
    return 0.0


@app.callback(
    [Output("graph-rent", "figure"), Output("rent-table-container", "children")],
    Input("rent-period", "data"),
    State("url", "pathname"),
)
def update_rentabilidade(period, pathname):
    fund_key = _get_fund_key(pathname)
    if not fund_key:
        empty = go.Figure()
        empty.update_layout(**_base("Sem dados", 300))
        return empty, html.P("Sem dados.")

    df_all = load_rent(fund_key)
    df = filter_df(df_all, period)
    if df.empty:
        empty = go.Figure()
        empty.update_layout(**_base("Sem dados", 300))
        return empty, html.P("Sem dados.")

    df = df.copy()
    df["rent_acum"] = (df["cota_liquida"] / df["cota_liquida"].iloc[0] - 1) * 100
    df["cdi_dia"] = df.apply(_cdi_diario, axis=1)
    fator = (1 + df["cdi_dia"] / 100).cumprod()
    df["cdi_acum"] = (fator / fator.iloc[0] - 1) * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["data"], y=df["rent_acum"], mode="lines",
        line=dict(color=VERDE, width=2.5), name="Fundo",
        hovertemplate="%{x|%d/%m/%Y}<br>Fundo: <b>%{y:.3f}%</b><extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["data"], y=df["cdi_acum"], mode="lines",
        line=dict(color=MARROM, width=2, dash="dot"), name="CDI",
        hovertemplate="%{x|%d/%m/%Y}<br>CDI: <b>%{y:.3f}%</b><extra></extra>",
    ))
    fig.update_layout(**_base("Rentabilidade Acumulada: Fundo vs CDI", 400, legend=True))
    fig.update_xaxes(tickformat="%d/%m/%y", showgrid=True,
                     gridcolor=MARROM, gridwidth=0.5)
    fig.update_yaxes(ticksuffix="%", showgrid=True,
                     gridcolor=MARROM, gridwidth=0.5)

    # ── Monthly table (always uses full data)
    df_full = df_all.copy()
    df_full["ano"] = df_full["data"].dt.year
    df_full["mes"] = df_full["data"].dt.month
    df_full["cdi_dia"] = df_full.apply(_cdi_diario, axis=1)

    monthly_cota = df_full.groupby(["ano", "mes"])["cota_liquida"].last().reset_index()
    monthly_cota = monthly_cota.sort_values(["ano", "mes"]).reset_index(drop=True)
    monthly_cota["rent_fundo"] = (
        monthly_cota["cota_liquida"] / monthly_cota["cota_liquida"].shift(1) - 1
    ) * 100

    monthly_groups = df_full.groupby(["ano", "mes"])
    cdi_monthly = {}
    for (ano, mes), grp in monthly_groups:
        fator_cdi = (1 + grp["cdi_dia"] / 100).prod()
        cdi_monthly[(ano, mes)] = (fator_cdi - 1) * 100

    years_sorted = sorted(monthly_cota["ano"].unique())
    fund_acum_by_year = {}
    cdi_acum_by_year = {}
    f_acum = 1.0
    c_acum = 1.0
    for ano in years_sorted:
        sub = monthly_cota[monthly_cota["ano"] == ano].sort_values("mes")
        for _, row in sub.iterrows():
            m = row["mes"]
            if pd.notna(row["rent_fundo"]):
                f_acum *= (1 + row["rent_fundo"] / 100)
            cv = cdi_monthly.get((ano, m))
            if cv is not None:
                c_acum *= (1 + cv / 100)
        fund_acum_by_year[ano] = (f_acum - 1) * 100
        cdi_acum_by_year[ano] = (c_acum - 1) * 100

    header_style = {
        "backgroundColor": VERDE, "color": PALHA,
        "fontWeight": "bold", "textAlign": "center",
        "fontSize": "12px", "fontFamily": FONT, "padding": "8px 6px",
        "border": f"1px solid {MARROM}",
    }

    all_years = sorted(monthly_cota["ano"].unique(), reverse=True)
    table_rows = []
    table_rows.append(html.Tr([
        html.Th("Ano", style=header_style),
        html.Th("", style=header_style),
    ] + [html.Th(nm, style=header_style) for nm in MESES.values()] + [
        html.Th("Ano", style=header_style),
        html.Th("Acum.", style=header_style),
    ]))

    for idx_year, ano in enumerate(all_years):
        sub = monthly_cota[monthly_cota["ano"] == ano].sort_values("mes")
        bg_fundo = PALHA if idx_year % 2 == 0 else "#f5e6cd"
        bg_cdi = "#f5e6cd" if idx_year % 2 == 0 else "#eddcbc"

        fund_year = 1.0
        cdi_year = 1.0
        fundo_cells = []
        cdi_cells = []

        for m, nm in MESES.items():
            row_m = sub[sub["mes"] == m]
            cdi_val = cdi_monthly.get((ano, m))

            if not row_m.empty and pd.notna(row_m["rent_fundo"].values[0]):
                fv = row_m["rent_fundo"].values[0]
                fundo_cells.append(html.Td(
                    f"{fv:.2f}%".replace(".", ","),
                    style={"textAlign": "center", "padding": "6px 4px",
                           "fontSize": "12px", "border": f"1px solid {MARROM}",
                           "backgroundColor": bg_fundo}
                ))
                fund_year *= (1 + fv / 100)
            else:
                fundo_cells.append(html.Td(
                    "\u2014",
                    style={"textAlign": "center", "padding": "6px 4px",
                           "fontSize": "12px", "border": f"1px solid {MARROM}",
                           "backgroundColor": bg_fundo}
                ))
                fv = None

            if fv is not None and cdi_val is not None and abs(cdi_val) > 1e-9:
                pct = fv / cdi_val * 100
                if pct > 100:
                    cell_bg = "#d4edda"
                elif pct < 100:
                    cell_bg = "#f8d7da"
                else:
                    cell_bg = bg_cdi
                cdi_cells.append(html.Td(
                    f"{pct:.2f}%".replace(".", ","),
                    style={"textAlign": "center", "padding": "6px 4px",
                           "fontSize": "12px", "fontWeight": "bold",
                           "fontStyle": "italic",
                           "border": f"1px solid {MARROM}",
                           "backgroundColor": cell_bg}
                ))
                cdi_year *= (1 + cdi_val / 100)
            else:
                cdi_cells.append(html.Td(
                    "\u2014",
                    style={"textAlign": "center", "padding": "6px 4px",
                           "fontSize": "12px", "fontWeight": "bold",
                           "fontStyle": "italic",
                           "border": f"1px solid {MARROM}",
                           "backgroundColor": bg_cdi}
                ))
                if cdi_val is not None:
                    cdi_year *= (1 + cdi_val / 100)

        fund_yr_ret = (fund_year - 1) * 100
        cdi_yr_ret = (cdi_year - 1) * 100

        fund_yr_str = f"{fund_yr_ret:.2f}%".replace(".", ",") if fund_yr_ret != 0 else "\u2014"
        fa = fund_acum_by_year.get(ano, 0)
        fund_acum_str = f"{fa:.2f}%".replace(".", ",")

        if abs(cdi_yr_ret) > 1e-9:
            pct_yr = fund_yr_ret / cdi_yr_ret * 100
            cdi_yr_str = f"{pct_yr:.2f}%".replace(".", ",")
            yr_bg = "#d4edda" if pct_yr > 100 else ("#f8d7da" if pct_yr < 100 else bg_cdi)
        else:
            cdi_yr_str = "\u2014"
            yr_bg = bg_cdi

        ca = cdi_acum_by_year.get(ano, 0)
        if abs(ca) > 1e-9:
            pct_acum = fa / ca * 100
            cdi_acum_str = f"{pct_acum:.2f}%".replace(".", ",")
            acum_bg = "#d4edda" if pct_acum > 100 else ("#f8d7da" if pct_acum < 100 else bg_cdi)
        else:
            cdi_acum_str = "\u2014"
            acum_bg = bg_cdi

        cell_base = {"fontFamily": FONT}
        ano_cell_style = {
            **cell_base, "textAlign": "center", "fontWeight": "bold",
            "padding": "6px 8px", "fontSize": "13px",
            "border": f"1px solid {MARROM}", "backgroundColor": bg_fundo,
            "verticalAlign": "middle",
        }
        tipo_style_fundo = {
            **cell_base, "textAlign": "center", "fontWeight": "bold",
            "padding": "6px 4px", "fontSize": "11px",
            "border": f"1px solid {MARROM}", "backgroundColor": bg_fundo,
        }
        tipo_style_cdi = {
            **cell_base, "textAlign": "center", "fontWeight": "bold",
            "fontStyle": "italic", "padding": "6px 4px", "fontSize": "11px",
            "border": f"1px solid {MARROM}", "backgroundColor": bg_cdi,
        }

        fundo_row = html.Tr([
            html.Td(str(ano), rowSpan=2, style=ano_cell_style),
            html.Td("Fundo", style=tipo_style_fundo),
        ] + fundo_cells + [
            html.Td(fund_yr_str, style={
                "textAlign": "center", "padding": "6px 4px", "fontWeight": "bold",
                "fontSize": "12px", "border": f"1px solid {MARROM}",
                "backgroundColor": bg_fundo}),
            html.Td(fund_acum_str, style={
                "textAlign": "center", "padding": "6px 4px", "fontWeight": "bold",
                "fontSize": "12px", "border": f"1px solid {MARROM}",
                "backgroundColor": bg_fundo, "color": VERDE}),
        ])

        cdi_row = html.Tr([
            html.Td("% CDI", style=tipo_style_cdi),
        ] + cdi_cells + [
            html.Td(cdi_yr_str, style={
                "textAlign": "center", "padding": "6px 4px",
                "fontWeight": "bold", "fontStyle": "italic",
                "fontSize": "12px", "border": f"1px solid {MARROM}",
                "backgroundColor": yr_bg}),
            html.Td(cdi_acum_str, style={
                "textAlign": "center", "padding": "6px 4px",
                "fontWeight": "bold", "fontStyle": "italic",
                "fontSize": "12px", "border": f"1px solid {MARROM}",
                "backgroundColor": acum_bg}),
        ])

        table_rows.append(fundo_row)
        table_rows.append(cdi_row)

    tabela = html.Table(table_rows, style={
        "borderCollapse": "collapse", "width": "100%",
        "fontFamily": FONT, "fontSize": "12px",
    })

    return fig, tabela


# ══════════════════════════════════════════════════════════════════════════════
# ABA 3 — CARTEIRA
# ══════════════════════════════════════════════════════════════════════════════

def _tab_carteira_layout(fund_key):
    datas = get_datas(fund_key)
    return html.Div([
        html.Div([
            html.Label("Data:", style={
                "fontWeight": "bold", "color": VERDE,
                "marginRight": "12px", "fontFamily": FONT, "fontSize": "14px",
            }),
            dcc.Dropdown(
                id="dd-data",
                options=[{"label": d, "value": d} for d in datas],
                value=datas[0] if datas else None,
                clearable=False,
                style={"width": "220px", "fontFamily": FONT},
            ),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "24px"}),
        html.Div(id="carteira-content"),
    ])


@app.callback(
    Output("carteira-content", "children"),
    Input("dd-data", "value"),
    State("url", "pathname"),
)
def update_carteira(data, pathname):
    fund_key = _get_fund_key(pathname)
    if not fund_key or not data:
        return html.P("Nenhuma data disponível.", style={"color": VERDE})

    df = load_titulos(data, fund_key)
    if df.empty:
        return html.P(f"Nenhum título privado para {data}.", style={"color": VERDE})

    # Patrimonio dos Masters (somado)
    patrimonio = load_patrimonio_carteira(data, fund_key)

    def get_ticker(titulo):
        return str(titulo)[:6].upper()

    def fmt_taxa(idx_label, coupon):
        if pd.isna(coupon) or coupon == 0:
            return idx_label
        c = f"{coupon:.2f}".replace(".", ",")
        if "IPCA" in idx_label:
            return f"IPCA + {c}%"
        if "CDI" in idx_label:
            return f"CDI + {c}%"
        if "Prefixado" in idx_label or "PRE" in idx_label.upper():
            return f"PRE {c}%"
        return f"{c}%"

    rows = []
    total_fin = 0.0
    for _, r in df.iterrows():
        idx = _get_indexador(r.get("sr_indexador"), r["titulo"])
        fin = r["financeiro"]
        pct = (fin / patrimonio * 100) if patrimonio else 0
        total_fin += fin
        rows.append({
            "Ticker": get_ticker(r["titulo"]),
            "Emissor": r["emissor"],
            "Setor": r["setor"] if pd.notna(r.get("setor")) else "N/A",
            "Rating": r["rating"] if pd.notna(r.get("rating")) else "N/A",
            "Taxa": fmt_taxa(idx, r["coupon"]),
            "Financeiro (R$ mil)": _fmt_fin_mil(fin),
            "% PL": _fmt_pct(pct),
            "_fin": fin,
            "_pct": pct,
            "_titulo": str(r["titulo"]),
            "_indexador": idx,
            "_type": "normal",
        })

    rows.sort(key=lambda x: -x["_fin"])

    # Caixa
    caixa = load_caixa(data, fund_key)
    caixa_pct = (caixa / patrimonio * 100) if patrimonio else 0
    rows.append({
        "Ticker": "", "Emissor": "Caixa", "Setor": "", "Rating": "", "Taxa": "",
        "Financeiro (R$ mil)": _fmt_fin_mil(caixa),
        "% PL": _fmt_pct(caixa_pct),
        "_fin": caixa, "_pct": caixa_pct,
        "_titulo": "Caixa", "_indexador": "CDI+", "_type": "caixa",
    })

    # Despesas
    desp = load_despesas(data, fund_key)
    desp_pct = (desp / patrimonio * 100) if patrimonio else 0
    rows.append({
        "Ticker": "", "Emissor": "Despesas", "Setor": "", "Rating": "", "Taxa": "",
        "Financeiro (R$ mil)": _fmt_fin_mil(desp),
        "% PL": _fmt_pct(desp_pct),
        "_fin": desp, "_pct": desp_pct,
        "_titulo": "Despesas", "_indexador": "", "_type": "despesas",
    })

    # TOTAL
    total_all = total_fin + caixa + desp
    total_pct = sum(r["_pct"] for r in rows)

    rows.append({
        "Ticker": "TOTAL", "Emissor": "", "Setor": "", "Rating": "", "Taxa": "",
        "Financeiro (R$ mil)": _fmt_fin_mil(total_all),
        "% PL": _fmt_pct(total_pct),
        "_fin": total_all, "_pct": total_pct, "_type": "total",
    })

    visible_cols = ["Ticker", "Emissor", "Setor", "Rating", "Taxa",
                    "Financeiro (R$ mil)", "% PL"]
    tbl_data = [{k: r[k] for k in visible_cols} for r in rows]

    caixa_idx = len(rows) - 3
    desp_idx = len(rows) - 2
    total_idx = len(rows) - 1

    style_cond = [
        {"if": {"row_index": "even"}, "backgroundColor": PALHA},
        {"if": {"row_index": "odd"}, "backgroundColor": "#f5e6cd"},
        {"if": {"row_index": caixa_idx},
         "backgroundColor": VERDE, "color": PALHA, "fontWeight": "bold"},
        {"if": {"row_index": desp_idx},
         "backgroundColor": VERDE, "color": PALHA, "fontWeight": "bold"},
        {"if": {"row_index": total_idx},
         "backgroundColor": VERDE, "color": PALHA, "fontWeight": "bold"},
    ]

    tabela = _DataTable(
        data=tbl_data,
        columns=[{"name": c, "id": c} for c in visible_cols],
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": VERDE, "color": PALHA,
            "fontWeight": "bold", "textAlign": "center",
            "fontSize": "12px", "fontFamily": FONT, "padding": "8px",
        },
        style_cell={
            "textAlign": "center", "fontFamily": FONT,
            "fontSize": "12px", "padding": "7px 10px",
            "border": f"1px solid {MARROM}",
        },
        style_cell_conditional=[
            {"if": {"column_id": "Emissor"}, "textAlign": "left", "minWidth": "200px"},
            {"if": {"column_id": "Taxa"}, "textAlign": "left"},
        ],
        style_data_conditional=style_cond,
        page_size=9999,
    )

    # ── Pie chart — % por Emissor
    priv = [r for r in rows if r["_type"] == "normal"]
    em_data = {}
    for r in priv:
        em_data[r["Emissor"]] = em_data.get(r["Emissor"], 0) + r["_fin"]
    em_sorted = sorted(em_data.items(), key=lambda x: -x[1])
    em_labels = [x[0] for x in em_sorted]
    em_values = [x[1] for x in em_sorted]

    fig_em = go.Figure(go.Pie(
        labels=em_labels, values=em_values, hole=0.38,
        textinfo="percent", textfont_size=11,
        marker_colors=PIE_COLORS[:len(em_labels)],
        hovertemplate="%{label}<br>R$ %{value:,.0f}<br>%{percent}<extra></extra>",
        sort=False, direction="clockwise", rotation=90,
    ))
    kw_em = _base("% por Emissor", 420, legend=True)
    kw_em["legend"] = dict(font=dict(size=9), x=1.02, y=0.5)
    fig_em.update_layout(**kw_em)

    # ── Pie chart — % por Indexador (uses ref_setor_rating.indexador)
    ix_data = {}
    for r in priv:
        ix_data[r["_indexador"]] = ix_data.get(r["_indexador"], 0) + r["_fin"]
    ix_data["CDI+"] = ix_data.get("CDI+", 0) + caixa
    total_ix = sum(ix_data.values())
    ix_sorted = sorted(ix_data.items(), key=lambda x: -x[1])
    ix_labels = [x[0] for x in ix_sorted]
    ix_values = [(x[1] / total_ix * 100) if total_ix else 0 for x in ix_sorted]

    fig_ix = go.Figure(go.Pie(
        labels=ix_labels, values=ix_values, hole=0.4,
        textinfo="percent", textfont_size=11,
        marker_colors=PIE_COLORS[:len(ix_labels)],
        hovertemplate="%{label}<br>%{percent}<extra></extra>",
        sort=False, direction="clockwise", rotation=90,
    ))
    kw_ix = _base("% por Indexador", 420, legend=True)
    kw_ix["legend"] = dict(font=dict(size=9), x=1.02, y=0.5)
    fig_ix.update_layout(**kw_ix)

    # ── Horizontal blocks — % PL por Rating
    rating_order = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-",
                    "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
                    "B+", "B", "B-", "S/R"]
    priv_for_rating = [r for r in priv]
    rt_data = {}
    for r in priv_for_rating:
        rating = r["Rating"] if r["Rating"] != "N/A" else "S/R"
        rt_data[rating] = rt_data.get(rating, 0) + r["_pct"]
    rt_sorted = sorted(rt_data.items(),
                       key=lambda x: rating_order.index(x[0]) if x[0] in rating_order else 99)

    _rt_colors = PIE_COLORS + ["#5c4a32", "#3d6b1e", "#c9b896", "#6b8e23",
                                "#deb887", "#556b2f", "#8b6914", "#4a7c59"]
    fig_rt = go.Figure()
    for i, (rating, pct) in enumerate(rt_sorted):
        bg = _rt_colors[i % len(_rt_colors)].lstrip("#")
        rv, gv, bv = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
        txt_c = "white" if (0.299 * rv + 0.587 * gv + 0.114 * bv) < 150 else VERDE
        fig_rt.add_trace(go.Bar(
            y=[""], x=[pct], name=rating, orientation="h",
            text=f"{rating} {pct:.1f}%".replace(".", ","),
            textposition="inside", insidetextanchor="middle",
            textfont=dict(size=11, color=txt_c),
            marker_color=_rt_colors[i % len(_rt_colors)],
            hovertemplate=f"{rating}: <b>{pct:.2f}%</b><extra></extra>",
        ))
    fig_rt.update_layout(barmode="stack",
                         **_base("Exposição por Rating (% PL)", 180, legend=True))
    fig_rt.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.08,
                    xanchor="center", x=0.5, font=dict(size=10)),
        margin=dict(t=80, b=20, l=30, r=30),
    )
    fig_rt.update_xaxes(ticksuffix="%", showgrid=False, visible=False)
    fig_rt.update_yaxes(showticklabels=False)

    # ── Pie chart — % por Setor
    st_data = {}
    for r in priv:
        setor = r["Setor"] if r["Setor"] not in ("N/A", "", None) else "Outros"
        st_data[setor] = st_data.get(setor, 0) + r["_pct"]
    st_sorted = sorted(st_data.items(), key=lambda x: -x[1])
    st_labels = [x[0] for x in st_sorted]
    st_values = [x[1] for x in st_sorted]

    fig_st = go.Figure(go.Pie(
        labels=st_labels, values=st_values, hole=0.38,
        textinfo="percent", textfont_size=11,
        marker_colors=PIE_COLORS[:len(st_labels)],
        hovertemplate="%{label}<br>%{percent}<extra></extra>",
        sort=False, direction="clockwise", rotation=90,
    ))
    kw_st = _base("% por Setor", 420, legend=True)
    kw_st["legend"] = dict(font=dict(size=9), x=1.02, y=0.5)
    fig_st.update_layout(**kw_st)

    return html.Div([
        tabela,
        html.Div([
            html.Div(dcc.Graph(figure=fig_em, config={"displayModeBar": False}),
                     style={"flex": "1"}),
            html.Div(dcc.Graph(figure=fig_ix, config={"displayModeBar": False}),
                     style={"flex": "1"}),
        ], style={"display": "flex", "gap": "16px", "marginTop": "28px"}),
        html.Div([
            html.Div(dcc.Graph(figure=fig_rt, config={"displayModeBar": False}),
                     style={"flex": "1"}),
            html.Div(dcc.Graph(figure=fig_st, config={"displayModeBar": False}),
                     style={"flex": "1"}),
        ], style={"display": "flex", "gap": "16px", "marginTop": "28px"}),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# ABA 4 — MAPA MENSAL
# ══════════════════════════════════════════════════════════════════════════════

def _ultimo_du_mes_anterior(fund_key):
    cfg = FUNDS[fund_key]
    con = _conn()
    df = pd.read_sql(
        "SELECT DISTINCT data FROM fact_rentabilidade "
        "WHERE fundo=? ORDER BY data DESC",
        con, params=(cfg["rent_fundo"],))
    con.close()
    if df.empty:
        return None
    df["data"] = pd.to_datetime(df["data"])
    hoje = pd.Timestamp.today().normalize()
    mes_atual_start = pd.Timestamp(hoje.year, hoje.month, 1)
    anteriores = df[df["data"] < mes_atual_start]
    if anteriores.empty:
        return df["data"].max().strftime("%Y-%m-%d")
    return anteriores["data"].max().strftime("%Y-%m-%d")


def _ultimo_du_do_mes(ano, mes, fund_key):
    cfg = FUNDS[fund_key]
    masters = cfg["carteira_fundos"]
    ph, params = _in_clause(masters)
    con = _conn()
    df = pd.read_sql(
        f"SELECT MAX(data) as d FROM fact_titulos_privados "
        f"WHERE data LIKE ? AND fundo IN ({ph})",
        con, params=(f"{ano:04d}-{mes:02d}-%", *params))
    con.close()
    if df.empty or df["d"].iloc[0] is None:
        return None
    return df["d"].iloc[0]


def _tab_mapa_mensal_layout(fund_key):
    default_date = _ultimo_du_mes_anterior(fund_key)
    return html.Div([
        html.Div([
            html.Label("Data de Referência:", style={
                "fontWeight": "bold", "color": VERDE,
                "marginRight": "12px", "fontFamily": FONT, "fontSize": "14px",
            }),
            dcc.DatePickerSingle(
                id="mapa-data-ref",
                date=default_date,
                display_format="DD/MM/YYYY",
                style={"fontFamily": FONT},
            ),
        ], style={"display": "flex", "alignItems": "center",
                  "marginBottom": "24px"}),
        html.Div(id="mapa-mensal-content"),
    ])


@app.callback(
    Output("mapa-mensal-content", "children"),
    Input("mapa-data-ref", "date"),
    State("url", "pathname"),
)
def update_mapa_mensal(data_ref, pathname):
    fund_key = _get_fund_key(pathname)
    if not fund_key or not data_ref:
        return html.P("Selecione uma data de referência.", style={"color": VERDE})

    cfg = FUNDS[fund_key]
    masters = cfg["carteira_fundos"]
    ph, params = _in_clause(masters)
    data_ref_dt = pd.Timestamp(data_ref)
    ano_ref = data_ref_dt.year
    mes_ref = data_ref_dt.month

    # ── Ultimo DU do mes de data_ref e do mes anterior
    ultimo_du_ref = _ultimo_du_do_mes(ano_ref, mes_ref, fund_key)
    if mes_ref == 1:
        ano_ant, mes_ant = ano_ref - 1, 12
    else:
        ano_ant, mes_ant = ano_ref, mes_ref - 1
    ultimo_du_ant = _ultimo_du_do_mes(ano_ant, mes_ant, fund_key)

    qtd_ant_label = (
        f"Qtd Anterior ({pd.Timestamp(ultimo_du_ant).strftime('%d/%m/%Y')})"
        if ultimo_du_ant else "Qtd Anterior"
    )
    qtd_ref_label = (
        f"Qtd Atual ({pd.Timestamp(ultimo_du_ref).strftime('%d/%m/%Y')})"
        if ultimo_du_ref else "Qtd Atual"
    )

    # ── Dados de rentabilidade (do FIC para D60)
    con = _conn()
    rent_mes_df = pd.read_sql(
        "SELECT rent_mes FROM fact_rentabilidade "
        "WHERE data = ? AND fundo=?",
        con, params=(ultimo_du_ref or data_ref, cfg["rent_fundo"]))
    rent_mes_val = rent_mes_df["rent_mes"].iloc[0] if (
        not rent_mes_df.empty and pd.notna(rent_mes_df["rent_mes"].iloc[0])
    ) else 0.0

    # Patrimonio dos Masters (somado)
    pat_df = pd.read_sql(
        f"SELECT SUM(patrimonio) as patrimonio FROM fact_rentabilidade "
        f"WHERE data = ? AND fundo IN ({ph})",
        con, params=(ultimo_du_ref or data_ref, *params))
    patrimonio = pat_df["patrimonio"].iloc[0] if not pat_df.empty and pat_df["patrimonio"].iloc[0] else 0.0

    # Captacao e resgates do mes (do FIC)
    fluxo_df = pd.read_sql(
        "SELECT aquisicao, resgate FROM fact_rentabilidade "
        "WHERE data LIKE ? AND fundo=?",
        con, params=(f"{ano_ref:04d}-{mes_ref:02d}-%", cfg["rent_fundo"]))
    cap_liquida = (fluxo_df["aquisicao"].fillna(0).sum()
                   - fluxo_df["resgate"].fillna(0).sum())
    resgates = fluxo_df["resgate"].fillna(0).sum()

    # ── Titulos privados (dos Masters — raw, sem GROUP BY para ter fundo-level detail)
    tp_ref = pd.read_sql(
        f"SELECT t.isin, t.titulo, t.emissor, t.quantidade, t.financeiro, t.pct_pl, "
        f"       t.ganho, t.rent_cdi, t.estrategia "
        f"FROM fact_titulos_privados t "
        f"WHERE t.data = ? AND t.fundo IN ({ph})",
        con, params=(ultimo_du_ref or data_ref, *params))
    tp_ant = pd.read_sql(
        f"SELECT t.isin, t.titulo, t.emissor, t.quantidade, t.financeiro, t.pct_pl "
        f"FROM fact_titulos_privados t "
        f"WHERE t.data = ? AND t.fundo IN ({ph})",
        con, params=(ultimo_du_ant, *params)) if ultimo_du_ant else pd.DataFrame()
    con.close()

    sections = []

    # ══════════════════════════════════════════════════════════════════
    # SECAO 1 — Principais Mudancas de Posicao
    # ══════════════════════════════════════════════════════════════════
    sections.append(_section_title("Principais Mudanças de Posição"))

    if tp_ref.empty:
        sections.append(html.P("Sem dados de títulos privados para a data.",
                               style={"color": VERDE}))
    else:
        def _ticker(titulo):
            return str(titulo).split()[0].upper() if pd.notna(titulo) else ""

        # Aggregate by ISIN (for multi-master dedup)
        ref_grp = tp_ref.groupby("isin").agg({
            "titulo": "first", "emissor": "first",
            "quantidade": "sum", "financeiro": "sum", "pct_pl": "sum",
        }).reset_index()
        ref_grp["ticker"] = ref_grp["titulo"].apply(_ticker)

        if not tp_ant.empty:
            ant_grp = tp_ant.groupby("isin").agg({
                "quantidade": "sum",
            }).reset_index().rename(columns={"quantidade": "qtd_ant"})
        else:
            ant_grp = pd.DataFrame(columns=["isin", "qtd_ant"])

        merged = ref_grp.merge(ant_grp, on="isin", how="outer")
        merged["qtd_ant"] = merged["qtd_ant"].fillna(0)
        merged["quantidade"] = merged["quantidade"].fillna(0)
        merged["variacao"] = merged["quantidade"] - merged["qtd_ant"]

        if not tp_ant.empty:
            ant_info = tp_ant.groupby("isin").agg({
                "titulo": "first", "emissor": "first",
            }).reset_index()
            for col in ["titulo", "emissor"]:
                mask = merged[col].isna()
                if mask.any():
                    info_map = ant_info.set_index("isin")[col]
                    merged.loc[mask, col] = merged.loc[mask, "isin"].map(info_map)
            merged["ticker"] = merged["titulo"].apply(
                lambda x: str(x).split()[0].upper() if pd.notna(x) else "")

        changed = merged[merged["variacao"].abs() > 0.01].copy()

        if changed.empty:
            sections.append(html.P("Nenhuma mudança de posição no período.",
                                   style={"color": VERDE}))
        else:
            changed["financeiro"] = changed["financeiro"].fillna(0)
            changed["pct_pl"] = changed["pct_pl"].fillna(0)
            changed["abs_var"] = changed["variacao"].abs()
            changed = changed.sort_values("abs_var", ascending=False)

            def _tipo(row):
                if row["qtd_ant"] == 0:
                    return "Nova Posição"
                if row["quantidade"] == 0:
                    return "Zerada"
                if row["quantidade"] > row["qtd_ant"]:
                    return "Aumento"
                return "Redução"

            changed["Tipo"] = changed.apply(_tipo, axis=1)

            tbl_data = []
            for _, r in changed.iterrows():
                tbl_data.append({
                    "Ticker": r.get("ticker", ""),
                    "Emissor": r.get("emissor", ""),
                    qtd_ant_label: f"{r['qtd_ant']:,.0f}".replace(",", "."),
                    qtd_ref_label: f"{r['quantidade']:,.0f}".replace(",", "."),
                    "Variação Qtd": f"{r['variacao']:+,.0f}".replace(",", "."),
                    "Financeiro Atual (R$ MM)": f"{r['financeiro'] / 1e6:,.4f}".replace(",", "X").replace(".", ",").replace("X", "."),
                    "% PL": f"{r['pct_pl'] * 100:.2f}%".replace(".", ","),
                    "Tipo": r["Tipo"],
                })

            tipo_colors = {
                "Nova Posição": "#d4edda",
                "Zerada": "#f8d7da",
                "Aumento": "#e8f5e9",
                "Redução": "#fff3e0",
            }
            style_data_cond = []
            for tipo, cor in tipo_colors.items():
                style_data_cond.append({
                    "if": {"filter_query": '{Tipo} = "' + tipo + '"'},
                    "backgroundColor": cor,
                })

            cols_mudanca = ["Ticker", "Emissor", qtd_ant_label, qtd_ref_label,
                            "Variação Qtd", "Financeiro Atual (R$ MM)",
                            "% PL", "Tipo"]
            sections.append(_DataTable(
                data=tbl_data,
                columns=[{"name": c, "id": c} for c in cols_mudanca],
                style_table={"overflowX": "auto"},
                style_header={
                    "backgroundColor": VERDE, "color": PALHA,
                    "fontWeight": "bold", "textAlign": "center",
                    "fontSize": "12px", "fontFamily": FONT, "padding": "8px",
                },
                style_cell={
                    "textAlign": "center", "fontFamily": FONT,
                    "fontSize": "12px", "padding": "7px 10px",
                    "border": f"1px solid {MARROM}",
                    "userSelect": "text",
                },
                style_cell_conditional=[
                    {"if": {"column_id": "Emissor"}, "textAlign": "left",
                     "minWidth": "180px"},
                ],
                style_data_conditional=style_data_cond,
                page_size=9999,
            ))

    # ══════════════════════════════════════════════════════════════════
    # SECAO 2 — AUM
    # ══════════════════════════════════════════════════════════════════
    sections.append(_section_title("AUM"))

    sections.append(html.Div([
        _card("PL do Fundo (R$ MM)", _fmt_brl(patrimonio)),
        _card("Captação Líquida no Mês (R$ MM)", _fmt_brl(cap_liquida)),
        _card("Resgates no Mês (R$ MM)", _fmt_brl(resgates)),
    ], style={"display": "flex", "gap": "16px"}))

    # ══════════════════════════════════════════════════════════════════
    # SECAO 3 — Atribuicao de Performance
    # ══════════════════════════════════════════════════════════════════
    sections.append(_section_title("Atribuição de Performance"))

    if tp_ref.empty or tp_ref["ganho"].fillna(0).abs().sum() < 0.01:
        sections.append(html.P(
            "Dados de ganho indisponíveis ou zerados para esta data.",
            style={"color": VERDE, "fontStyle": "italic"}))
    else:
        # Aggregate ganho by emissor (across masters)
        ganho_grp = tp_ref.groupby("emissor").agg(
            {"ganho": "sum", "financeiro": "sum"}).reset_index()
        ganho_grp["ganho_mm"] = ganho_grp["ganho"] / 1e6
        ganho_grp["pct_pl"] = (ganho_grp["ganho"] / patrimonio * 100
                                if patrimonio else 0)

        top3_pos = ganho_grp[ganho_grp["ganho"] > 0].nlargest(3, "ganho")
        top3_neg = ganho_grp[ganho_grp["ganho"] < 0].nsmallest(3, "ganho")

        def _attr_table(title, df_attr):
            if df_attr.empty:
                return html.Div([
                    html.H5(title, style={"color": VERDE, "fontFamily": FONT,
                                          "fontSize": "13px", "fontWeight": "bold"}),
                    html.P("Nenhum registro.", style={"color": VERDE,
                                                      "fontStyle": "italic"}),
                ], style={"flex": "1"})
            attr_rows = []
            for _, r in df_attr.iterrows():
                attr_rows.append({
                    "Emissor": r["emissor"],
                    "Ganho (R$ MM)": f"{r['ganho_mm']:+,.4f}".replace(",", "X").replace(".", ",").replace("X", "."),
                    "% PL": f"{r['pct_pl']:+.4f}%".replace(".", ","),
                })
            cols = ["Emissor", "Ganho (R$ MM)", "% PL"]
            return html.Div([
                html.H5(title, style={"color": VERDE, "fontFamily": FONT,
                                      "fontSize": "13px", "fontWeight": "bold",
                                      "marginBottom": "8px"}),
                _DataTable(
                    data=attr_rows,
                    columns=[{"name": c, "id": c} for c in cols],
                    style_header={
                        "backgroundColor": VERDE, "color": PALHA,
                        "fontWeight": "bold", "textAlign": "center",
                        "fontSize": "12px", "fontFamily": FONT, "padding": "8px",
                    },
                    style_cell={
                        "textAlign": "center", "fontFamily": FONT,
                        "fontSize": "12px", "padding": "7px 10px",
                        "border": f"1px solid {MARROM}",
                        "userSelect": "text",
                    },
                    style_cell_conditional=[
                        {"if": {"column_id": "Emissor"}, "textAlign": "left",
                         "minWidth": "200px"},
                    ],
                    page_size=9999,
                ),
            ], style={"flex": "1"})

        sections.append(html.Div([
            _attr_table("Top 3 Contribuidores", top3_pos),
            _attr_table("Top 3 Detratores", top3_neg),
        ], style={"display": "flex", "gap": "24px"}))

    # ══════════════════════════════════════════════════════════════════
    # SECAO 4 — Exposicoes
    # ══════════════════════════════════════════════════════════════════
    sections.append(_section_title("Exposições"))

    if tp_ref.empty:
        sections.append(html.P("Sem dados de exposição.", style={"color": VERDE}))
    else:
        # Aggregate by ISIN for exposure calcs
        tp_agg = tp_ref.groupby("isin").agg({
            "titulo": "first", "emissor": "first",
            "financeiro": "sum", "pct_pl": "sum",
        }).reset_index()

        exp_cp = tp_agg["pct_pl"].sum() * 100
        n_emissoes = tp_agg["isin"].nunique()

        # Carrego medio: show "–" because rent_cdi data is unreliable
        carrego_str = "\u2013"

        sections.append(html.Div([
            _card("Exposição Crédito Privado",
                  f"{exp_cp:.2f}%".replace(".", ",")),
            _card("Nº de Emissões", str(n_emissoes)),
            _card("Carrego Médio (% CDI)", carrego_str),
        ], style={"display": "flex", "gap": "16px", "marginBottom": "20px"}))

        # Top 5 posicoes
        top5 = tp_agg.nlargest(5, "pct_pl")
        top5_data = []
        for _, r in top5.iterrows():
            tk = str(r["titulo"]).split()[0].upper() if pd.notna(r["titulo"]) else ""
            top5_data.append({
                "Ticker": tk,
                "Emissor": r["emissor"],
                "% PL": f"{r['pct_pl'] * 100:.2f}%".replace(".", ","),
            })
        sections.append(html.H5("Top 5 Posições", style={
            "color": VERDE, "fontFamily": FONT, "fontSize": "13px",
            "fontWeight": "bold", "marginBottom": "8px"}))
        sections.append(_DataTable(
            data=top5_data,
            columns=[{"name": c, "id": c} for c in ["Ticker", "Emissor", "% PL"]],
            style_header={
                "backgroundColor": VERDE, "color": PALHA,
                "fontWeight": "bold", "textAlign": "center",
                "fontSize": "12px", "fontFamily": FONT, "padding": "8px",
            },
            style_cell={
                "textAlign": "center", "fontFamily": FONT,
                "fontSize": "12px", "padding": "7px 10px",
                "border": f"1px solid {MARROM}",
                "userSelect": "text",
            },
            style_cell_conditional=[
                {"if": {"column_id": "Emissor"}, "textAlign": "left",
                 "minWidth": "200px"},
            ],
            page_size=9999,
        ))

        # % PL por Indexador (rosca) — uses ref_setor_rating.indexador
        con_ix = _conn()
        tp_ref_ix = pd.read_sql(
            f"SELECT t.titulo, t.pct_pl, t.isin, t.emissor, "
            f"       sr.indexador AS sr_indexador "
            f"FROM fact_titulos_privados t "
            f"LEFT JOIN ref_setor_rating sr "
            f"  ON sr.codigo = UPPER(SUBSTR(t.titulo, 1, 6)) "
            f"WHERE t.data = ? AND t.fundo IN ({ph})",
            con_ix, params=(ultimo_du_ref or data_ref, *params))
        con_ix.close()

        # Aggregate by ISIN first, then classify
        if not tp_ref_ix.empty:
            ix_agg = tp_ref_ix.groupby("isin").agg({
                "titulo": "first", "emissor": "first",
                "pct_pl": "sum", "sr_indexador": "first",
            }).reset_index()
            ix_agg["indexador"] = ix_agg.apply(
                lambda r: _get_indexador(r["sr_indexador"], r["titulo"]),
                axis=1,
            )
            idx_grp = ix_agg.groupby("indexador")["pct_pl"].sum().reset_index()
            idx_grp["pct_pl"] = idx_grp["pct_pl"] * 100
            idx_grp = idx_grp.sort_values("pct_pl", ascending=False)
        else:
            idx_grp = pd.DataFrame(columns=["indexador", "pct_pl"])

        if not idx_grp.empty:
            fig_idx = go.Figure(go.Pie(
                labels=idx_grp["indexador"], values=idx_grp["pct_pl"], hole=0.4,
                textinfo="percent", textfont_size=11,
                marker_colors=PIE_COLORS[:len(idx_grp)],
                hovertemplate="%{label}<br>%{percent}<extra></extra>",
                sort=False, direction="clockwise", rotation=90,
            ))
            kw_idx = _base("% PL por Indexador", 280, legend=True)
            kw_idx["legend"] = dict(font=dict(size=9), x=1.02, y=0.5)
            fig_idx.update_layout(**kw_idx)
            chart_idx = dcc.Graph(figure=fig_idx, config={"displayModeBar": False})
        else:
            chart_idx = html.P("Sem dados de indexador.", style={"color": VERDE})

        # % PL por Rating
        con_rt = _conn()
        tp_ref_rt = pd.read_sql(
            f"SELECT t.titulo, t.pct_pl, t.isin, sr.rating "
            f"FROM fact_titulos_privados t "
            f"LEFT JOIN ref_setor_rating sr "
            f"  ON sr.codigo = UPPER(SUBSTR(t.titulo, 1, 6)) "
            f"WHERE t.data = ? AND t.fundo IN ({ph})",
            con_rt, params=(ultimo_du_ref or data_ref, *params))
        con_rt.close()

        if not tp_ref_rt.empty:
            # Aggregate by ISIN
            rt_agg = tp_ref_rt.groupby("isin").agg({
                "pct_pl": "sum", "rating": "first",
            }).reset_index()
            rt_agg["rating"] = rt_agg["rating"].fillna("S/R")
            rt_agg["rating"] = rt_agg["rating"].str.replace(r'[+-]$', '', regex=True)
            rating_order_mapa = ["AAA", "AA", "A", "BBB", "BB", "B", "S/R"]

            rt_grp_m = rt_agg.groupby("rating")["pct_pl"].sum().reset_index()
            rt_grp_m["pct_pl"] = rt_grp_m["pct_pl"] * 100
            rt_grp_m["sort_key"] = rt_grp_m["rating"].apply(
                lambda x: rating_order_mapa.index(x) if x in rating_order_mapa else 99)
            rt_grp_m = rt_grp_m.sort_values("sort_key", ascending=False)

            fig_rt_m = go.Figure(go.Bar(
                y=rt_grp_m["rating"], x=rt_grp_m["pct_pl"],
                orientation="h", marker_color=MARROM,
                text=[f"{v:.2f}%".replace(".", ",") for v in rt_grp_m["pct_pl"]],
                textposition="auto",
                hovertemplate="%{y}: <b>%{x:.2f}%</b><extra></extra>",
            ))
            fig_rt_m.update_layout(**_base("% PL por Rating", 280))
            fig_rt_m.update_xaxes(ticksuffix="%", showgrid=True,
                                  gridcolor=MARROM, gridwidth=0.5)
            chart_rating = dcc.Graph(figure=fig_rt_m, config={"displayModeBar": False})
        else:
            chart_rating = html.Div([
                html.H5("% PL por Rating", style={
                    "color": VERDE, "fontFamily": FONT, "fontSize": "13px",
                    "fontWeight": "bold", "marginBottom": "8px"}),
                html.P("Sem dados de rating disponíveis.",
                       style={"color": VERDE, "fontStyle": "italic",
                              "fontSize": "12px"}),
            ])

        sections.append(html.Div([
            html.Div(chart_idx, style={"flex": "1"}),
            html.Div(chart_rating, style={"flex": "1"}),
        ], style={"display": "flex", "gap": "24px", "marginTop": "20px"}))

    return html.Div(sections)


# ══════════════════════════════════════════════════════════════════════════════
# ABA 5 — ENQUADRAMENTO
# ══════════════════════════════════════════════════════════════════════════════

def _tab_enquadramento_layout(fund_key):
    datas = get_datas(fund_key)
    if not datas:
        return html.P("Sem dados de carteira disponíveis.", style={"color": VERDE})
    options = [{"label": d, "value": d} for d in datas]
    return html.Div([
        html.Div([
            html.Div([
                html.Label("Data de Referência", style={
                    "fontWeight": "bold", "fontSize": "13px",
                    "fontFamily": FONT, "color": VERDE,
                }),
                dcc.Dropdown(
                    id="enq-data",
                    options=options,
                    value=datas[0],
                    clearable=False,
                    style={"width": "200px", "fontFamily": FONT},
                ),
            ], style={"marginRight": "32px"}),
            html.Div([
                html.Label("Denominador", style={
                    "fontWeight": "bold", "fontSize": "13px",
                    "fontFamily": FONT, "color": VERDE,
                }),
                dcc.RadioItems(
                    id="enq-denominador",
                    options=[
                        {"label": "PL Médio 252d", "value": "medio"},
                        {"label": "PL do Dia", "value": "dia"},
                    ],
                    value="medio",
                    inline=True,
                    style={"fontFamily": FONT, "fontSize": "13px"},
                    inputStyle={"marginRight": "4px"},
                    labelStyle={"marginRight": "16px"},
                ),
            ]),
        ], style={"display": "flex", "alignItems": "flex-end", "marginBottom": "20px"}),
        dcc.Store(id="enq-fund-key", data=fund_key),
        html.Div(id="enq-content"),
    ])


def _enq_status_color(status):
    if status == "CONFORME":
        return VERDE
    if status == "ALERTA":
        return MARROM
    return VERMELHO_ALERTA


def _enq_semaforo_card(rule_id, rule_name, pct, limite, status, limit_type):
    color = _enq_status_color(status)
    if limit_type == "min":
        limite_label = f"Min {limite:.0%}"
    else:
        limite_label = f"Max {limite:.0%}"
    return html.Div([
        html.Div(f"{rule_id}", style={
            "fontSize": "11px", "opacity": "0.7", "marginBottom": "2px",
        }),
        html.Div(rule_name, style={
            "fontSize": "13px", "fontWeight": "bold", "marginBottom": "8px",
            "lineHeight": "1.2",
        }),
        html.Div(f"{pct:.2%}".replace(".", ","), style={
            "fontSize": "26px", "fontWeight": "bold", "marginBottom": "4px",
        }),
        html.Div(limite_label, style={
            "fontSize": "11px", "opacity": "0.7", "marginBottom": "6px",
        }),
        html.Div(status, style={
            "fontSize": "12px", "fontWeight": "bold",
            "padding": "3px 10px", "borderRadius": "4px",
            "backgroundColor": "rgba(255,255,255,0.15)",
            "display": "inline-block",
        }),
    ], style={
        "backgroundColor": color, "color": PALHA,
        "border": f"2px solid {MARROM}", "borderRadius": "10px",
        "padding": "16px 20px", "flex": "1", "textAlign": "center",
        "fontFamily": FONT, "minWidth": "180px",
    })


@app.callback(
    Output("enq-content", "children"),
    [Input("enq-data", "value"),
     Input("enq-denominador", "value")],
    State("enq-fund-key", "data"),
)
def update_enquadramento(data_ref, denominador, fund_key):
    if not fund_key or not data_ref:
        return html.P("Selecione uma data.", style={"color": VERDE})

    usar_pl_medio = (denominador == "medio")
    result = _calcular_enquadramento(fund_key, data_ref, usar_pl_medio=usar_pl_medio)
    if result is None:
        return html.P("Sem dados para esta data.", style={"color": VERDE})

    pl_usado = result["pl_usado"]
    dias_pl = result["dias_pl"]
    df = result["ativos"]
    regras = result["regras"]

    sections = []

    # ── PL Info ──────────────────────────────────────────────────────────────
    pl_info_parts = [f"PL usado: {_fmt_brl(pl_usado)}"]
    if result["pl_dia"]:
        pl_info_parts.append(f"PL dia: {_fmt_brl(result['pl_dia'])}")
    if result["pl_medio"]:
        pl_info_parts.append(f"PL médio: {_fmt_brl(result['pl_medio'])}")
    pl_info_parts.append(f"Janela: {dias_pl} dias")
    if dias_pl < REGRAS_ENQUADRAMENTO["R01"]["rolling_days"]:
        pl_info_parts.append(f"(< {REGRAS_ENQUADRAMENTO['R01']['rolling_days']}d)")

    sections.append(html.Div(
        " | ".join(pl_info_parts),
        style={
            "fontSize": "12px", "color": VERDE, "fontFamily": FONT,
            "marginBottom": "16px", "opacity": "0.8",
        },
    ))

    # ── Semáforo R01–R04 ─────────────────────────────────────────────────────
    semaforo_cards = []
    for rid in ["R01", "R02", "R03"]:
        r = regras[rid]
        cfg = REGRAS_ENQUADRAMENTO[rid]
        semaforo_cards.append(
            _enq_semaforo_card(rid, cfg["name"], r["pct"], r["limite"],
                               r["status"], cfg["limit_type"])
        )
    # R04 — show worst emissor pct
    r04 = regras["R04"]
    r04_det = r04["detalhe"]
    r04_worst_pct = r04_det["pct"].max() if not r04_det.empty else 0
    semaforo_cards.append(
        _enq_semaforo_card("R04", REGRAS_ENQUADRAMENTO["R04"]["name"],
                           r04_worst_pct, r04["limite"],
                           r04["status"], "max")
    )

    sections.append(html.Div(semaforo_cards, style={
        "display": "flex", "gap": "12px", "flexWrap": "wrap",
        "marginBottom": "28px",
    }))

    # ── Detalhamento R01 — Elegibilidade por ativo ───────────────────────────
    sections.append(_section_title("Detalhamento R01 — Elegibilidade por Ativo"))

    # Summary bar
    total_fin = df["financeiro"].sum()
    total_eleg = df.loc[df["is_elegivel"], "financeiro"].sum()
    total_nao = total_fin - total_eleg
    sections.append(html.Div([
        _card("Elegíveis", _fmt_brl(total_eleg)),
        _card("Não Elegíveis", _fmt_brl(total_nao)),
        _card("Total Carteira", _fmt_brl(total_fin)),
    ], style={"display": "flex", "gap": "12px", "marginBottom": "16px"}))

    # Assets table
    tbl_df = df[[
        "ticker", "emissor_enquadramento", "tipo_ref", "prazo_anos",
        "prazo_bucket", "elegibilidade", "financeiro",
    ]].copy()
    tbl_df["prazo_anos"] = tbl_df["prazo_anos"].apply(
        lambda x: f"{x:.1f}" if pd.notna(x) else "—"
    )
    tbl_df["financeiro_fmt"] = tbl_df["financeiro"].apply(
        lambda v: f"{v / 1000:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    tbl_df["pct_pl"] = tbl_df["financeiro"].apply(
        lambda v: f"{v / pl_usado:.2%}".replace(".", ",")
    )
    tbl_df["tipo_ref"] = tbl_df["tipo_ref"].fillna("Sem ref")

    # Aggregate by ticker for display
    tbl_agg = tbl_df.groupby(["ticker", "emissor_enquadramento", "tipo_ref",
                               "prazo_bucket", "elegibilidade"]).agg(
        prazo_anos=("prazo_anos", "first"),
        financeiro=("financeiro", "sum"),
    ).reset_index()
    tbl_agg["financeiro_fmt"] = tbl_agg["financeiro"].apply(
        lambda v: f"{v / 1000:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    tbl_agg["pct_pl"] = tbl_agg["financeiro"].apply(
        lambda v: f"{v / pl_usado:.2%}".replace(".", ",")
    )
    tbl_agg = tbl_agg.sort_values("financeiro", ascending=False)
    tbl_agg["elegibilidade"] = tbl_agg["elegibilidade"].map(
        _ELEGIBILIDADE_LABELS).fillna(tbl_agg["elegibilidade"])

    sections.append(_DataTable(
        columns=[
            {"name": "Ticker", "id": "ticker"},
            {"name": "Emissor", "id": "emissor_enquadramento"},
            {"name": "Tipo", "id": "tipo_ref"},
            {"name": "Prazo (anos)", "id": "prazo_anos"},
            {"name": "Bucket", "id": "prazo_bucket"},
            {"name": "Elegibilidade", "id": "elegibilidade"},
            {"name": "Financeiro (R$ mil)", "id": "financeiro_fmt"},
            {"name": "% PL", "id": "pct_pl"},
        ],
        data=tbl_agg.to_dict("records"),
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": VERDE, "color": PALHA,
            "fontWeight": "bold", "fontFamily": FONT, "fontSize": "12px",
        },
        style_cell={
            "fontFamily": FONT, "fontSize": "12px", "padding": "6px 10px",
            "backgroundColor": PALHA, "color": VERDE,
            "border": f"1px solid {MARROM}",
        },
        style_data_conditional=[
            {
                "if": {"filter_query": '{elegibilidade} contains "Elegível"'},
                "backgroundColor": "#e8f5e9",
            },
            {
                "if": {"filter_query": '{elegibilidade} contains "Não Elegível"'},
                "backgroundColor": "#fff3e0",
            },
            {
                "if": {"filter_query": '{elegibilidade} contains "Sem Classificação"'},
                "backgroundColor": "#fff3e0",
            },
        ],
        page_size=20,
        sort_action="native",
        filter_action="native",
    ))

    # ── Detalhamento R04 — Concentração por Emissor ──────────────────────────
    sections.append(_section_title("Detalhamento R04 — Concentração por Emissor"))

    r04_det = regras["R04"]["detalhe"].copy()
    r04_det["financeiro_fmt"] = r04_det["financeiro"].apply(
        lambda v: f"{v / 1000:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    r04_det["pct_fmt"] = r04_det["pct"].apply(
        lambda v: f"{v:.2%}".replace(".", ",")
    )

    sections.append(_DataTable(
        columns=[
            {"name": "Emissor", "id": "emissor_enquadramento"},
            {"name": "Financeiro (R$ mil)", "id": "financeiro_fmt"},
            {"name": "% PL", "id": "pct_fmt"},
            {"name": "Status", "id": "status"},
        ],
        data=r04_det.to_dict("records"),
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": VERDE, "color": PALHA,
            "fontWeight": "bold", "fontFamily": FONT, "fontSize": "12px",
        },
        style_cell={
            "fontFamily": FONT, "fontSize": "12px", "padding": "6px 10px",
            "backgroundColor": PALHA, "color": VERDE,
            "border": f"1px solid {MARROM}",
        },
        style_data_conditional=[
            {
                "if": {"filter_query": '{status} = "VIOLADO"'},
                "backgroundColor": "#ffebee", "color": VERMELHO_ALERTA,
            },
            {
                "if": {"filter_query": '{status} = "ALERTA"'},
                "backgroundColor": "#fff3e0",
            },
        ],
        sort_action="native",
    ))

    # Top 10 emissor bar chart
    top10 = r04_det.head(10).copy()
    if not top10.empty:
        top10 = top10.sort_values("pct", ascending=True)
        bar_colors = [_enq_status_color(s) for s in top10["status"]]
        fig_em = go.Figure(go.Bar(
            x=top10["pct"] * 100,
            y=top10["emissor_enquadramento"],
            orientation="h",
            marker_color=bar_colors,
            text=top10["pct"].apply(lambda v: f"{v:.1%}"),
            textposition="outside",
        ))
        fig_em.add_vline(
            x=REGRAS_ENQUADRAMENTO["R04"]["limit_value"] * 100,
            line_dash="dash", line_color=VERMELHO_ALERTA, line_width=2,
            annotation_text="Limite 20%",
            annotation_position="top right",
        )
        fig_em.update_layout(
            **_base("Top 10 Emissores (% PL)", 350),
            xaxis_title="% PL",
        )
        fig_em.update_xaxes(ticksuffix="%", showgrid=True,
                            gridcolor=MARROM, gridwidth=0.5)
        sections.append(html.Div(
            dcc.Graph(figure=fig_em, config={"displayModeBar": False}),
            style={"marginTop": "16px"},
        ))

    # ── Auditoria — Ativos sem classificação ─────────────────────────────────
    df_sem = df[df["qualidade_tipo"] == "sem_classificacao"]
    if not df_sem.empty:
        sections.append(_section_title("Auditoria — Ativos sem Classificação"))
        sections.append(html.P(
            f"{len(df_sem)} posições com ticker sem correspondência em "
            f"ref_setor_rating. Tratadas como NÃO elegíveis por conservadorismo.",
            style={"fontSize": "12px", "color": VERDE, "fontFamily": FONT,
                   "marginBottom": "8px"},
        ))
        sem_agg = df_sem.groupby(["ticker", "emissor_fact"]).agg(
            financeiro=("financeiro", "sum"),
        ).reset_index().sort_values("financeiro", ascending=False)
        sem_agg["financeiro_fmt"] = sem_agg["financeiro"].apply(
            lambda v: f"{v / 1000:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        sections.append(_DataTable(
            columns=[
                {"name": "Ticker", "id": "ticker"},
                {"name": "Emissor (fact)", "id": "emissor_fact"},
                {"name": "Financeiro (R$ mil)", "id": "financeiro_fmt"},
            ],
            data=sem_agg.to_dict("records"),
            style_table={"overflowX": "auto"},
            style_header={
                "backgroundColor": MARROM, "color": VERDE,
                "fontWeight": "bold", "fontFamily": FONT, "fontSize": "12px",
            },
            style_cell={
                "fontFamily": FONT, "fontSize": "12px", "padding": "6px 10px",
                "backgroundColor": PALHA, "color": VERDE,
                "border": f"1px solid {MARROM}",
            },
        ))

    # ── Flag PL janela incompleta ────────────────────────────────────────────
    rolling_target = REGRAS_ENQUADRAMENTO["R01"]["rolling_days"]
    if dias_pl < rolling_target:
        sections.append(html.Div(
            f"Janela de PL: {dias_pl}/{rolling_target} dias disponíveis. "
            f"PL médio calculado com janela incompleta.",
            style={
                "marginTop": "16px", "padding": "10px 16px",
                "backgroundColor": "#fff3e0", "borderRadius": "6px",
                "border": f"1px solid {MARROM}",
                "fontFamily": FONT, "fontSize": "12px", "color": VERDE,
            },
        ))

    return html.Div(sections)


# ══════════════════════════════════════════════════════════════════════════════
# CONSOLIDADO PAGE
# ══════════════════════════════════════════════════════════════════════════════

def _render_consolidado_page():
    header_children = []
    if LOGO_SRC:
        header_children.append(
            html.Img(src=LOGO_SRC, style={"height": "50px", "marginRight": "20px"})
        )
    header_children.append(
        html.H2("Visão Consolidada", style={
            "color": VERDE, "letterSpacing": "3px", "margin": "0",
            "fontSize": "24px", "fontWeight": "bold", "fontFamily": FONT,
        })
    )

    return html.Div([
        dcc.Link("\u2190 Voltar", href="/", style={
            "color": VERDE, "fontFamily": FONT, "fontWeight": "bold",
            "fontSize": "14px", "textDecoration": "none",
            "marginBottom": "12px", "display": "inline-block",
        }),
        html.Div(header_children, style={
            "display": "flex", "alignItems": "center", "marginBottom": "8px",
        }),
        html.Hr(style={"borderColor": VERDE, "borderWidth": "2px",
                        "marginBottom": "24px"}),
        html.Div(id="consolidado-content"),
        dcc.Store(id="consolidado-trigger", data="load"),
    ])


@app.callback(
    Output("consolidado-content", "children"),
    Input("consolidado-trigger", "data"),
)
def update_consolidado(_trigger):
    con = _conn()

    # ── AUM Overview (FICs + Standalone only to avoid double-counting)
    # Use each fund's latest date (not global MAX) since funds may have
    # different reporting dates
    exclude_ph = ",".join([f"'{f}'" for f in _EXCLUDE_FUNDS]) if _EXCLUDE_FUNDS else "''"
    aum_df = pd.read_sql(f"""
        SELECT r.fundo, f.display, f.produto, f.tipo,
               r.patrimonio, r.rent_mes, r.rent_ano,
               r.pct_cdi_mes, r.pct_cdi_ano, r.data
        FROM fact_rentabilidade r
        JOIN ref_fundos f ON f.fundo = r.fundo
        INNER JOIN (
            SELECT fundo, MAX(data) as max_data
            FROM fact_rentabilidade
            GROUP BY fundo
        ) latest ON r.fundo = latest.fundo AND r.data = latest.max_data
        WHERE f.tipo IN ('FIC', 'STANDALONE')
          AND r.fundo NOT IN ({exclude_ph})
        ORDER BY f.produto, r.patrimonio DESC
    """, con)

    latest_date = aum_df["data"].max() if not aum_df.empty else "N/A"

    # ── Credit Portfolio (Masters + Standalone, deduplicated by ISIN)
    latest_tp_date = pd.read_sql(
        "SELECT MAX(data) as d FROM fact_titulos_privados", con
    )["d"].iloc[0]

    portfolio_df = pd.read_sql(f"""
        SELECT v.isin, MAX(v.titulo) as titulo, MAX(v.emissor) as emissor,
               MAX(v.setor) as setor, MAX(v.rating) as rating,
               MAX(v.indexador) as sr_indexador,
               SUM(v.financeiro) as financeiro
        FROM vw_carteira_consolidada v
        WHERE v.data = ? AND v.tipo_fundo IN ('MASTER', 'STANDALONE')
        GROUP BY v.isin
        ORDER BY financeiro DESC
    """, con, params=(latest_tp_date,))

    con.close()

    sections = []

    # ══════════════════════════════════════════════════════════════════
    # SECAO 1 — AUM Overview
    # ══════════════════════════════════════════════════════════════════
    sections.append(_section_title(f"AUM — {latest_date}"))

    total_aum = aum_df["patrimonio"].sum()
    aum_by_produto = aum_df.groupby("produto")["patrimonio"].sum().sort_values(ascending=False)

    # Cards
    cards = [_card("AUM Total", _fmt_brl(total_aum))]
    for produto, pl in aum_by_produto.items():
        cards.append(_card(f"AUM {produto}", _fmt_brl(pl)))
    sections.append(html.Div(cards, style={
        "display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "20px",
    }))

    # AUM Table
    aum_rows = []
    for _, r in aum_df.iterrows():
        rent_mes = f"{r['rent_mes']:.2f}%".replace(".", ",") if pd.notna(r["rent_mes"]) else "\u2014"
        pct_cdi = f"{r['pct_cdi_mes']:.2f}%".replace(".", ",") if pd.notna(r["pct_cdi_mes"]) else "\u2014"
        aum_rows.append({
            "Fundo": r["display"],
            "Produto": r["produto"],
            "PL (R$ MM)": _fmt_brl(r["patrimonio"]).replace("R$ ", ""),
            "Rent. Mês": rent_mes,
            "% CDI Mês": pct_cdi,
        })
    if aum_rows:
        sections.append(_DataTable(
            data=aum_rows,
            columns=[{"name": c, "id": c} for c in
                     ["Fundo", "Produto", "PL (R$ MM)", "Rent. Mês", "% CDI Mês"]],
            style_table={"overflowX": "auto"},
            style_header={
                "backgroundColor": VERDE, "color": PALHA,
                "fontWeight": "bold", "textAlign": "center",
                "fontSize": "12px", "fontFamily": FONT, "padding": "8px",
            },
            style_cell={
                "textAlign": "center", "fontFamily": FONT,
                "fontSize": "12px", "padding": "7px 10px",
                "border": f"1px solid {MARROM}",
            },
            style_cell_conditional=[
                {"if": {"column_id": "Fundo"}, "textAlign": "left", "minWidth": "250px"},
            ],
            style_data_conditional=[
                {"if": {"row_index": "even"}, "backgroundColor": PALHA},
                {"if": {"row_index": "odd"}, "backgroundColor": "#f5e6cd"},
            ],
            page_size=9999,
        ))

    # ══════════════════════════════════════════════════════════════════
    # SECAO 2 — Portfolio Consolidado de Credito
    # ══════════════════════════════════════════════════════════════════
    sections.append(_section_title(f"Portfolio Consolidado de Crédito — {latest_tp_date}"))

    if portfolio_df.empty:
        sections.append(html.P("Sem dados de crédito.", style={"color": VERDE}))
    else:
        total_credito = portfolio_df["financeiro"].sum()
        n_emissoes = portfolio_df["isin"].nunique()

        sections.append(html.Div([
            _card("Total Crédito Privado", _fmt_brl(total_credito)),
            _card("Nº de Emissões (ISIN)", str(n_emissoes)),
        ], style={"display": "flex", "gap": "16px", "marginBottom": "20px"}))

        # Top 15 positions
        top15 = portfolio_df.head(15)
        top_rows = []
        for _, r in top15.iterrows():
            tk = str(r["titulo"])[:6].upper() if pd.notna(r["titulo"]) else ""
            pct = (r["financeiro"] / total_credito * 100) if total_credito else 0
            top_rows.append({
                "Ticker": tk,
                "Emissor": r["emissor"] if pd.notna(r["emissor"]) else "",
                "Setor": r["setor"] if pd.notna(r["setor"]) else "N/A",
                "Rating": r["rating"] if pd.notna(r["rating"]) else "N/A",
                "Financeiro (R$ mil)": _fmt_fin_mil(r["financeiro"]),
                "% Total": _fmt_pct(pct),
            })
        sections.append(html.H5("Top 15 Posições", style={
            "color": VERDE, "fontFamily": FONT, "fontSize": "13px",
            "fontWeight": "bold", "marginBottom": "8px"}))
        sections.append(_DataTable(
            data=top_rows,
            columns=[{"name": c, "id": c} for c in
                     ["Ticker", "Emissor", "Setor", "Rating",
                      "Financeiro (R$ mil)", "% Total"]],
            style_table={"overflowX": "auto"},
            style_header={
                "backgroundColor": VERDE, "color": PALHA,
                "fontWeight": "bold", "textAlign": "center",
                "fontSize": "12px", "fontFamily": FONT, "padding": "8px",
            },
            style_cell={
                "textAlign": "center", "fontFamily": FONT,
                "fontSize": "12px", "padding": "7px 10px",
                "border": f"1px solid {MARROM}",
            },
            style_cell_conditional=[
                {"if": {"column_id": "Emissor"}, "textAlign": "left", "minWidth": "200px"},
            ],
            style_data_conditional=[
                {"if": {"row_index": "even"}, "backgroundColor": PALHA},
                {"if": {"row_index": "odd"}, "backgroundColor": "#f5e6cd"},
            ],
            page_size=9999,
        ))

        # ── Pie charts: Indexador, Setor, Rating, Emissor
        # Indexador
        portfolio_df["indexador_label"] = portfolio_df.apply(
            lambda r: _get_indexador(r.get("sr_indexador"), r["titulo"]),
            axis=1,
        )
        ix_grp = portfolio_df.groupby("indexador_label")["financeiro"].sum().reset_index()
        ix_grp = ix_grp.sort_values("financeiro", ascending=False)

        fig_ix_c = go.Figure(go.Pie(
            labels=ix_grp["indexador_label"], values=ix_grp["financeiro"], hole=0.4,
            textinfo="percent", textfont_size=11,
            marker_colors=PIE_COLORS[:len(ix_grp)],
            hovertemplate="%{label}<br>R$ %{value:,.0f}<br>%{percent}<extra></extra>",
            sort=False, direction="clockwise", rotation=90,
        ))
        kw = _base("% por Indexador", 380, legend=True)
        kw["legend"] = dict(font=dict(size=9), x=1.02, y=0.5)
        fig_ix_c.update_layout(**kw)

        # Setor
        portfolio_df["setor_label"] = portfolio_df["setor"].fillna("Outros").replace("", "Outros")
        st_grp = portfolio_df.groupby("setor_label")["financeiro"].sum().reset_index()
        st_grp = st_grp.sort_values("financeiro", ascending=False)

        fig_st_c = go.Figure(go.Pie(
            labels=st_grp["setor_label"], values=st_grp["financeiro"], hole=0.4,
            textinfo="percent", textfont_size=11,
            marker_colors=PIE_COLORS[:len(st_grp)],
            hovertemplate="%{label}<br>R$ %{value:,.0f}<br>%{percent}<extra></extra>",
            sort=False, direction="clockwise", rotation=90,
        ))
        kw2 = _base("% por Setor", 380, legend=True)
        kw2["legend"] = dict(font=dict(size=9), x=1.02, y=0.5)
        fig_st_c.update_layout(**kw2)

        sections.append(html.Div([
            html.Div(dcc.Graph(figure=fig_ix_c, config={"displayModeBar": False}),
                     style={"flex": "1"}),
            html.Div(dcc.Graph(figure=fig_st_c, config={"displayModeBar": False}),
                     style={"flex": "1"}),
        ], style={"display": "flex", "gap": "16px", "marginTop": "20px"}))

        # Rating + Top Emissores
        # Rating bar
        portfolio_df["rating_label"] = portfolio_df["rating"].fillna("S/R")
        rating_order_c = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-",
                          "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
                          "B+", "B", "B-", "S/R"]
        rt_grp_c = portfolio_df.groupby("rating_label")["financeiro"].sum().reset_index()
        rt_grp_c["pct"] = rt_grp_c["financeiro"] / total_credito * 100
        rt_grp_c["sort_key"] = rt_grp_c["rating_label"].apply(
            lambda x: rating_order_c.index(x) if x in rating_order_c else 99)
        rt_grp_c = rt_grp_c.sort_values("sort_key")

        _rt_colors = PIE_COLORS + ["#5c4a32", "#3d6b1e", "#c9b896", "#6b8e23",
                                    "#deb887", "#556b2f", "#8b6914", "#4a7c59"]
        fig_rt_c = go.Figure()
        for i, (_, row_rt) in enumerate(rt_grp_c.iterrows()):
            pct_val = row_rt["pct"]
            rating = row_rt["rating_label"]
            bg = _rt_colors[i % len(_rt_colors)].lstrip("#")
            rv, gv, bv = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
            txt_c = "white" if (0.299 * rv + 0.587 * gv + 0.114 * bv) < 150 else VERDE
            fig_rt_c.add_trace(go.Bar(
                y=[""], x=[pct_val], name=rating, orientation="h",
                text=f"{rating} {pct_val:.1f}%".replace(".", ","),
                textposition="inside", insidetextanchor="middle",
                textfont=dict(size=11, color=txt_c),
                marker_color=_rt_colors[i % len(_rt_colors)],
                hovertemplate=f"{rating}: <b>{pct_val:.2f}%</b><extra></extra>",
            ))
        fig_rt_c.update_layout(barmode="stack",
                               **_base("Exposição por Rating (% Crédito)", 180, legend=True))
        fig_rt_c.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=1.08,
                        xanchor="center", x=0.5, font=dict(size=10)),
            margin=dict(t=80, b=20, l=30, r=30),
        )
        fig_rt_c.update_xaxes(ticksuffix="%", showgrid=False, visible=False)
        fig_rt_c.update_yaxes(showticklabels=False)

        # Top 10 emissores
        em_grp = portfolio_df.groupby("emissor")["financeiro"].sum().reset_index()
        em_grp = em_grp.sort_values("financeiro", ascending=False).head(10)
        em_grp["pct"] = em_grp["financeiro"] / total_credito * 100

        fig_em_c = go.Figure(go.Bar(
            y=em_grp["emissor"][::-1],
            x=em_grp["pct"][::-1],
            orientation="h", marker_color=MARROM,
            text=[f"{v:.1f}%".replace(".", ",") for v in em_grp["pct"][::-1]],
            textposition="auto",
            hovertemplate="%{y}: <b>%{x:.2f}%</b><extra></extra>",
        ))
        fig_em_c.update_layout(**_base("Top 10 Emissores (% Crédito Total)", 350))
        fig_em_c.update_xaxes(ticksuffix="%", showgrid=True,
                              gridcolor=MARROM, gridwidth=0.5)

        sections.append(html.Div([
            html.Div(dcc.Graph(figure=fig_rt_c, config={"displayModeBar": False}),
                     style={"flex": "1"}),
        ], style={"marginTop": "20px"}))

        sections.append(html.Div([
            html.Div(dcc.Graph(figure=fig_em_c, config={"displayModeBar": False}),
                     style={"flex": "1"}),
        ], style={"marginTop": "20px"}))

    return html.Div(sections)


# ══════════════════════════════════════════════════════════════════════════════
# ABA 6 — P&L ATTRIBUTION (fact_perfatt)
# ══════════════════════════════════════════════════════════════════════════════

_ATT_COMPS = [
    ("pnl_carrego_index", "Carrego Index",  "#0a2300"),
    ("pnl_carrego_yield", "Carrego Yield",  "#2e5c14"),
    ("pnl_curva",         "Curva (NTN-B)",  "#cdaa82"),
    ("pnl_spread",        "Spread",         "#a68b5b"),
    ("pnl_trading",       "Trading",        "#b22222"),
]


def _tab_attribution_layout(fund_key):
    if not _cg_top_fundo(fund_key):
        return html.Div("Performance Attribution não disponível para este fundo.",
                        style={"color": VERDE, "fontFamily": FONT,
                               "padding": "20px", "fontSize": "14px"})
    return html.Div([
        _period_buttons("att"),
        dcc.Store(id="att-period", data="ano"),
        html.Div(id="att-content"),
    ])


@app.callback(
    Output("att-period", "data"),
    [Input({"type": "att-btn", "index": v}, "n_clicks") for v in
     ["inicio", "ano", "12m", "1m"]],
    prevent_initial_call=True,
)
def att_set_period(*clicks):
    ctx = callback_context
    if not ctx.triggered:
        return "ano"
    prop = ctx.triggered[0]["prop_id"]
    key = json.loads(prop.split(".")[0])
    return key["index"]


@app.callback(
    Output("att-content", "children"),
    Input("att-period", "data"),
    State("url", "pathname"),
)
def update_attribution(period, pathname):
    fund_key = _get_fund_key(pathname)
    if not fund_key:
        return ""
    df = load_perfatt_resumo(fund_key)
    if df.empty:
        return html.P("Sem dados de Performance Attribution.",
                      style={"color": VERDE, "fontFamily": FONT})

    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df = df.dropna(subset=["data"]).sort_values("data")
    df = filter_df(df, period)
    if df.empty:
        return html.P("Sem dados no período selecionado.",
                      style={"color": VERDE, "fontFamily": FONT})

    # ── Cards: somatorios do periodo ─────────────────────────────────────
    cards = []
    for col, label, _ in _ATT_COMPS:
        v = df[col].sum() if col in df.columns else 0
        cards.append(_card(label, _fmt_brl(v)))
    total = df["pnl_total"].sum() if "pnl_total" in df.columns else 0
    cards.append(_card("Total P&L", _fmt_brl(total)))

    # ── Bar chart empilhado: P&L diario decomposto ───────────────────────
    fig_pnl = go.Figure()
    for col, label, color in _ATT_COMPS:
        if col in df.columns:
            fig_pnl.add_trace(go.Bar(
                x=df["data"], y=df[col].fillna(0), name=label,
                marker_color=color,
                hovertemplate=f"{label}<br>%{{x|%d/%m/%Y}}<br>R$ %{{y:,.0f}}<extra></extra>",
            ))
    fig_pnl.update_layout(barmode="relative",
                          **_base("P&L Diário Decomposto (R$)", 380, legend=True))
    fig_pnl.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.06,
                                      xanchor="center", x=0.5, font=dict(size=11)))

    # ── Linha: P&L acumulado e cada componente acumulado ─────────────────
    fig_cum = go.Figure()
    df_sorted = df.sort_values("data")
    for col, label, color in _ATT_COMPS:
        if col in df_sorted.columns:
            cum = df_sorted[col].fillna(0).cumsum()
            fig_cum.add_trace(go.Scatter(
                x=df_sorted["data"], y=cum, name=label,
                mode="lines", line=dict(color=color, width=2),
                hovertemplate=f"{label} acum<br>%{{x|%d/%m/%Y}}<br>R$ %{{y:,.0f}}<extra></extra>",
            ))
    if "pnl_total" in df_sorted.columns:
        cum_total = df_sorted["pnl_total"].fillna(0).cumsum()
        fig_cum.add_trace(go.Scatter(
            x=df_sorted["data"], y=cum_total, name="Total",
            mode="lines", line=dict(color="#000", width=3, dash="dot"),
            hovertemplate="Total acum<br>%{x|%d/%m/%Y}<br>R$ %{y:,.0f}<extra></extra>",
        ))
    fig_cum.update_layout(**_base("P&L Acumulado por Componente (R$)", 380, legend=True))
    fig_cum.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.06,
                                      xanchor="center", x=0.5, font=dict(size=11)))

    # ── Top contribuidores ativo (ultimo dia do periodo) ────────────────
    ultima_data = df["data"].max().strftime("%Y-%m-%d")
    df_at = load_perfatt_ativos(fund_key, ultima_data)
    ativos_block = []
    if not df_at.empty:
        df_at = df_at[df_at["ativo"].astype(str).str.strip() != ""]
        if not df_at.empty:
            df_at_top = df_at.sort_values("pnl_total", ascending=False).head(10)
            df_at_bot = df_at.sort_values("pnl_total", ascending=True).head(10)

            fig_top = go.Figure(go.Bar(
                y=df_at_top["ativo"][::-1], x=df_at_top["pnl_total"][::-1],
                orientation="h", marker_color="#2e5c14",
                text=[_fmt_brl(v) for v in df_at_top["pnl_total"][::-1]],
                textposition="auto",
                hovertemplate="%{y}<br>R$ %{x:,.0f}<extra></extra>",
            ))
            fig_top.update_layout(**_base(f"Top 10 P&L Positivo (Ativos) — {ultima_data}", 340))

            fig_bot = go.Figure(go.Bar(
                y=df_at_bot["ativo"][::-1], x=df_at_bot["pnl_total"][::-1],
                orientation="h", marker_color=VERMELHO_ALERTA,
                text=[_fmt_brl(v) for v in df_at_bot["pnl_total"][::-1]],
                textposition="auto",
                hovertemplate="%{y}<br>R$ %{x:,.0f}<extra></extra>",
            ))
            fig_bot.update_layout(**_base(f"Top 10 P&L Negativo (Ativos) — {ultima_data}", 340))

            ativos_block = [html.Div([
                html.Div(dcc.Graph(figure=fig_top, config={"displayModeBar": False}),
                         style={"flex": "1"}),
                html.Div(dcc.Graph(figure=fig_bot, config={"displayModeBar": False}),
                         style={"flex": "1"}),
            ], style={"display": "flex", "gap": "16px", "marginTop": "20px"})]

    return html.Div([
        html.Div(cards, style={"display": "flex", "gap": "12px",
                               "flexWrap": "wrap", "margin": "20px 0"}),
        dcc.Graph(figure=fig_pnl, config={"displayModeBar": False}),
        dcc.Graph(figure=fig_cum, config={"displayModeBar": False}),
        *ativos_block,
    ])


# ══════════════════════════════════════════════════════════════════════════════
# ABA 7 — TRADES (fact_trades)
# ══════════════════════════════════════════════════════════════════════════════

def _tab_trades_layout(fund_key):
    if not _cg_top_fundo(fund_key):
        return html.Div("Histórico de Trades não disponível para este fundo.",
                        style={"color": VERDE, "fontFamily": FONT,
                               "padding": "20px", "fontSize": "14px"})

    df = load_trades(fund_key)
    if df.empty:
        return html.P("Sem trades registrados para este fundo.",
                      style={"color": VERDE, "fontFamily": FONT})

    # Cards
    df["net_amount"] = pd.to_numeric(df["net_amount"], errors="coerce").fillna(0)
    df["mtm_pnl"]    = pd.to_numeric(df["mtm_pnl"], errors="coerce").fillna(0)
    df["par_pnl"]    = pd.to_numeric(df["par_pnl"], errors="coerce").fillna(0)

    n_trades  = len(df)
    n_compras = (df["side"] == "B").sum()
    n_vendas  = (df["side"] == "S").sum()
    vol_compra = df.loc[df["side"] == "B", "net_amount"].sum()
    vol_venda  = df.loc[df["side"] == "S", "net_amount"].sum()
    mtm_total  = df["mtm_pnl"].sum()
    par_total  = df["par_pnl"].sum()

    cards = [
        _card("Nº Trades", str(n_trades)),
        _card("Compras", f"{n_compras} ({_fmt_brl(vol_compra)})"),
        _card("Vendas",  f"{n_vendas} ({_fmt_brl(vol_venda)})"),
        _card("MtM PnL Realizado",  _fmt_brl(mtm_total)),
        _card("Par PnL Realizado",  _fmt_brl(par_total)),
    ]

    # Tabela
    df_view = df.copy()
    df_view["Data"] = pd.to_datetime(df_view["data_trade"], errors="coerce").dt.strftime("%d/%m/%Y")
    df_view["Fundo Master"] = df_view["fundo"].fillna("")
    df_view["Título"] = df_view["titulo"]
    df_view["B/S"] = df_view["side"]
    df_view["Qtde"] = df_view["quantidade"].fillna(0).map(lambda v: f"{v:,.0f}".replace(",", "."))
    df_view["Yield (%)"] = (df_view["trade_yield"].astype(float) * 100).map(
        lambda v: f"{v:.3f}".replace(".", ",") if pd.notna(v) else "—")
    df_view["PU"] = df_view["pu"].map(
        lambda v: f"{v:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if pd.notna(v) else "—")
    df_view["Net (R$)"] = df_view["net_amount"].map(_fmt_brl)
    df_view["Spread Neg. (bps)"] = (df_view["spread_negociado"].astype(float) * 10000).map(
        lambda v: f"{v:,.0f}".replace(",", ".") if pd.notna(v) else "—")
    df_view["Spread Liq. (bps)"] = (df_view["spread_liquidado"].astype(float) * 10000).map(
        lambda v: f"{v:,.0f}".replace(",", ".") if pd.notna(v) else "—")
    df_view["MtM PnL"] = df_view["mtm_pnl"].map(_fmt_brl)
    df_view["Vértice"] = pd.to_datetime(df_view["vertice"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("")

    visible_cols = ["Data", "Fundo Master", "Título", "B/S", "Qtde", "Yield (%)",
                    "PU", "Net (R$)", "Spread Neg. (bps)", "Spread Liq. (bps)",
                    "Vértice", "MtM PnL"]
    tbl_data = df_view[visible_cols].to_dict("records")

    tabela = _DataTable(
        data=tbl_data,
        columns=[{"name": c, "id": c} for c in visible_cols],
        style_table={"overflowX": "auto", "maxHeight": "640px", "overflowY": "auto"},
        style_header={
            "backgroundColor": VERDE, "color": PALHA,
            "fontWeight": "bold", "textAlign": "center",
            "fontSize": "12px", "fontFamily": FONT, "padding": "8px",
            "position": "sticky", "top": 0, "zIndex": 1,
        },
        style_cell={
            "textAlign": "center", "fontFamily": FONT,
            "fontSize": "11px", "padding": "6px 8px",
            "border": f"1px solid {MARROM}",
        },
        style_data_conditional=[
            {"if": {"row_index": "even"}, "backgroundColor": PALHA},
            {"if": {"row_index": "odd"}, "backgroundColor": "#f5e6cd"},
            {"if": {"filter_query": "{B/S} = B"}, "color": "#2e5c14"},
            {"if": {"filter_query": "{B/S} = S"}, "color": VERMELHO_ALERTA},
        ],
        page_size=200,
        sort_action="native",
        filter_action="native",
    )

    # Bar chart: volume por mes
    df["mes"] = pd.to_datetime(df["data_trade"], errors="coerce").dt.to_period("M")
    df_mes = df.dropna(subset=["mes"]).groupby(["mes", "side"])["net_amount"].sum().reset_index()
    df_mes["mes_str"] = df_mes["mes"].astype(str)
    fig_vol = go.Figure()
    for side, color, label in [("B", "#2e5c14", "Compra"), ("S", VERMELHO_ALERTA, "Venda")]:
        sub = df_mes[df_mes["side"] == side]
        if not sub.empty:
            fig_vol.add_trace(go.Bar(
                x=sub["mes_str"], y=sub["net_amount"], name=label, marker_color=color,
                hovertemplate=f"{label}<br>%{{x}}<br>R$ %{{y:,.0f}}<extra></extra>",
            ))
    fig_vol.update_layout(barmode="group",
                          **_base("Volume de Trades por Mês (R$)", 320, legend=True))

    return html.Div([
        html.Div(cards, style={"display": "flex", "gap": "12px",
                               "flexWrap": "wrap", "margin": "20px 0"}),
        dcc.Graph(figure=fig_vol, config={"displayModeBar": False}),
        html.H4(f"Trade Log — {n_trades} trades",
                style={"color": VERDE, "fontFamily": FONT,
                       "fontSize": "14px", "marginTop": "24px"}),
        tabela,
    ])


# ══════════════════════════════════════════════════════════════════════════════
# ABA 8 — SPREAD HISTÓRICO (fact_pu_deb_bocaina + fact_deb_anbima)
# ══════════════════════════════════════════════════════════════════════════════

def _tab_spread_hist_layout(fund_key):
    tickers = load_tickers_carteira(fund_key)
    if not tickers:
        return html.P("Sem carteira para este fundo.",
                      style={"color": VERDE, "fontFamily": FONT})

    return html.Div([
        html.Div([
            html.Label("Ativo:", style={
                "fontWeight": "bold", "color": VERDE,
                "marginRight": "12px", "fontFamily": FONT, "fontSize": "14px",
            }),
            dcc.Dropdown(
                id="sh-ticker",
                options=[{"label": t, "value": t} for t in tickers],
                value=tickers[0],
                clearable=False,
                style={"width": "200px", "fontFamily": FONT},
            ),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "16px"}),
        html.Div(id="sh-content"),
    ])


@app.callback(
    Output("sh-content", "children"),
    Input("sh-ticker", "value"),
    State("url", "pathname"),
)
def update_spread_hist(ticker, pathname):
    if not ticker:
        return ""

    df_b = load_pu_deb_ticker(ticker)
    df_a = load_anbima_ticker(ticker)

    if df_b.empty and df_a.empty:
        return html.P(f"Sem histórico para {ticker}.",
                      style={"color": VERDE, "fontFamily": FONT})

    df_b["data"] = pd.to_datetime(df_b["data"], errors="coerce") if not df_b.empty else None
    df_a["data"] = pd.to_datetime(df_a["data"], errors="coerce") if not df_a.empty else None

    # Series para taxa
    fig_taxa = go.Figure()
    if not df_b.empty and "taxa" in df_b.columns:
        df_b_par = df_b[df_b["tipo"].fillna("") == "Par"].dropna(subset=["taxa"])
        if not df_b_par.empty:
            fig_taxa.add_trace(go.Scatter(
                x=df_b_par["data"], y=df_b_par["taxa"] * 100,
                name="Taxa Bocaina (Par)",
                mode="lines", line=dict(color=VERDE, width=2),
                hovertemplate="Bocaina<br>%{x|%d/%m/%Y}<br>%{y:.3f}%<extra></extra>",
            ))
    if not df_a.empty:
        df_a_main = df_a.dropna(subset=["tx_indicativa"])
        if not df_a_main.empty:
            # uma linha por indexador (IPCA_SPREAD, DI_PERCENTUAL, etc)
            for idx_tipo, sub in df_a_main.groupby("indexador_tipo"):
                fig_taxa.add_trace(go.Scatter(
                    x=sub["data"], y=sub["tx_indicativa"] * 100,
                    name=f"ANBIMA ({idx_tipo})",
                    mode="lines", line=dict(color=MARROM, width=2, dash="dash"),
                    hovertemplate=f"ANBIMA {idx_tipo}<br>%{{x|%d/%m/%Y}}<br>%{{y:.3f}}%<extra></extra>",
                ))
    fig_taxa.update_layout(**_base(f"{ticker} — Taxa Indicativa (% a.a.)", 360, legend=True))
    fig_taxa.update_yaxes(ticksuffix="%")
    fig_taxa.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.06,
                                       xanchor="center", x=0.5, font=dict(size=11)))

    # Series para spread (em bps)
    # Spread: uma linha por fonte de PU (BTG, Daycoval, XP, Anbima); valores de Par
    # geralmente nao tem spread (sao taxa de par/cupom contratual).
    fig_spread = go.Figure()
    if not df_b.empty and "spread" in df_b.columns:
        df_b_sp = df_b.dropna(subset=["spread"]).copy()
        # remove outliers obvios (spread bruto vindo como ticker no parse bug)
        df_b_sp = df_b_sp[pd.to_numeric(df_b_sp["spread"], errors="coerce").notna()]
        df_b_sp["spread"] = df_b_sp["spread"].astype(float)
        # cores estaveis por fonte
        cores_tipo = {"BTG": VERDE, "Daycoval": MARROM, "XP": "#8b5e3c",
                      "Anbima": "#a87d4f", "Par": "#5d3a1f"}
        for tipo, sub in df_b_sp.groupby("tipo"):
            sub = sub.sort_values("data")
            fig_spread.add_trace(go.Scatter(
                x=sub["data"], y=sub["spread"] * 10000,
                name=f"Spread {tipo} (bps)",
                mode="lines",
                line=dict(color=cores_tipo.get(tipo, VERDE), width=2),
                hovertemplate=f"{tipo}<br>%{{x|%d/%m/%Y}}<br>%{{y:.1f}} bps<extra></extra>",
            ))
    fig_spread.update_layout(**_base(f"{ticker} — Spread (bps)", 320, legend=True))
    fig_spread.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.06,
                                          xanchor="center", x=0.5, font=dict(size=11)))

    # Series para PU
    fig_pu = go.Figure()
    if not df_b.empty and "pu" in df_b.columns:
        df_b_pu = df_b[df_b["tipo"].fillna("") == "Par"].dropna(subset=["pu"])
        if not df_b_pu.empty:
            fig_pu.add_trace(go.Scatter(
                x=df_b_pu["data"], y=df_b_pu["pu"],
                name="PU Bocaina",
                mode="lines", line=dict(color=VERDE, width=2),
                hovertemplate="Bocaina<br>%{x|%d/%m/%Y}<br>R$ %{y:,.2f}<extra></extra>",
            ))
    if not df_a.empty and "pu" in df_a.columns:
        df_a_pu = df_a.dropna(subset=["pu"])
        if not df_a_pu.empty:
            for idx_tipo, sub in df_a_pu.groupby("indexador_tipo"):
                fig_pu.add_trace(go.Scatter(
                    x=sub["data"], y=sub["pu"],
                    name=f"PU ANBIMA ({idx_tipo})",
                    mode="lines", line=dict(color=MARROM, width=2, dash="dash"),
                    hovertemplate=f"ANBIMA<br>%{{x|%d/%m/%Y}}<br>R$ %{{y:,.2f}}<extra></extra>",
                ))
    fig_pu.update_layout(**_base(f"{ticker} — PU (R$)", 320, legend=True))

    return html.Div([
        dcc.Graph(figure=fig_taxa, config={"displayModeBar": False}),
        dcc.Graph(figure=fig_spread, config={"displayModeBar": False}),
        dcc.Graph(figure=fig_pu, config={"displayModeBar": False}),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# RUN
# ══════════════════════════════════════════════════════════════════════════════

_auth_user = os.environ.get("BASIC_AUTH_USER")
_auth_pass = os.environ.get("BASIC_AUTH_PASS")
if _auth_user and _auth_pass:
    import dash_auth
    dash_auth.BasicAuth(app, {_auth_user: _auth_pass})

if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)

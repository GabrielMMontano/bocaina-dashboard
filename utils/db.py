import os
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = "https://jrmjtfpledyuvwvwigyw.supabase.co"

def _key() -> str:
    # Tenta st.secrets primeiro (Streamlit Cloud), depois .env (local)
    key = ""
    try:
        key = st.secrets.get("SUPABASE_SERVICE_KEY", "")
    except Exception:
        pass
    if not key:
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
    return key

def _headers() -> dict:
    k = _key()
    return {
        "Authorization": f"Bearer {k}",
        "apikey": k,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

# Sem @st.cache_data aqui — o cache fica nas funções load() de cada página
def query(table: str, select: str = "*", filters: dict | None = None,
          order: str | None = None, limit: int | None = None) -> pd.DataFrame:
    params: dict = {"select": select}
    if order:
        params["order"] = order
    if limit:
        params["limit"] = limit
    if filters:
        params.update(filters)
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    if not r.ok:
        st.error(f"Erro ao consultar `{table}`: HTTP {r.status_code} — {r.text[:300]}")
        return pd.DataFrame()
    data = r.json()
    if isinstance(data, dict) and "message" in data:
        st.error(f"Supabase erro em `{table}`: {data.get('message', '')}")
        return pd.DataFrame()
    return pd.DataFrame(data)

@st.cache_data(ttl=300)
def latest_date(table: str, col: str = "data_ref") -> str:
    df = query(table, select=col, order=f"{col}.desc", limit=1)
    return str(df.iloc[0][col]) if not df.empty else ""

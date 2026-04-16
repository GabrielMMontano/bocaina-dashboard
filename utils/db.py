import os
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = "https://jrmjtfpledyuvwvwigyw.supabase.co"

# Chave pública (anon) — segura para expor, RLS habilitado
_ANON_KEY_DEFAULT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpybWp0ZnBsZWR5dXZ3dndpZ3l3"
    "Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYxOTEyODgsImV4cCI6MjA5MTc2NzI4OH0"
    ".s1vor5gyfgGm08UovtYzpxwzQNgJLLikiOzFsOZEM18"
)

def _key() -> str:
    key = ""
    try:
        key = (st.secrets.get("SUPABASE_ANON_KEY", "")
               or st.secrets.get("SUPABASE_PUBLISHABLE_KEY", "")
               or st.secrets.get("SUPABASE_SERVICE_KEY", ""))
    except Exception:
        pass
    if not key:
        key = (os.getenv("SUPABASE_ANON_KEY", "")
               or os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
               or os.getenv("SUPABASE_SERVICE_KEY", ""))
    return key or _ANON_KEY_DEFAULT

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
    try:
        r = requests.get(url, headers=_headers(), params=params, timeout=30)
    except requests.RequestException as exc:
        st.error(f"Erro de conexão ao consultar `{table}`: {exc}")
        return pd.DataFrame()
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

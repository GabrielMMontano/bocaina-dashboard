import os
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = "https://jrmjtfpledyuvwvwigyw.supabase.co"

def _key() -> str:
    # Streamlit Cloud: usa st.secrets; local: usa .env
    try:
        return st.secrets["SUPABASE_SERVICE_KEY"]
    except Exception:
        return os.getenv("SUPABASE_SERVICE_KEY", "")

def _headers() -> dict:
    k = _key()
    return {
        "Authorization": f"Bearer {k}",
        "apikey": k,
        "Content-Type": "application/json",
    }

@st.cache_data(ttl=300)
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
    r.raise_for_status()
    return pd.DataFrame(r.json())

@st.cache_data(ttl=300)
def latest_date(table: str, col: str = "data_ref") -> str:
    df = query(table, select=col, order=f"{col}.desc", limit=1)
    return str(df.iloc[0][col]) if not df.empty else ""

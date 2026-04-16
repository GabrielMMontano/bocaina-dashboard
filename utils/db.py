import os
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://jrmjtfpledyuvwvwigyw.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }


@st.cache_data(ttl=300)
def query(table: str, select: str = "*", filters: dict | None = None,
          order: str | None = None, limit: int | None = None) -> pd.DataFrame:
    """Faz SELECT via PostgREST e retorna DataFrame."""
    params: dict = {"select": select}
    if order:
        params["order"] = order
    if limit:
        params["limit"] = limit
    if filters:
        params.update(filters)

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json())
    return df


@st.cache_data(ttl=300)
def latest_date(table: str, date_col: str = "data_ref") -> str:
    """Retorna a data mais recente de uma tabela/view."""
    df = query(table, select=date_col, order=f"{date_col}.desc", limit=1)
    if df.empty:
        return ""
    return str(df.iloc[0][date_col])

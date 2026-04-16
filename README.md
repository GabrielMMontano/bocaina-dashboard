# Bocaina Dashboard — Screening de Crédito Privado

Dashboard Streamlit para análise de debêntures (IPCA+, CDI+) com dados do Supabase.

**Deploy:** https://bocaina.streamlit.app

---

## Estrutura

```
app.py                  # Página principal (KPIs + gráficos 60d + Top 10)
pages/
  1_Historico.py        # Série histórica 5 anos
  2_Mercado.py          # Scatter + tabela completa do dia
  3_Setores.py          # Análise por setor (barras, heatmap, bubble)
utils/
  db.py                 # Camada de acesso ao Supabase (PostgREST)
supabase/
  rls_policies.sql      # Policies RLS para migrar de service_role → anon
.streamlit/
  config.toml           # Tema Bocaina (verde escuro)
```

---

## Setup local

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # Preencher SUPABASE_ANON_KEY
streamlit run app.py
```

---

## Secrets

### Regra de ouro

> **Nunca use a `service_role` key em um app público.**
> Ela bypassa o RLS e dá acesso irrestrito (leitura e escrita) a todo o banco.

### Configuração correta (anon key + RLS)

1. No **Supabase Dashboard → Project Settings → API**, copie a chave **`anon public`**.
2. Execute `supabase/rls_policies.sql` no **SQL Editor** do Supabase para habilitar RLS e
   conceder SELECT ao role `anon` nas views e tabelas usadas pelo dashboard.
3. No **Streamlit Cloud → App Settings → Secrets**, adicione:
   ```toml
   SUPABASE_ANON_KEY = "sua_anon_key_aqui"
   ```
4. Remova `SUPABASE_SERVICE_KEY` do painel do Streamlit Cloud.

### Dev local

Copie `.env.example` para `.env` e preencha `SUPABASE_ANON_KEY`.
O arquivo `.env` está no `.gitignore` — nunca será commitado.

### O que NÃO commitar

| Arquivo | Motivo |
|---------|--------|
| `.env` | Contém chaves reais |
| `.streamlit/secrets.toml` | Contém chaves reais |
| Qualquer `*_key`, `*_secret`, `eyJhbGci...` | JWT / API keys |

---

## Views Supabase

| View | Uso |
|------|-----|
| `vw_series_historico` | Série histórica de spreads |
| `vw_ativos_enriquecido` | Ativos do dia com rating, setor, duration |
| `vw_spread_por_setor` | Agregação por setor e faixa de rating |
| `fato_debentures` | Tabela fato (usada apenas para `latest_date`) |

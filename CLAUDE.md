# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run full pipeline (ETL + market indicators)
python run_pipeline.py

# Run only step 1 (process ZIP files -> SQLite)
python run_pipeline.py --step 1

# Run only step 2 (fetch CDI, seed fundos, load Setor_Rating, create view)
python run_pipeline.py --step 2

# Reprocess everything, ignoring the processed-files log
python run_pipeline.py --rerun

# Run individual ETL scripts directly
python etl/processar_carteiras.py [--rerun]
python etl/indicadores_mercado.py [--rerun]

# Launch the Dash dashboard (http://localhost:8050)
python painel.py
```

**Dependencies:** `pip install openpyxl requests pandas dash plotly`

**First-time setup:** Create `data/` directory before running the pipeline -- SQLite DB is created there automatically.

**Log files:** `pipeline.log` and `indicadores.log` are written to the project root.

## Architecture

This is a two-stage ETL pipeline feeding a Plotly Dash dashboard for Bocaina Capital's FI-INFRA (infrastructure bond) funds.

### Pipeline flow

```
Carteiras_STB/*.zip          --+
Carteiras_D60s/*.zip         --+
Carteiras_BODB/*.zip         --+--> etl/processar_carteiras.py --> data/carteiras_btg.db (fact_* tables)
Carteiras_BODI/*.zip         --+
Carteiras_Incentivados/*.zip --+
                                                                        |
Rating_Setor/Rating_Setor.xlsx -----> etl/indicadores_mercado.py ------+
BCB API (CDI serie 12) -----------------------------------------------+
                                                                        |
                                                                 vw_carteira_consolidada
                                                                        |
                                                               painel.py (Dash app)
```

### Input directories (5 total, ~3705 ZIPs)

| Directory | ZIPs | Funds | Notes |
|---|---|---|---|
| `Carteiras_STB` | 76 | BOCAINA_STB_RF_INFRA | Standalone D360 |
| `Carteiras_D60s` | 876 | 3 FICs + 3 Masters | D60 CDI/IPCA/Inst |
| `Carteiras_BODB` | 2170 | 1 FIC + 5 Masters + BG_FIM_CP | BODB product; D60 Masters duplicated here |
| `Carteiras_BODI` | 23 | 1 FIC + 1 Master | BODI product |
| `Carteiras_Incentivados` | 560 | 3 FICs + 1 Master | Incentivados product |

### Fund structure (FIC <-> Master)

`ref_fundos` (21 rows) and `ref_fic_master` (12 relations) model the full structure:

- **STB:** BOCAINA_STB_RF_INFRA (standalone, no FIC/Master split)
- **D60:** 3 FICs -> 3 Masters (1:1 each)
  - CDI: BOCAINA_60_CDI_FCRF -> BOCAINA_60_INFR_RF
  - IPCA: BOCAINA_IPCA_60_FCRF -> BOCAINA_60_IPCA_FIRF
  - INST: BOCAINA_60_INST_FCRF -> BOCAINA_INFR_60_FIRF
- **BODB:** 1 FIC -> 5 Masters (1:N)
  - BOCAINA_FC_RF_INFRA -> M_I_RF, MASTER_II_RF, MSTR_3_RF, MAST_V_FIRF, INF_M_4_FIRF
- **BODI:** 1 FIC -> 1 Master
  - BOCAINA_FIC_INFRA_RF -> BOCAINA_INFRA_M_RF
- **Incentivados:** 3 FICs -> 1 Master (N:1)
  - BOCAINA_INFR_FICRF -> BOCAINA_INC_INFRA_RF
  - BOCAINA_I_FC_RF_CL_A -> BOCAINA_INC_INFRA_RF
  - BOCAINA_CL_A_I_FC_RF -> BOCAINA_INC_INFRA_RF

Seed data is hardcoded in `_FUNDOS` and `_FIC_MASTER` lists in `indicadores_mercado.py`.

### ETL: `etl/processar_carteiras.py`

Reads daily position ZIP files from BTG across all 5 directories. Each ZIP contains one or more `.xlsx` files (BODB ZIPs carry up to 5 XLSX -- one per Master fund). Processing:
1. Scans all 5 `CARTEIRA_DIRS` for `*.zip` files
2. Reads each XLSX via `openpyxl` into a grid
3. Detects section markers (e.g. `Resumo`, `Rentabilidade`, `Titulos_Privados`) by checking that col A matches a known prefix and all other columns are `None`
4. Extracts each section's headers + rows positionally (columns are mapped by position, not header name)
5. Inserts via `INSERT OR REPLACE` into the corresponding `fact_*` table
6. Logs each ZIP to `log_processamento` with directory origin; already-processed ZIPs are skipped unless `--rerun`

**Section prefixes** (order matters -- longer prefixes first):
- titulos_privados, titulos_publicos, compromissada_longa, compromissada_over, compromissada, rentabilidade, despesas, resumo, bmf, portfolio_investido

**9 inserters:** resumo, rentabilidade, compromissada, compromissada_longa, titulos_publicos, titulos_privados, bmf, despesas, portfolio_investido

**Deduplication:** BODB contains D60 Master ZIPs that also appear in Carteiras_D60s. `INSERT OR REPLACE` handles this naturally -- later inserts overwrite earlier ones for the same natural key.

### ETL: `etl/indicadores_mercado.py`

1. **Seed** `ref_fundos` (21 funds) and `ref_fic_master` (12 relations) from hardcoded lists
2. **CDI:** Fetches daily CDI from BCB SGS API (serie 12) for all dates in `fact_rentabilidade`, inserts into `ref_indicadores`
3. **Setor/Rating:** Loads `Rating_Setor/Rating_Setor.xlsx` into `ref_setor_rating` (9 columns: codigo, volume_serie, indexador, emissor, setor, rating_anterior, rating, ultima_aval, tipo). Headers on row 2, data from row 3.
4. **View:** Recreates `vw_carteira_consolidada` joining fact_titulos_privados <-> ref_fundos <-> ref_setor_rating <-> fact_rentabilidade <-> ref_indicadores

### Database: `data/carteiras_btg.db` (SQLite, ~41 MB)

| Table / View | Rows | Description |
|---|---|---|
| `ref_fundos` | 21 | Fund registry (fundo, tipo, produto, display) |
| `ref_fic_master` | 12 | FIC<->Master relationships (N:N) |
| `ref_setor_rating` | 54 | Sector + rating per 6-char ticker (9 columns) |
| `ref_indicadores` | 1054 | Daily CDI values |
| `fact_resumo` | 41572 | Fund balance summary per date |
| `fact_rentabilidade` | 7092 | NAV, returns (day/month/semester/year), pct CDI |
| `fact_compromissada` | 7006 | Repo (overnight) positions |
| `fact_compromissada_longa` | 1211 | Long-term repo positions |
| `fact_titulos_publicos` | 654 | Government bonds |
| `fact_titulos_privados` | 69646 | Private credit / debentures incentivadas |
| `fact_bmf` | 3457 | Futures/derivatives (BMF) |
| `fact_despesas` | 47207 | Fund expenses |
| `fact_portfolio_investido` | 5671 | FIC->Master allocation (portfolio invested) |
| `log_processamento` | 3705 | Pipeline run history (with directory) |
| `vw_carteira_consolidada` | - | Consolidated view for the dashboard |

All `fact_*` tables use `UNIQUE` constraints on the natural key (usually `data, fundo, isin` or similar); inserts use `INSERT OR REPLACE`.

The view join key: `UPPER(SUBSTR(t.titulo, 1, 6))` extracts the 6-char ticker from the `titulo` field and matches it against `ref_setor_rating.codigo`. The view also joins `ref_fundos` to add `produto` and `tipo_fundo` columns.

### Dashboard: `painel.py`

Dash multi-page app. Four funds are configured in the `FUNDS` dict:
- **STB** -- `rent_fundo == carteira_fundo == "BOCAINA_STB_RF_INFRA"`
- **D60_CDI / D60_IPCA / D60_INST** -- D60 funds with FIC/Master split: `rent_fundo` is the FIC (used for rentabilidade), `carteira_fundo` is the Master (used for titulos, compromissada, despesas)

Fund names stored in the DB use underscores (e.g. `BOCAINA_60_CDI_FCRF`), not the display names. The `FUNDS` dict maps both `rent_fundo` and `carteira_fundo` DB names for each fund key.

The `FUNDS` dict is the single source of truth for which fund names appear in the dashboard. If new funds/products (BODB, BODI, Incentivados) are added to the dashboard, update this dict first.

Color palette: `PALHA = #fff0dc`, `VERDE = #0a2300`, `MARROM = #cdaa82`. Custom font: Gotham HTF (loaded from `assets/`).

### Input data conventions

- ZIP filenames follow `YYYYMMDD-*.zip` (date prefix used for sorting)
- XLSX cells may contain dates as Excel serials (int/float), `DD/MM/YYYY` strings, or Python `date`/`datetime` objects -- all handled by `to_date()` in `processar_carteiras.py`
- Indexador classification (CDI+, IPCA+, etc.) is derived from the `titulo` field string matching in `_classify_indexador()` in `painel.py`

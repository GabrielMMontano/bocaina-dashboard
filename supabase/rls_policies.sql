-- ============================================================
-- RLS Policies — Bocaina Dashboard (leitura pública com anon key)
-- Rodar no SQL Editor do Supabase: https://supabase.com/dashboard
-- ANTES de trocar a secret no Streamlit Cloud de service_role → anon
-- ============================================================

-- 1. Habilitar RLS nas tabelas base
ALTER TABLE fato_debentures    ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_ativo          ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_setor          ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_indexador      ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_rating         ENABLE ROW LEVEL SECURITY;
ALTER TABLE serie_historica    ENABLE ROW LEVEL SECURITY;

-- 2. Policies de SELECT para o role anon (leitura pública)
CREATE POLICY "anon pode ler fato_debentures"
    ON fato_debentures FOR SELECT TO anon USING (true);

CREATE POLICY "anon pode ler dim_ativo"
    ON dim_ativo FOR SELECT TO anon USING (true);

CREATE POLICY "anon pode ler dim_setor"
    ON dim_setor FOR SELECT TO anon USING (true);

CREATE POLICY "anon pode ler dim_indexador"
    ON dim_indexador FOR SELECT TO anon USING (true);

CREATE POLICY "anon pode ler dim_rating"
    ON dim_rating FOR SELECT TO anon USING (true);

CREATE POLICY "anon pode ler serie_historica"
    ON serie_historica FOR SELECT TO anon USING (true);

-- 3. GRANT SELECT nas views para o role anon
--    (views no Postgres herdam segurança do owner por padrão;
--     o GRANT garante que anon pode chamar via PostgREST)
GRANT SELECT ON vw_series_historico   TO anon;
GRANT SELECT ON vw_ativos_enriquecido TO anon;
GRANT SELECT ON vw_spread_por_setor   TO anon;
GRANT SELECT ON fato_debentures       TO anon;

-- 4. Se as views usarem SECURITY DEFINER, verificar que o owner
--    tem acesso. Caso contrário, recriar com SECURITY INVOKER:
--
--    ALTER VIEW vw_series_historico   SECURITY INVOKER;
--    ALTER VIEW vw_ativos_enriquecido SECURITY INVOKER;
--    ALTER VIEW vw_spread_por_setor   SECURITY INVOKER;
--
-- 5. Após executar este script:
--    - Copiar a anon key do painel Supabase (Project Settings → API → anon public)
--    - Atualizar o secret no Streamlit Cloud:
--        SUPABASE_ANON_KEY = <anon key>
--      (remover SUPABASE_SERVICE_KEY do painel do Streamlit)
--    - Testar o app; se aparecer 403/401, verificar o passo 4 (SECURITY INVOKER)

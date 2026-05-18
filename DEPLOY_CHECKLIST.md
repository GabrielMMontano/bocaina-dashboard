# Deploy Checklist — Bocaina Dashboard no Render

## 1. Preparar repositório Git (local)

```bash
cd <pasta do projeto>
git init
git add painel.py assets/ requirements.txt Dockerfile render.yaml .gitignore .dockerignore
git commit -m "feat: deploy inicial bocaina dashboard"
```

> **Confirme antes do commit:** `git status` não deve mostrar nenhum .db, .xlsx, .zip, .csv ou Carteiras_*.

## 2. Criar repositório no GitHub

1. Acesse github.com → New repository → `bocaina-dashboard` (privado)
2. Conecte e envie:

```bash
git remote add origin https://github.com/<seu-usuario>/bocaina-dashboard.git
git push -u origin main
```

## 3. Criar serviço no Render

1. Acesse render.com → New → Web Service
2. Conecte o repositório `bocaina-dashboard`
3. Render detecta o `render.yaml` automaticamente — confirme as configs
4. Em **Environment Variables**, defina manualmente (sync: false):
   - `BASIC_AUTH_USER` → usuário desejado
   - `BASIC_AUTH_PASS` → senha forte
5. Clique em **Create Web Service**

## 4. Fazer upload do banco para o disco Render

O disco `/data` está vazio no primeiro deploy. Após o serviço subir:

**Opção A — via Render Shell** (mais simples):
1. No painel do serviço → Shell
2. `ls /data` (deve estar vazio)

**Opção B — via scp/rsync** se o Render liberar SSH:
```bash
scp dashboard.db <ssh-host-render>:/data/dashboard.db
```

**Opção C — script de seed** (recomendado para automação futura):
Crie um endpoint protegido ou script separado que recebe o .db via upload.

> Por enquanto, a forma mais prática é usar o **Render Shell** e fazer upload via `curl` de um pré-signed URL ou copiar o arquivo manualmente pela interface.

## 5. Verificar deploy

- Acesse a URL do serviço (ex: `https://bocaina-dashboard.onrender.com`)
- Login com as credenciais definidas nas env vars
- Confirme que o dashboard carrega com dados

## 6. Atualizar o banco (rotina)

Sempre que rodar `run_pipeline.py` localmente e gerar um novo `dashboard.db`:

1. Copie para o disco Render via Render Shell ou scp
2. O app lê o DB em read-only — não precisa reiniciar

## Observações

- O disco Render persiste entre deploys — o .db não é apagado em redeploys de código.
- Plano Starter inclui 1 disco de até 5 GB (configurado no render.yaml).
- Se o serviço ficar inativo (plano free), ele dorme — considere upgrade para Starter pago para evitar cold starts.

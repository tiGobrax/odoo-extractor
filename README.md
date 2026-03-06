# Odoo Extractor

[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue)](https://github.com/tiGobrax/odoo-extractor)

Extrator de dados do Odoo usando XML-RPC, com suporte a paginação automática, retry inteligente e exportação para Parquet usando Polars.

**Repositório:** [https://github.com/tiGobrax/odoo-extractor](https://github.com/tiGobrax/odoo-extractor)

## 🚀 Características

- ✅ Conexão segura via XML-RPC com autenticação
- ✅ Paginação automática para grandes volumes de dados
- ✅ Retry inteligente com categorização de erros (temporários vs permanentes)
- ✅ Exportação para Parquet usando Polars
- ✅ Timeout configurável para requisições
- ✅ Logging detalhado com Loguru
- ✅ Suporte a Docker

## 🧠 Arquitetura em Alto Nível

- **API FastAPI (`MODE=service`)** expõe endpoints para health check, atualização/listagem do registry de models e execução incremental/full do ETL.
- **Cloud Run Job / batch (`MODE=job`)** reutiliza a mesma engine para full extract sem servidor HTTP (`app/jobs/full_extract_job.py`).
- **Engine (`app/engine`)** concentra regra de negócio: controle de cursores, sanitização de registros, escrita em Parquet + upload no GCS.
- **Cliente Odoo (`src/odoo_extractor`)** encapsula autenticação, paginação e políticas de retry/classificação de erros da API XML-RPC.
- **Persistência (`src/storage.py`, `app/engine/cursor_store.py`, `app/engine/models_registry.py`)** escreve datasets, cursores incrementais e `models_list.csv` dentro do mesmo bucket/prefixo no GCS.
- **Ferramentas auxiliares**: script de análise de Parquet (`parquet_analysis/`), manifests Terraform (`terraform/`) e guia de deploy no EKS (`DEPLOY.md`).

## 📋 Pré-requisitos

- Python 3.11+
- Conta no Odoo com acesso à API
- Variáveis de ambiente configuradas (veja `.env.example`)

## 🧪 Setup e Execução Local (Python)

1. **Clonar e criar ambiente virtual**
   ```bash
   git clone https://github.com/tiGobrax/odoo-extractor
   cd odoo-extractor
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
2. **Configurar o arquivo `.env`**
   ```bash
   cp env.example .env
   # edite ODOO_URL/DB/USERNAME/PASSWORD e GOOGLE_APPLICATION_CREDENTIALS
   ```
3. **Executar a API (modo service, FastAPI)**
   ```bash
   MODE=service PORT=8080 python -m app.main
   # API disponível em http://127.0.0.1:8080
   ```
4. **Executar um batch completo (modo job)**
   ```bash
   MODE=job ODOO_BATCH_SIZE=5000 python -m app.main
   ```
   O job usa `app/jobs/full_extract_job.py`, resolve a lista de models no registry (GCS) e grava Parquets diretamente no bucket configurado.

## 🔧 Execução com Docker

```bash
docker-compose up --build
```

Ou usando Docker diretamente:

```bash
docker build -t odoo-extractor .
docker run --env-file .env odoo-extractor
```

## ⚙️ Configuração

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```env
ODOO_URL=https://seu-dominio.odoo.com
ODOO_DB=nome-do-banco
ODOO_USERNAME=seu-usuario@email.com
ODOO_PASSWORD=sua-api-key
GOOGLE_APPLICATION_CREDENTIALS=/app/creds/odoo-etl.json
```

### Variáveis de Ambiente

| Variável | Descrição | Obrigatória | Padrão |
|----------|-----------|-------------|--------|
| `ODOO_URL` | URL base do Odoo | Sim | - |
| `ODOO_DB` | Nome do banco de dados | Sim | - |
| `ODOO_USERNAME` | Usuário para autenticação | Sim | - |
| `ODOO_PASSWORD` | API Key ou senha | Sim | - |
| `GOOGLE_APPLICATION_CREDENTIALS` | Caminho para o JSON da service account com acesso ao bucket (apenas fora do GCP) | Não | `/app/creds/odoo-etl.json` |
| `MODE` | Define se o processo sobe API (`service`) ou roda o job (`job`) | Não | `service` |
| `PORT` | Porta da API quando em modo serviço | Não | `8080` |
| `ODOO_MODELS_PREFIX` | Filtra os models do registry por prefixo quando `MODE=job` | Não | vazio |

## 🧭 Modos de Execução

| Modo | Variável | Entrypoint | Descrição |
|------|----------|------------|-----------|
| Service (API) | `MODE=service` | `uvicorn app.api.app:app` (via `start.sh` ou `python -m app.main`) | Expõe endpoints REST para disparar extrações, atualizar registry e health-check. |
| Job (batch) | `MODE=job` | `python -m app.main` → `app/jobs/full_extract_job.py` | Executa full extract fora do contexto HTTP, ideal para Cloud Run Job, CronJob ou execução manual. |

Ambos os modos reutilizam `run_extraction` (em `app/engine/extractor.py`). A diferença é somente o wrapper que aciona a engine.

## ☁️ Armazenamento no Google Cloud Storage

Todos os datasets extraídos são enviados diretamente para o Google Cloud Storage. Cada model recebe sua própria pasta abaixo do prefixo configurado (`GCS_BASE_PATH`), por exemplo:

- `gs://gobrax-data-lake/data-lake/odoo/stock_lot/<timestamp>.parquet`
- `gs://gobrax-data-lake/data-lake/odoo/account_account/<timestamp>.parquet`
- `gs://gobrax-data-lake/data-lake/odoo/crm_stage/<timestamp>.parquet`
- `gs://gobrax-data-lake/data-lake/odoo/models_list.csv`

O projeto **não remove arquivos do GCS**, apenas adiciona novos Parquet a cada execução.

Todo arquivo inclui a coluna `ingestion_ts` em UTC (ISO 8601), permitindo filtrar facilmente o lote mais recente na camada silver.

Campos complexos (listas/dicionários retornados por relacionamentos do Odoo) são serializados como JSON para evitar inconsistências de tipo entre registros.

Além dos Parquet, o mesmo bucket/prefixo hospeda:
- `models_list.csv`: resultado do `ModelsRegistry`, atualizado via endpoint `/models/update`.
- `cursors/<model>.json`: cursores incrementais (write_date/id) persistidos pela `CursorStore`.

Para rodar em Docker, monte o JSON da service account no container e aponte `GOOGLE_APPLICATION_CREDENTIALS` para o caminho interno. O `docker-compose.yml` de exemplo já expõe o segredo via volume somente leitura (`./odoo-etl@gobrax-data.iam.gserviceaccount.com.json:/app/creds/odoo-etl.json:ro`).
> ℹ️ Os valores padrão de bucket/prefixo (`gobrax-data-lake` / `data-lake/odoo`) estão definidos nos módulos `src/storage.py`, `app/engine/cursor_store.py` e `app/engine/models_registry.py`. Ajuste-os se precisar apontar para outro data lake.

## 🏃 Rodar com Docker (Passo a Passo)

### 1. Clone o repositório

```bash
git clone https://github.com/tiGobrax/odoo-extractor
cd odoo-extractor
```

### 2. Configure as variáveis de ambiente

Copie o arquivo de exemplo e edite com suas credenciais:

```bash
cp env.example .env
# Edite o arquivo .env com suas credenciais do Odoo
```

> 💡 Posicione o arquivo JSON da service account na raiz do projeto e mantenha o nome configurado no `docker-compose.yml` (ou ajuste o volume) para que o container consiga ler `GOOGLE_APPLICATION_CREDENTIALS`.

### 3. Execute a aplicação

**Opção A: API (FastAPI com Uvicorn)**

```bash
docker compose up --build
```

A API estará disponível em `http://127.0.0.1:18080` (o container escuta em `PORT=8000`, mas o `docker-compose.yml` publica `18080:8000`; sem override, o padrão interno é `8080`).

**Opção B: Execução batch (job)**

```bash
docker compose run --rm -e MODE=job odoo-extractor python -m app.main
```

### Atualizar registry de models (CSV no GCS)

1. **Garanta que a API esteja rodando localmente**:

   ```bash
   docker compose up --build
   ```

2. **Dispare a atualização do registry** (o endpoint `/models/update` gera o `models_list.csv` dentro da pasta `odoo` no GCS):

   ```bash
   curl -X POST "http://127.0.0.1:18080/models/update"
   ```

### 4. Testar a API (se usando Opção A)

Execute uma requisição para o endpoint de ETL:

```bash
curl -X POST "http://127.0.0.1:18080/run/inc"
```

### 5. Documentação da API (se usando FastAPI)

Acesse a documentação interativa em:
- Swagger UI: `http://127.0.0.1:18080/docs`
- ReDoc: `http://127.0.0.1:18080/redoc`

## 📡 Endpoints da API

| Método | Caminho | Descrição |
|--------|---------|-----------|
| `GET` | `/health` | Health check simples. |
| `POST` | `/models/update` | Consulta `ir.model`, salva `models_list.csv` no GCS. |
| `GET` | `/models/list` | Retorna a lista atual armazenada no GCS. |
| `POST` | `/run/inc` | Executa extração incremental (default, usa cursor write_date/id). |
| `POST` | `/run/full` | Executa full refresh ignorando cursores. |
| `POST` | `/etl/run` | Endpoint legado, mantém comportamento incremental. |

Parâmetros opcionais aceitos nos endpoints de ETL:
- `prefix`: apenas models cujo nome inicia com esse prefixo.
- `fields`: lista customizada de campos (default = todos).
- `limit`: limite de registros por model (apenas para troubleshooting).

## 🧾 Registry de Models e Incremental

1. **Atualize o registry** (`/models/update`) sempre que novos models forem habilitados no Odoo. O arquivo `models_list.csv` fica no mesmo bucket/prefixo configurado na engine.
2. **Liste para verificar** (`/models/list`), especialmente antes de rodar jobs via linha de comando.
3. **Execute o ETL**:
   - Incremental (`/run/inc` ou `MODE=service`/`MODE=job` sem limpar cursores) usa `write_date` + `id` como cursor. Models sem `write_date` caem para full refresh automaticamente.
   - Full refresh (`/run/full` ou `MODE=job`) ignora cursores e não atualiza `last_value`.
   - Para restringir o Cloud Run Job a uma família de models, defina `ODOO_MODELS_PREFIX` (ex.: `stock`).
4. **Cursores** são salvos em `cursors/<model>.json` contendo `cursor_field`, `last_value`, `last_id` e `updated_at`. Caso precise reiniciar de um ponto, remova o arquivo correspondente no bucket.
5. **Falhas controladas**:
   - Erros permanentes de schema/permissão são classificados como `skipped`.
   - Erros temporários disparam retry com backoff e reconexão automática da sessão XML-RPC.

## 📖 Uso

### Uso Básico

Para executar o pipeline completo sem subir a API, defina `MODE=job` e chame o mesmo entrypoint principal:

```bash
docker compose run --rm -e MODE=job odoo-extractor python -m app.main
```

Os Parquet são gravados em `gs://gobrax-data-lake/data-lake/odoo/<model>/`.

## 🔍 Análise de Parquets (Ferramenta Auxiliar)

O script `parquet_analysis/analyze_parquets.py` ajuda a inspecionar arquivos no bucket, identificando campos que podem servir como cursor (`write_date`, `__last_update`, etc.), checando min/max/null e exibindo colunas com palavras-chave.

Uso típico:
```bash
python parquet_analysis/analyze_parquets.py \
  --bucket gobrax-data-lake \
  --base-path data-lake/odoo \
  --fields id name write_date \
  --search-terms write date last update \
  --limit 5
```

Principais parâmetros:
- `--bucket` / `--base-path`: mesmo bucket/prefixo usado na engine.
- `--models`: restringe os models analisados; se omisso, lista automaticamente via prefixos do GCS.
- `--fields`: campos fixos que sempre aparecerão no relatório.
- `--search-terms`: termos (case-insensitive) para procurar colunas adicionais.
- `--ignore-fields`: remove campos específicos mesmo que coincidam com termos.

O script baixa apenas o Parquet mais recente de cada model (pelo nome do arquivo) e exibe estatísticas no terminal.

### Rodar análise dentro de um container

Se quiser executar o analisador sem instalar dependências localmente, use o container oficial do Python montando o diretório do projeto e o JSON da service account:

```bash
docker run --rm -it \
  --env-file .env \
  -v "$(pwd)":/workspace \
  -v "$(pwd)/odoo-etl@gobrax-data.iam.gserviceaccount.com.json":/app/creds/odoo-etl.json:ro \
  -w /workspace \
  python:3.11-slim \
  bash -c "pip install --no-cache-dir -r requirements.txt && python parquet_analysis/analyze_parquets.py"
```

Esse comando instala as dependências necessárias dentro do container temporário (sem cache), reaproveita o `.env` local e garante que o script consiga acessar as credenciais do GCS em `/app/creds/odoo-etl.json`. Ajuste o caminho do JSON, parâmetros do script ou `requirements.txt` se estiver usando outro nome/arquivo.

## ☁️ Deploy no Cloud Run

O container expõe o FastAPI com Uvicorn via `start.sh` e automaticamente utiliza a porta definida pela variável `PORT` (Cloud Run define `PORT=8080`). Use o fluxo abaixo para garantir que a imagem publicada está alinhada com o que está no repositório:

1. **Build e push da imagem para o Artifact Registry**
   ```bash
   export PROJECT_ID=gobrax-data           # ajuste conforme o seu projeto
   export REGION=us-central1
   export REPO=odoo-extractor
   export IMAGE_NAME=odoo-extractor

   gcloud builds submit \
     --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}:latest
   ```

2. **Service Account e permissões**
   ```bash
   gcloud iam service-accounts create odoo-extractor \
     --display-name="Service Account do Extrator Odoo"

   gcloud projects add-iam-policy-binding ${PROJECT_ID} \
     --member="serviceAccount:odoo-extractor@${PROJECT_ID}.iam.gserviceaccount.com" \
     --role="roles/storage.objectAdmin"
   gcloud projects add-iam-policy-binding ${PROJECT_ID} \
     --member="serviceAccount:odoo-extractor@${PROJECT_ID}.iam.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor"
   ```

3. **Secrets e variáveis sensíveis**
   ```bash
   printf 'MINHA_API_KEY' | gcloud secrets create odoo-password --data-file=-
   gcloud secrets add-iam-policy-binding projects/${PROJECT_ID}/secrets/odoo-password \
     --member="serviceAccount:odoo-extractor@${PROJECT_ID}.iam.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor"
   ```
   Configure os demais valores (URL, banco, usuário) via `--set-env-vars`. Para o `ODOO_PASSWORD`, prefira `--set-secrets`, evitando expor o valor.

4. **Deploy da API**
   ```bash
   gcloud run deploy odoo-extractor \
     --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}:latest \
     --region ${REGION} --platform managed --allow-unauthenticated \
     --service-account odoo-extractor@${PROJECT_ID}.iam.gserviceaccount.com \
     --set-env-vars ODOO_URL=https://gobrax.odoo.com, \
                    ODOO_DB=gobrax-sh-main-22440471, \
                    ODOO_USERNAME=odoo@gobrax.com \
     --set-secrets ODOO_PASSWORD=odoo-password:latest
   ```
   > Não defina `GOOGLE_APPLICATION_CREDENTIALS` se estiver usando a service account do Cloud Run; o client do GCS utiliza Workload Identity automaticamente.

5. **Observabilidade e troubleshooting**
   - Logs do último deploy:  
     `gcloud run services describe odoo-extractor --region ${REGION} --format='value(status.latestReadyRevisionName)'`  
     `gcloud run logs read odoo-extractor --region ${REGION} --revision <revision>`
   - Quando o erro for “container failed to start”, quase sempre existe um stack trace nos logs de execução indicando variável ausente ou exceção do Python.

Para execuções batch (engine completa sem API), crie um Cloud Run Job reutilizando a mesma imagem e defina `MODE=job` (o `start.sh` já chama `python -m app.main`). Também é possível orquestrar deltas chamando os endpoints `/run/inc` (incremental) ou `/run/full` (full refresh) via DAG sem necessidade de autenticação adicional.

## 🧱 Provisionamento com Terraform

Se preferir automatizar toda a infraestrutura GCP (Artifact Registry, Secret Manager, service account e Cloud Run), utilize os manifests em `terraform/`.
> Para um guia completo de deploy no Amazon EKS (Jobs, CronJobs, IRSA, etc.), consulte `DEPLOY.md`.

1. Configure a autenticação local (`gcloud auth application-default login` ou `GOOGLE_APPLICATION_CREDENTIALS`).
2. Copie o arquivo de variáveis e edite com seus valores:
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # edite o arquivo e substitua tokens/senhas
   ```
3. Inicialize e valide:
   ```bash
   terraform init
   terraform plan
   ```
4. Caso o plano esteja correto, aplique:
   ```bash
   terraform apply
   ```

O módulo habilita as APIs necessárias, cria (ou confirma) o repositório do Artifact Registry, provisiona a service account com as permissões corretas, cadastra o segredo `odoo-password` e implanta o Cloud Run já apontando para a imagem informada. Ajuste `allow_unauthenticated=false` se quiser proteger o endpoint e forneça um `invoker_identity` para controle fino de acesso.

### Uso Programático

```python
from src.odoo_extractor.odoo_client import OdooClient

client = OdooClient()

# Extrair dados de um modelo
records = client.search_read(
    model="res.partner",
    domain=[],  # Filtros Odoo
    fields=client.get_all_fields("res.partner"),  # retorna todos os campos disponíveis
    batch_size=5000,
    limit=None  # None para extrair todos
)

# Converter para Polars DataFrame
import polars as pl
df = pl.DataFrame(records)
```

### Parâmetros do `search_read`

- `model` (str): Nome do modelo Odoo (ex: `res.partner`, `sale.order`)
- `domain` (list): Lista de filtros no formato Odoo (ex: `[('active', '=', True)]`)
- `fields` (list)`: Lista de campos a serem extraídos. Se `None`, usamos `client.get_all_fields(model)` para buscar todos os campos disponíveis.
- `batch_size` (int): Tamanho do lote para paginação (padrão: 5000)
- `limit` (int, opcional): Limite máximo de registros a extrair

## 📁 Estrutura do Projeto

```
odoo-extractor/
├── app/
│   ├── api/                    # FastAPI + autenticação
│   ├── engine/                 # Orquestração da extração
│   ├── jobs/                   # Entrypoints batch (Cloud Run Job)
│   └── main.py                 # Entrypoint único (MODE=service|job)
├── src/
│   ├── utils.py                # Normalização de registros
│   ├── storage.py              # Persistência em GCS (Polars)
│   └── odoo_extractor/         # Cliente XML-RPC, conexão e erros
├── start.sh                    # Script usado pelo container
├── requirements.txt            # Dependências Python
├── Dockerfile                  # Imagem Docker multi-stage
├── docker-compose.yml          # Configuração para desenvolvimento local
├── .env.example                # Exemplo de variáveis de ambiente
├── terraform/                  # Provisionamento opcional na GCP
└── README.md                   # Este arquivo
```

## 🧪 Testes

Ainda não há suíte automatizada publicada neste repositório. Recomendamos adicionar testes com `pytest` quando evoluir o projeto (por exemplo, cobrindo `OdooClient` com mocks de XML-RPC e o fluxo da engine).

## 🔍 Tratamento de Erros

O extrator categoriza automaticamente os erros:

- **Erros Temporários**: Timeouts, problemas de rede, servidor temporariamente indisponível
  - Ação: Retry automático (até 3 tentativas) com backoff exponencial
  
- **Erros Permanentes**: Campos inválidos, modelos inexistentes, permissões negadas
  - Ação: Log de aviso e continuação com próximo modelo

## 📝 Logs

Os logs são exibidos no console usando Loguru com emojis para facilitar a identificação:

- 🔗 Conexão estabelecida
- 📦 Registros carregados
- ✅ Sucesso
- ⚠️ Avisos
- ❌ Erros
- 🚨 Falhas críticas

## 🐳 Docker

### Build da Imagem

```bash
docker build -t odoo-extractor .
```

### Executar Container

```bash
docker run --env-file .env odoo-extractor
```

### Docker Compose

```bash
docker-compose up
```

## 🤝 Contribuindo

1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT.

## 🐛 Problemas Conhecidos

- Alguns modelos podem ter campos que causam erros de schema (são automaticamente ignorados)
- Timeouts podem ocorrer com modelos muito grandes (ajuste a variável `ODOO_BATCH_SIZE` antes da execução)

## 📞 Suporte

Para problemas ou dúvidas, abra uma issue no repositório.


## Orquestracao via Airflow (sem cron no GCP)

Quando a orquestracao e exclusiva no Airflow:

- Use Cloud Run Job `odoo-extractor-full` para full refresh (`MODE=job`, `JOB_TYPE=full`).
- Use Cloud Run Job `odoo-extractor-inc` para incremental (`MODE=job`, `JOB_TYPE=inc`).
- Nao habilite Cloud Scheduler no GCP (`enable_full_extract_scheduler=false`).

O workflow de deploy (`.github/workflows/main.yml`) deve atualizar service e os dois jobs,
mas os disparos ficam sob controle das DAGs no Airflow.

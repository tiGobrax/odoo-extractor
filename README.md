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

## 📋 Pré-requisitos

- Python 3.11+
- Conta no Odoo com acesso à API
- Variáveis de ambiente configuradas (veja `.env.example`)

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
ODOO_MODEL=res.partner
```

### Variáveis de Ambiente

| Variável | Descrição | Obrigatória | Padrão |
|----------|-----------|-------------|--------|
| `ODOO_URL` | URL base do Odoo | Sim | - |
| `ODOO_DB` | Nome do banco de dados | Sim | - |
| `ODOO_USERNAME` | Usuário para autenticação | Sim | - |
| `ODOO_PASSWORD` | API Key ou senha | Sim | - |
| `ODOO_MODEL` | Modelo a ser extraído | Não | `res.partner` |
| `GCS_BUCKET` | Bucket do Google Cloud Storage utilizado para salvar os Parquet | Sim | - |
| `GCS_BASE_PATH` | Prefixo dentro do bucket (cada model vira uma subpasta) | Não | `data-lake/odoo` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Caminho para o JSON da service account com acesso ao bucket | Sim | - |

## ☁️ Armazenamento no Google Cloud Storage

Todos os datasets extraídos são enviados diretamente para o Google Cloud Storage. Cada model recebe sua própria pasta abaixo do prefixo configurado (`GCS_BASE_PATH`), por exemplo:

- `gs://gobrax-data-lake/data-lake/odoo/stock_lot/<timestamp>.parquet`
- `gs://gobrax-data-lake/data-lake/odoo/account_account/<timestamp>.parquet`
- `gs://gobrax-data-lake/data-lake/odoo/crm_stage/<timestamp>.parquet`

O projeto **não remove arquivos do GCS**, apenas adiciona novos Parquet a cada execução.

Todo arquivo inclui a coluna `ingestion_ts` em UTC (ISO 8601), permitindo filtrar facilmente o lote mais recente na camada silver.

Campos complexos (listas/dicionários retornados por relacionamentos do Odoo) são serializados como JSON para evitar inconsistências de tipo entre registros.

Para rodar em Docker, monte o JSON da service account no container e aponte `GOOGLE_APPLICATION_CREDENTIALS` para o caminho interno. O `docker-compose.yml` de exemplo já expõe o segredo via volume somente leitura (`./odoo-etl@gobrax-data.iam.gserviceaccount.com.json:/app/creds/odoo-etl.json:ro`).

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

A API estará disponível em `http://127.0.0.1:8000` (o container usa a variável `PORT`, padrão `8000`).

**Opção B: Script direto (job)**

```bash
docker compose run --rm odoo-extractor python -m src.main
```

### 4. Testar a API (se usando Opção A)

Execute uma requisição para o endpoint de ETL:

```bash
curl -X POST "http://127.0.0.1:8000/etl/run" \
  -H "Authorization: Bearer meu_token"
```

**Nota:** Substitua `meu_token` pelo token de autenticação válido.

### 5. Documentação da API (se usando FastAPI)

Acesse a documentação interativa em:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## 📖 Uso

### Uso Básico

Execute o script principal (dentro do container):

```bash
docker-compose run --rm odoo-extractor python -m src.main
```

Os Parquet serão enviados automaticamente para `gs://<GCS_BUCKET>/<GCS_BASE_PATH>/<model>/`.

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
   Configure os demais valores (URL, banco, usuário, bucket, token da API) via `--set-env-vars`. Para o `ODOO_PASSWORD`, prefira `--set-secrets`, evitando expor o valor.

4. **Deploy da API**
   ```bash
   gcloud run deploy odoo-extractor \
     --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}:latest \
     --region ${REGION} --platform managed --allow-unauthenticated \
     --service-account odoo-extractor@${PROJECT_ID}.iam.gserviceaccount.com \
     --set-env-vars ODOO_URL=https://gobrax.odoo.com, \
                    ODOO_DB=gobrax-sh-main-22440471, \
                    ODOO_USERNAME=odoo@gobrax.com, \
                    GCS_BUCKET=gobrax-data-lake, \
                    GCS_BASE_PATH=data-lake/odoo, \
                    API_TOKEN=meu_token \
     --set-secrets ODOO_PASSWORD=odoo-password:latest
   ```
   > Não defina `GOOGLE_APPLICATION_CREDENTIALS` se estiver usando a service account do Cloud Run; o client do GCS utiliza Workload Identity automaticamente.

5. **Observabilidade e troubleshooting**
   - Logs do último deploy:  
     `gcloud run services describe odoo-extractor --region ${REGION} --format='value(status.latestReadyRevisionName)'`  
     `gcloud run logs read odoo-extractor --region ${REGION} --revision <revision>`
   - Quando o erro for “container failed to start”, quase sempre existe um stack trace nos logs de execução indicando variável ausente ou exceção do Python.

Para execuções batch (equivalente a `python -m src.main`), crie um Cloud Run Job reutilizando a mesma imagem e comando `python -m src.main`, ou acione o endpoint `/etl/run` via DAG (Composer/Airflow) usando `Authorization: Bearer <API_TOKEN>`.

## 🧱 Provisionamento com Terraform

Se preferir automatizar toda a infraestrutura GCP (Artifact Registry, Secret Manager, service account e Cloud Run), utilize os manifests em `terraform/`.

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
├── src/
│   ├── main.py                 # Script principal
│   └── odoo_extractor/
│       ├── __init__.py
│       └── odoo_client.py      # Cliente Odoo
├── data/                       # Dados extraídos (Parquet)
├── tests/                      # Testes unitários
├── requirements.txt            # Dependências Python
├── Dockerfile                  # Imagem Docker
├── docker-compose.yml          # Configuração Docker Compose
├── .env.example               # Exemplo de variáveis de ambiente
└── README.md                  # Este arquivo
```

## 🧪 Testes

Execute os testes:

```bash
pytest tests/
```

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
- Timeouts podem ocorrer com modelos muito grandes (ajuste o `batch_size`)

## 📞 Suporte

Para problemas ou dúvidas, abra uma issue no repositório.


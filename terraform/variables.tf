variable "project_id" {
  description = "ID do projeto GCP"
  type        = string
}

variable "region" {
  description = "Região padrão para recursos (ex: us-central1)"
  type        = string
}

variable "environment" {
  description = "Rótulo de ambiente para tagging"
  type        = string
  default     = "dev"
}

variable "service_account_name" {
  description = "Nome curto da service account usada pelo Cloud Run"
  type        = string
  default     = "odoo-extractor"
}

variable "artifact_registry_repo" {
  description = "Nome do repositório no Artifact Registry"
  type        = string
  default     = "odoo-extractor"
}

variable "cloud_run_service_name" {
  description = "Nome do serviço Cloud Run"
  type        = string
  default     = "odoo-extractor"
}

variable "container_image" {
  description = "Imagem container publicada no Artifact Registry"
  type        = string
}

variable "container_port" {
  description = "Porta interna exposta pelo container"
  type        = number
  default     = 8080
}

variable "odoo_url" {
  description = "URL base do Odoo"
  type        = string
}

variable "odoo_db" {
  description = "Nome do banco do Odoo"
  type        = string
}

variable "odoo_username" {
  description = "Usuário/API key ID para autenticar no Odoo"
  type        = string
}

variable "odoo_password" {
  description = "Senha/API key do Odoo"
  type        = string
  sensitive   = true
}

variable "odoo_password_secret_name" {
  description = "Nome do secret no Secret Manager"
  type        = string
  default     = "odoo-password"
}

variable "gcs_bucket" {
  description = "Bucket do GCS que receberá os arquivos Parquet"
  type        = string
}

variable "gcs_base_path" {
  description = "Prefixo base para salvar arquivos no GCS"
  type        = string
  default     = "data-lake/odoo"
}

variable "api_token" {
  description = "Token usado pelos clientes para chamar a API"
  type        = string
  sensitive   = true
}

variable "enable_apis" {
  description = "APIs que precisam estar habilitadas no projeto"
  type        = list(string)
  default = [
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com"
  ]
}

variable "min_instance_count" {
  description = "Número mínimo de instâncias Cloud Run"
  type        = number
  default     = 0
}

variable "max_instance_count" {
  description = "Número máximo de instâncias Cloud Run"
  type        = number
  default     = 5
}

variable "request_timeout_seconds" {
  description = "Timeout (em segundos) por requisição"
  type        = number
  default     = 300
}

variable "allow_unauthenticated" {
  description = "Define se o serviço será público"
  type        = bool
  default     = true
}

variable "invoker_identity" {
  description = "Principal que poderá invocar o serviço (quando não público)"
  type        = string
  default     = null
}

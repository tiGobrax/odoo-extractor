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

variable "cloud_run_job_name" {
  description = "Nome do Cloud Run Job responsável pelo full extract"
  type        = string
  default     = "odoo-extractor-full"
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

variable "enable_apis" {
  description = "APIs que precisam estar habilitadas no projeto"
  type        = list(string)
  default = [
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudscheduler.googleapis.com"
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

variable "cloud_run_job_task_count" {
  description = "Quantidade de tasks executadas pelo Cloud Run Job"
  type        = number
  default     = 1
}

variable "cloud_run_job_parallelism" {
  description = "Paralelismo máximo por execução do Cloud Run Job"
  type        = number
  default     = 1
}

variable "cloud_run_job_timeout_seconds" {
  description = "Timeout máximo por task do Cloud Run Job"
  type        = number
  default     = 14400
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

variable "enable_full_extract_scheduler" {
  description = "Cria um Cloud Scheduler para executar o job de full extract diariamente"
  type        = bool
  default     = false
}

variable "scheduler_service_account_name" {
  description = "Service account usada pelo Cloud Scheduler para invocar o Cloud Run Job"
  type        = string
  default     = "odoo-extractor-scheduler"
}

variable "cloud_scheduler_job_name" {
  description = "Nome do job no Cloud Scheduler"
  type        = string
  default     = "odoo-extractor-full"
}

variable "cloud_scheduler_cron" {
  description = "Agendamento cron (formato Cloud Scheduler)"
  type        = string
  default     = "0 5 * * *"
}

variable "cloud_scheduler_time_zone" {
  description = "Time zone usado pelo Cloud Scheduler"
  type        = string
  default     = "Etc/UTC"
}

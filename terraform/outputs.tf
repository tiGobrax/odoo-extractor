output "cloud_run_url" {
  description = "URL pública do serviço Cloud Run"
  value       = google_cloud_run_v2_service.odoo.uri
}

output "service_account_email" {
  description = "Email da service account usada pelo Cloud Run"
  value       = google_service_account.odoo.email
}

output "artifact_registry_repository" {
  description = "ID do repositório Artifact Registry"
  value       = google_artifact_registry_repository.odoo.id
}

output "odoo_password_secret" {
  description = "Nome completo do secret criado"
  value       = google_secret_manager_secret.odoo_password.name
}

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "current" {
  project_id = var.project_id
}

locals {
  base_container_env = [
    {
      name  = "ODOO_URL"
      value = var.odoo_url
    },
    {
      name  = "ODOO_DB"
      value = var.odoo_db
    },
    {
      name  = "ODOO_USERNAME"
      value = var.odoo_username
    },
  ]

  service_container_env = concat(
    local.base_container_env,
    [
      {
        name  = "MODE"
        value = "service"
      }
    ],
  )

  job_container_env = concat(
    local.base_container_env,
    [
      {
        name  = "MODE"
        value = "job"
      }
    ],
  )
}

resource "google_project_service" "enabled" {
  for_each = toset(var.enable_apis)

  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "odoo" {
  location      = var.region
  repository_id = var.artifact_registry_repo
  description   = "Imagens do Odoo Extractor"
  format        = "DOCKER"
  labels = {
    environment = var.environment
  }
  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "odoo" {
  account_id   = var.service_account_name
  display_name = "Service Account do Odoo Extractor"
}

resource "google_project_iam_member" "service_account_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.odoo.email}"
}

resource "google_secret_manager_secret" "odoo_password" {
  secret_id = var.odoo_password_secret_name
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "odoo_password" {
  secret      = google_secret_manager_secret.odoo_password.id
  secret_data = var.odoo_password
}

resource "google_secret_manager_secret_iam_member" "odoo_accessor" {
  secret_id = google_secret_manager_secret.odoo_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.odoo.email}"
}

resource "google_cloud_run_v2_service" "odoo" {
  name     = var.cloud_run_service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.odoo.email
    timeout         = "${var.request_timeout_seconds}s"

    scaling {
      min_instance_count = var.min_instance_count
      max_instance_count = var.max_instance_count
    }

    containers {
      image = var.container_image

      ports {
        name           = "http1"
        container_port = var.container_port
      }

      dynamic "env" {
        for_each = local.service_container_env
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      env {
        name = "ODOO_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.odoo_password.secret_id
            version = google_secret_manager_secret_version.odoo_password.version
          }
        }
      }
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  depends_on = [
    google_project_service.enabled,
    google_secret_manager_secret_version.odoo_password
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  name     = google_cloud_run_v2_service.odoo.name
  location = var.region
  role     = "roles/run.invoker"
  member   = var.allow_unauthenticated ? "allUsers" : var.invoker_identity

  lifecycle {
    precondition {
      condition     = var.allow_unauthenticated || var.invoker_identity != null
      error_message = "Set allow_unauthenticated=true or provide invoker_identity"
    }
  }
}

resource "google_cloud_run_v2_job" "odoo_full" {
  name     = var.cloud_run_job_name
  location = var.region

  template {
    parallelism = var.cloud_run_job_parallelism
    task_count  = var.cloud_run_job_task_count

    template {
      service_account = google_service_account.odoo.email
      timeout         = "${var.cloud_run_job_timeout_seconds}s"

      containers {
        image   = var.container_image
        command = ["python", "-m", "app.main"]

        dynamic "env" {
          for_each = local.job_container_env
          content {
            name  = env.value.name
            value = env.value.value
          }
        }

        env {
          name = "ODOO_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.odoo_password.secret_id
              version = google_secret_manager_secret_version.odoo_password.version
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.enabled,
    google_secret_manager_secret_version.odoo_password
  ]
}

resource "google_service_account" "scheduler" {
  count        = var.enable_full_extract_scheduler ? 1 : 0
  account_id   = var.scheduler_service_account_name
  display_name = "Cloud Scheduler - Odoo Extractor Job"
}

resource "google_project_iam_member" "scheduler_run_admin" {
  count   = var.enable_full_extract_scheduler ? 1 : 0
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.scheduler[0].email}"
}

resource "google_service_account_iam_member" "scheduler_token_creator" {
  count              = var.enable_full_extract_scheduler ? 1 : 0
  service_account_id = google_service_account.scheduler[0].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
}

resource "google_cloud_scheduler_job" "odoo_full_daily" {
  count       = var.enable_full_extract_scheduler ? 1 : 0
  name        = var.cloud_scheduler_job_name
  description = "Dispara o Cloud Run Job do Odoo Extractor (full refresh)"
  schedule    = var.cloud_scheduler_cron
  time_zone   = var.cloud_scheduler_time_zone

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.odoo_full.name}:run"
    headers = {
      "Content-Type" = "application/json"
    }
    body = jsonencode({})
    oidc_token {
      service_account_email = google_service_account.scheduler[0].email
      audience              = "https://run.googleapis.com/"
    }
  }

  depends_on = [
    google_project_service.enabled,
    google_cloud_run_v2_job.odoo_full,
    google_project_iam_member.scheduler_run_admin,
    google_service_account_iam_member.scheduler_token_creator,
  ]
}

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

locals {
  container_env = [
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
    {
      name  = "GCS_BUCKET"
      value = var.gcs_bucket
    },
    {
      name  = "GCS_BASE_PATH"
      value = var.gcs_base_path
    },
    {
      name  = "API_TOKEN"
      value = var.api_token
    }
  ]
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
        for_each = local.container_env
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

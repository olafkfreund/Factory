terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

variable "subscription_id" { type = string }
variable "location" { type = string, default = "uksouth" }
variable "image" { type = string, default = "" } # acr/app:tag — empty in phase-1 (infra only)
variable "prefix" { type = string, default = "ttt" }

resource "random_password" "db" {
  length  = 20
  special = false
}
resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}

resource "azurerm_resource_group" "rg" {
  name     = "${var.prefix}-rg"
  location = var.location
}

resource "azurerm_container_registry" "acr" {
  name                = "${var.prefix}acr${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Basic"
  admin_enabled       = true
}

resource "azurerm_postgresql_flexible_server" "pg" {
  name                          = "${var.prefix}-pg-${random_string.suffix.result}"
  resource_group_name           = azurerm_resource_group.rg.name
  location                      = azurerm_resource_group.rg.location
  version                       = "15"
  administrator_login           = "ttt"
  administrator_password        = random_password.db.result
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  zone                          = "1"
  public_network_access_enabled = true
}
resource "azurerm_postgresql_flexible_server_database" "db" {
  name      = "ttt"
  server_id = azurerm_postgresql_flexible_server.pg.id
}
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure" {
  name             = "allow-azure"
  server_id        = azurerm_postgresql_flexible_server.pg.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_redis_cache" "redis" {
  name                 = "${var.prefix}-redis-${random_string.suffix.result}"
  resource_group_name  = azurerm_resource_group.rg.name
  location             = azurerm_resource_group.rg.location
  capacity             = 0
  family               = "C"
  sku_name             = "Basic"
  non_ssl_port_enabled = false
  minimum_tls_version  = "1.2"
}

resource "azurerm_service_plan" "plan" {
  name                = "${var.prefix}-plan"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  os_type             = "Linux"
  sku_name            = "B1"
}

resource "azurerm_linux_web_app" "app" {
  count               = var.image == "" ? 0 : 1
  name                = "${var.prefix}-app-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  service_plan_id     = azurerm_service_plan.plan.id
  site_config {
    application_stack {
      docker_image_name        = var.image
      docker_registry_url      = "https://${azurerm_container_registry.acr.login_server}"
      docker_registry_username = azurerm_container_registry.acr.admin_username
      docker_registry_password = azurerm_container_registry.acr.admin_password
    }
  }
  app_settings = {
    WEBSITES_PORT  = "8080"
    DATABASE_URL   = "postgresql://ttt:${random_password.db.result}@${azurerm_postgresql_flexible_server.pg.fqdn}:5432/ttt?sslmode=require"
    REDIS_HOST     = azurerm_redis_cache.redis.hostname
    REDIS_PORT     = "6380"
    REDIS_SSL      = "true"
    REDIS_PASSWORD = azurerm_redis_cache.redis.primary_access_key
  }
}

output "acr_login_server" { value = azurerm_container_registry.acr.login_server }
output "url" { value = var.image == "" ? "" : "https://${azurerm_linux_web_app.app[0].default_hostname}" }

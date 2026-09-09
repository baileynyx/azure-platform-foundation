# A deliberate Terraform/provider compatibility baseline; upgrades require tests.
terraform {
  required_version = ">= 1.9.0, < 2.0.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# Real deployment uses the operator's Azure CLI session and ARM_SUBSCRIPTION_ID.
# Mock tests replace this provider and do not request Azure credentials.
provider "azurerm" {
  features {}
  resource_provider_registrations = "none"
}

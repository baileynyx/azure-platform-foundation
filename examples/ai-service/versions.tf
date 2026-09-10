# This isolated root reuses the repository's reviewed AzureRM release and lock.
# It has its own local state; running the networking root does not deploy AI.
terraform {
  required_version = ">= 1.9.0, < 2.0.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.81.0"
    }
  }
}

provider "azurerm" {
  subscription_id                 = var.subscription_id
  resource_provider_registrations = "none"
  features {
    cognitive_account {
      # A normal destroy soft-deletes the account instead of purging it. Azure's
      # name retention and recovery behavior still apply after Terraform exits.
      purge_soft_delete_on_destroy = false
    }
  }
}

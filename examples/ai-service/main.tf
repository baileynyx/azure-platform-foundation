locals {
  # The subscription ID is not secret. Its hash is a naming aid, not a claim of
  # guaranteed global uniqueness; change the prefix if Azure reports a collision.
  account_name = "${var.name_prefix}-${substr(sha256(lower(var.subscription_id)), 0, 8)}"
  tags = {
    project     = "terraform-ai-review"
    environment = "portfolio-demo"
    managed_by  = "terraform"
  }
}

resource "azurerm_resource_group" "demo" {
  name     = "rg-${local.account_name}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_cognitive_account" "demo" {
  name                  = local.account_name
  custom_subdomain_name = local.account_name
  resource_group_name   = azurerm_resource_group.demo.name
  location              = azurerm_resource_group.demo.location
  kind                  = "OpenAI"
  sku_name              = "S0"
  tags                  = local.tags

  # The existing reviewer uses API-key authentication. This deliberately enables
  # keys, but does not export them. AzureRM can still store computed keys in state;
  # treat the entire local state and all saved plans as sensitive.
  local_auth_enabled            = true
  public_network_access_enabled = true
  network_acls {
    default_action = "Deny"
    bypass         = "None"
    # A single public endpoint host rule allows the operator's workstation.
    # This does not create a private endpoint or allow GitHub-hosted runners.
    ip_rules = [var.operator_ipv4]
  }
}

resource "azurerm_cognitive_deployment" "reviewer" {
  name                 = "terraform-reviewer"
  cognitive_account_id = azurerm_cognitive_account.demo.id
  # Keep evaluation provenance tied to an explicit version. Review and re-test a
  # replacement before updating this input. At retirement, this deployment may
  # stop serving rather than silently change the model under the experiment.
  version_upgrade_option     = "NoAutoUpgrade"
  dynamic_throttling_enabled = false

  model {
    format  = "OpenAI"
    name    = var.model.name
    version = var.model.version
  }
  sku {
    # Consumption-based global routing avoids provisioned hourly capacity.
    # GlobalStandard does not guarantee inference stays in the account region.
    name     = "GlobalStandard"
    capacity = var.capacity
  }
}

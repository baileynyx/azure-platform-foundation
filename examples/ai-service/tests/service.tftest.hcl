# Provider mocks use the real installed schema while avoiding Azure credentials.
# These assertions prove configuration contracts, not region quota or firewall
# reachability. The synthetic IP and subscription are documentation-only values.
mock_provider "azurerm" {
  mock_resource "azurerm_cognitive_account" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/mock-rg/providers/Microsoft.CognitiveServices/accounts/mock-account"
    }
  }
}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000001"
  operator_ipv4   = "203.0.113.10"
}

run "isolated_account_contract" {
  command = plan
  assert {
    condition     = azurerm_cognitive_account.demo.kind == "OpenAI" && azurerm_cognitive_account.demo.sku_name == "S0"
    error_message = "The demo must provision an OpenAI S0 account."
  }
  assert {
    condition     = azurerm_cognitive_account.demo.resource_group_name == azurerm_resource_group.demo.name
    error_message = "The account must belong to this root's dedicated resource group."
  }
  assert {
    condition     = azurerm_cognitive_account.demo.custom_subdomain_name == local.account_name
    error_message = "The endpoint must use this demo's stable custom subdomain."
  }
}

run "network_and_auth_contract" {
  command = plan
  assert {
    condition = (
      azurerm_cognitive_account.demo.network_acls[0].default_action == "Deny" &&
      azurerm_cognitive_account.demo.network_acls[0].bypass == "None" &&
      azurerm_cognitive_account.demo.network_acls[0].ip_rules == toset([var.operator_ipv4])
    )
    error_message = "The public endpoint must allow exactly the configured host without trusted-service bypass."
  }
  assert {
    condition     = azurerm_cognitive_account.demo.local_auth_enabled && azurerm_cognitive_account.demo.public_network_access_enabled
    error_message = "The first live demo requires API-key auth and a firewall-restricted public endpoint."
  }
}

run "version_and_capacity_contract" {
  command = plan
  assert {
    condition = (
      azurerm_cognitive_deployment.reviewer.model[0].name == "gpt-4.1-mini" &&
      azurerm_cognitive_deployment.reviewer.model[0].version == "2025-04-14" &&
      azurerm_cognitive_deployment.reviewer.version_upgrade_option == "NoAutoUpgrade"
    )
    error_message = "Default model provenance must be explicit and automatic upgrades disabled."
  }
  assert {
    condition = (
      azurerm_cognitive_deployment.reviewer.sku[0].name == "GlobalStandard" &&
      azurerm_cognitive_deployment.reviewer.sku[0].capacity == 10 &&
      !azurerm_cognitive_deployment.reviewer.dynamic_throttling_enabled
    )
    error_message = "Use the small standard deployment with explicit capacity and no dynamic quota expansion."
  }
}

run "nonsecret_reviewer_outputs" {
  command = plan
  assert {
    condition = (
      length(keys(output.reviewer_environment)) == 2 &&
      output.reviewer_environment.AZURE_OPENAI_ENDPOINT == "https://${local.account_name}.openai.azure.com" &&
      output.reviewer_environment.AZURE_OPENAI_DEPLOYMENT == "terraform-reviewer"
    )
    error_message = "Export exactly the reviewer's endpoint and deployment name, without a key."
  }
}

run "configurable_model_and_location" {
  command = plan
  variables {
    name_prefix = "custom-demo"
    location    = "westus"
    capacity    = 5
    model = {
      name    = "gpt-5-mini"
      version = "2025-08-07"
    }
  }
  assert {
    condition = (
      azurerm_resource_group.demo.location == "westus" &&
      azurerm_cognitive_deployment.reviewer.model[0].name == "gpt-5-mini" &&
      azurerm_cognitive_deployment.reviewer.model[0].version == "2025-08-07" &&
      azurerm_cognitive_deployment.reviewer.sku[0].capacity == 5 &&
      startswith(azurerm_cognitive_account.demo.name, "custom-demo-")
    )
    error_message = "Operator configuration must flow through without changing the root's policy."
  }
}

run "reject_broad_network" {
  command = plan
  variables { operator_ipv4 = "0.0.0.0/0" }
  expect_failures = [var.operator_ipv4]
}

run "reject_invalid_ipv4" {
  command = plan
  variables { operator_ipv4 = "999.1.1.1" }
  expect_failures = [var.operator_ipv4]
}

run "reject_bad_subscription" {
  command = plan
  variables { subscription_id = "not-a-subscription" }
  expect_failures = [var.subscription_id]
}

run "reject_oversized_capacity" {
  command = plan
  variables { capacity = 21 }
  expect_failures = [var.capacity]
}

run "reject_fractional_capacity" {
  command = plan
  variables { capacity = 1.5 }
  expect_failures = [var.capacity]
}

run "reject_bad_prefix" {
  command = plan
  variables { name_prefix = "BAD NAME" }
  expect_failures = [var.name_prefix]
}

run "reject_unpinned_model" {
  command = plan
  variables {
    model = {
      name    = "gpt-4.1-mini"
      version = ""
    }
  }
  expect_failures = [var.model]
}

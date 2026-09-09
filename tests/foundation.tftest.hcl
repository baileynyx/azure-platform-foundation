# Plan-only tests use provider schemas without contacting Azure APIs.
mock_provider "azurerm" {}

run "network_contract" {
  command = plan
  assert {
    condition     = output.network_allocations == { hub = "10.42.0.0/20", spoke = "10.42.16.0/20" }
    error_message = "Hub and spoke allocations must match the disjoint subnet design."
  }
  assert {
    condition     = azurerm_resource_group.foundation.tags.owner == "platform-engineering"
    error_message = "The foundation must preserve accountable ownership metadata."
  }
  assert {
    condition     = !azurerm_virtual_network_peering.hub_to_spoke.allow_forwarded_traffic && !azurerm_virtual_network_peering.spoke_to_hub.allow_forwarded_traffic
    error_message = "The lab must not enable forwarded traffic."
  }
}

run "invalid_environment" {
  command = plan
  variables { environment = "prod" }
  expect_failures = [var.environment]
}

run "invalid_owner" {
  command = plan
  variables { owner = "  " }
  expect_failures = [var.owner]
}

run "invalid_cidr" {
  command = plan
  variables { base_cidr = "10.0.0.0/24" }
  expect_failures = [var.base_cidr]
}

# Exercise the child module's actual security contract, not merely its outputs.
run "subnet_security_contract" {
  command = plan
  module {
    source = "./modules/network"
  }
  variables {
    name                = "vnet-test"
    location            = "eastus2"
    resource_group_name = "rg-test"
    address_space       = "10.42.0.0/20"
    subnet_prefix       = "10.42.0.0/24"
    tags                = { owner = "platform-engineering" }
  }
  assert {
    condition     = azurerm_network_security_rule.deny_inbound.direction == "Inbound" && azurerm_network_security_rule.deny_inbound.access == "Deny" && azurerm_network_security_rule.deny_inbound.priority == 4096
    error_message = "The module must override Azure's default inbound allow rules."
  }
  assert {
    condition     = azurerm_network_security_rule.deny_inbound.source_address_prefix == "*" && azurerm_network_security_rule.deny_inbound.destination_address_prefix == "*"
    error_message = "The baseline deny must cover every source and destination."
  }
}

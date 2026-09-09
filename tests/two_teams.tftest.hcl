# Every run replaces Azure with a mock provider and performs a plan only.
# Comparing before/after configured resource values catches regressions without
# making claims about packet flow, deployed state migration or permissions.
mock_provider "azurerm" {}

run "single_team_baseline" {
  command = plan
  variables {
    team_a_owner = "application-team-a"
  }
  assert {
    condition     = output.network_allocations == { hub = "10.42.0.0/20", spoke = "10.42.16.0/20" }
    error_message = "Disabling Team B must preserve the original allocation output."
  }
  assert {
    condition     = length(module.team_b) == 0 && length(azurerm_virtual_network_peering.hub_to_team_b) == 0 && length(azurerm_virtual_network_peering.team_b_to_hub) == 0
    error_message = "The default configuration must not create any Team B module or peering."
  }
  assert {
    condition     = output.network_configuration.spoke.tags.owner == "application-team-a" && output.network_configuration.hub.tags.owner == "platform-engineering"
    error_message = "Assigning Team A must not transfer ownership of the hub."
  }
}

run "onboard_team_b" {
  command = plan
  variables {
    team_a_owner = "application-team-a"
    team_b = {
      owner = "application-team-b"
    }
  }
  assert {
    condition     = output.network_configuration.spoke == run.single_team_baseline.network_configuration.spoke && output.network_configuration.hub == run.single_team_baseline.network_configuration.hub
    error_message = "Adding Team B changed Team A or hub naming, allocation, owner tags or security configuration."
  }
  assert {
    condition     = output.network_allocations.team_b == "10.42.32.0/20" && output.network_configuration.team_b.subnet_prefix == tolist(["10.42.32.0/24"])
    error_message = "The default Team B allocation must occupy the next unused /20 and its first /24."
  }
  assert {
    condition     = output.network_configuration.team_b.tags.owner == "application-team-b" && output.network_configuration.team_b.nsg_tags.owner == "application-team-b" && azurerm_resource_group.foundation.tags.owner == "platform-engineering"
    error_message = "Team B's VNet and NSG must carry its owner while the resource group stays platform-owned."
  }
  assert {
    condition     = output.network_configuration.team_b.inbound_deny == run.single_team_baseline.network_configuration.spoke.inbound_deny
    error_message = "Team B must inherit the same explicit inbound-deny rule as Team A."
  }
  assert {
    condition = alltrue([
      length(azurerm_virtual_network_peering.hub_to_team_b) == 1,
      length(azurerm_virtual_network_peering.team_b_to_hub) == 1,
      !azurerm_virtual_network_peering.hub_to_team_b["team_b"].allow_forwarded_traffic,
      !azurerm_virtual_network_peering.hub_to_team_b["team_b"].allow_gateway_transit,
      !azurerm_virtual_network_peering.hub_to_team_b["team_b"].use_remote_gateways,
      !azurerm_virtual_network_peering.team_b_to_hub["team_b"].allow_forwarded_traffic,
      !azurerm_virtual_network_peering.team_b_to_hub["team_b"].allow_gateway_transit,
      !azurerm_virtual_network_peering.team_b_to_hub["team_b"].use_remote_gateways
    ])
    error_message = "Team B must have both peering directions without forwarding or gateway transit."
  }
}

run "custom_team_b_allocation" {
  command = plan
  variables {
    base_cidr = "10.60.0.0/16"
    team_b = {
      owner            = "application-team-b"
      allocation_index = 15
    }
  }
  assert {
    condition     = output.network_allocations == { hub = "10.60.0.0/20", spoke = "10.60.16.0/20", team_b = "10.60.240.0/20" }
    error_message = "The last valid slot must stay inside the /16 without changing the hub or Team A slots."
  }
}

run "disable_team_b_again" {
  command = plan
  variables {
    team_a_owner = "application-team-a"
    team_b       = null
  }
  assert {
    condition     = output.network_configuration == run.single_team_baseline.network_configuration && length(azurerm_virtual_network_peering.hub_to_team_b) == 0 && length(azurerm_virtual_network_peering.team_b_to_hub) == 0
    error_message = "Disabling the optional spoke must restore the single-team configuration. This is not a live destroy test."
  }
}

run "reject_blank_team_a_owner" {
  command = plan
  variables { team_a_owner = "  " }
  expect_failures = [var.team_a_owner]
}

run "reject_blank_team_b_owner" {
  command = plan
  variables { team_b = { owner = "  " } }
  expect_failures = [var.team_b]
}

run "reject_null_team_b_owner" {
  command = plan
  variables { team_b = { owner = null } }
  expect_failures = [var.team_b]
}

run "reject_hub_allocation" {
  command = plan
  variables { team_b = { owner = "application-team-b", allocation_index = 0 } }
  expect_failures = [var.team_b]
}

run "reject_team_a_allocation" {
  command = plan
  variables { team_b = { owner = "application-team-b", allocation_index = 1 } }
  expect_failures = [var.team_b]
}

run "reject_out_of_range_allocation" {
  command = plan
  variables { team_b = { owner = "application-team-b", allocation_index = 16 } }
  expect_failures = [var.team_b]
}

run "reject_negative_allocation" {
  command = plan
  variables { team_b = { owner = "application-team-b", allocation_index = -1 } }
  expect_failures = [var.team_b]
}

run "reject_fractional_allocation" {
  command = plan
  variables { team_b = { owner = "application-team-b", allocation_index = 2.5 } }
  expect_failures = [var.team_b]
}

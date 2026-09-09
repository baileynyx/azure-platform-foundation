output "resource_group_name" {
  description = "Resource group containing the demonstration."
  value       = azurerm_resource_group.foundation.name
}
output "network_allocations" {
  description = "Disjoint hub and spoke allocations for review."
  # Preserve the existing hub/spoke keys and add team_b only when enabled.
  value = merge({ hub = local.hub_cidr, spoke = local.spoke_cidr }, local.team_b_cidrs)
}
output "subnet_ids" {
  description = "Workload subnets; inbound traffic is denied by default."
  value = merge(
    { hub = module.hub.subnet_id, spoke = module.spoke.subnet_id },
    { for key, network in module.team_b : key => network.subnet_id }
  )
}

output "network_configuration" {
  description = "Reviewable configured network, ownership and inbound security values. This does not certify deployed connectivity or RBAC isolation."
  value = merge(
    { hub = module.hub.configuration, spoke = module.spoke.configuration },
    { for key, network in module.team_b : key => network.configuration }
  )
}

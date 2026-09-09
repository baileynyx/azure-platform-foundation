output "resource_group_name" {
  description = "Resource group containing the demonstration."
  value       = azurerm_resource_group.foundation.name
}
output "network_allocations" {
  description = "Disjoint hub and spoke allocations for review."
  value       = { hub = local.hub_cidr, spoke = local.spoke_cidr }
}
output "subnet_ids" {
  description = "Workload subnets; inbound traffic is denied by default."
  value       = { hub = module.hub.subnet_id, spoke = module.spoke.subnet_id }
}

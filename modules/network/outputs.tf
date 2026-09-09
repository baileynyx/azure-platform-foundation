output "id" {
  description = "VNet ARM identifier used for peering."
  value       = azurerm_virtual_network.this.id
}
output "name" {
  description = "VNet name."
  value       = azurerm_virtual_network.this.name
}
output "subnet_id" {
  description = "NSG-associated workload subnet."
  value       = azurerm_subnet.workload.id
}

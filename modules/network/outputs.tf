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

output "configuration" {
  description = "Configured resource values for change review, including the actual deny rule fields rather than a claimed security status."
  # Use resource attributes so callers and regression tests inspect the values
  # Terraform plans, including future changes to naming, tags or rule fields.
  value = {
    name          = azurerm_virtual_network.this.name
    address_space = azurerm_virtual_network.this.address_space
    subnet_name   = azurerm_subnet.workload.name
    subnet_prefix = azurerm_subnet.workload.address_prefixes
    tags          = azurerm_virtual_network.this.tags
    nsg_name      = azurerm_network_security_group.this.name
    nsg_tags      = azurerm_network_security_group.this.tags
    inbound_deny = {
      name                       = azurerm_network_security_rule.deny_inbound.name
      priority                   = azurerm_network_security_rule.deny_inbound.priority
      direction                  = azurerm_network_security_rule.deny_inbound.direction
      access                     = azurerm_network_security_rule.deny_inbound.access
      protocol                   = azurerm_network_security_rule.deny_inbound.protocol
      source_port_range          = azurerm_network_security_rule.deny_inbound.source_port_range
      destination_port_range     = azurerm_network_security_rule.deny_inbound.destination_port_range
      source_address_prefix      = azurerm_network_security_rule.deny_inbound.source_address_prefix
      destination_address_prefix = azurerm_network_security_rule.deny_inbound.destination_address_prefix
    }
  }
}

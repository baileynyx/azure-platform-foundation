locals {
  # One allocation produces disjoint /20 networks, avoiding caller-supplied overlap.
  hub_cidr   = cidrsubnet(var.base_cidr, 4, 0)
  spoke_cidr = cidrsubnet(var.base_cidr, 4, 1)
  tags = {
    owner       = var.owner
    environment = var.environment
    managed_by  = "terraform"
    purpose     = "portfolio-demonstration"
  }
}

resource "azurerm_resource_group" "foundation" {
  name     = "rg-${var.prefix}-${var.environment}"
  location = var.location
  tags     = local.tags
}

module "hub" {
  source              = "./modules/network"
  name                = "vnet-${var.prefix}-hub"
  location            = var.location
  resource_group_name = azurerm_resource_group.foundation.name
  address_space       = local.hub_cidr
  subnet_prefix       = cidrsubnet(local.hub_cidr, 4, 0)
  tags                = local.tags
}

module "spoke" {
  source              = "./modules/network"
  name                = "vnet-${var.prefix}-spoke"
  location            = var.location
  resource_group_name = azurerm_resource_group.foundation.name
  address_space       = local.spoke_cidr
  subnet_prefix       = cidrsubnet(local.spoke_cidr, 4, 0)
  tags                = local.tags
}

# Both directions are necessary. Peering provides routing, not transit or access
# approval: the subnet NSGs still deny lateral inbound traffic in this lab.
resource "azurerm_virtual_network_peering" "hub_to_spoke" {
  name                      = "hub-to-spoke"
  resource_group_name       = azurerm_resource_group.foundation.name
  virtual_network_name      = module.hub.name
  remote_virtual_network_id = module.spoke.id
  allow_forwarded_traffic   = false
  allow_gateway_transit     = false
  use_remote_gateways       = false
}

resource "azurerm_virtual_network_peering" "spoke_to_hub" {
  name                      = "spoke-to-hub"
  resource_group_name       = azurerm_resource_group.foundation.name
  virtual_network_name      = module.spoke.name
  remote_virtual_network_id = module.hub.id
  allow_forwarded_traffic   = false
  allow_gateway_transit     = false
  use_remote_gateways       = false
}

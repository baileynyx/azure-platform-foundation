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

  # Keep the original owner unless Team A is explicitly assigned to another
  # team. The resource group and hub remain tagged with the platform owner.
  team_a_tags = merge(local.tags, {
    owner = var.team_a_owner == null ? var.owner : var.team_a_owner
  })

  # A fixed key gives the optional module and peerings stable Terraform
  # addresses. Allocation index is configuration, not instance identity.
  team_b_instances = var.team_b == null ? {} : { team_b = var.team_b }
  team_b_cidrs = {
    for key, team in local.team_b_instances : key => cidrsubnet(var.base_cidr, 4, team.allocation_index)
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
  tags                = local.team_a_tags
}

# Preserve module.spoke and its existing peering addresses for Team A. A
# separate optional module avoids turning existing resources into indexed
# instances, which would otherwise need an explicit state-address migration.
module "team_b" {
  for_each            = local.team_b_instances
  source              = "./modules/network"
  name                = "vnet-${var.prefix}-team-b"
  location            = var.location
  resource_group_name = azurerm_resource_group.foundation.name
  address_space       = local.team_b_cidrs[each.key]
  subnet_prefix       = cidrsubnet(local.team_b_cidrs[each.key], 4, 0)
  tags                = merge(local.tags, { owner = each.value.owner })
}

# Platform-managed connectivity follows the same restrictions as Team A. No
# team-to-team peering, gateway transit or application allow rule is created.
resource "azurerm_virtual_network_peering" "hub_to_team_b" {
  for_each                  = local.team_b_instances
  name                      = "hub-to-team-b"
  resource_group_name       = azurerm_resource_group.foundation.name
  virtual_network_name      = module.hub.name
  remote_virtual_network_id = module.team_b[each.key].id
  allow_forwarded_traffic   = false
  allow_gateway_transit     = false
  use_remote_gateways       = false
}

resource "azurerm_virtual_network_peering" "team_b_to_hub" {
  for_each                  = local.team_b_instances
  name                      = "team-b-to-hub"
  resource_group_name       = azurerm_resource_group.foundation.name
  virtual_network_name      = module.team_b[each.key].name
  remote_virtual_network_id = module.hub.id
  allow_forwarded_traffic   = false
  allow_gateway_transit     = false
  use_remote_gateways       = false
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

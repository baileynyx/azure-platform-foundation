variable "name" {
  description = "Network resource name."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "resource_group_name" {
  description = "Existing resource group."
  type        = string
}

variable "address_space" {
  description = "VNet CIDR allocation."
  type        = string
}

variable "subnet_prefix" {
  description = "Workload subnet within the VNet allocation."
  type        = string
}

variable "tags" {
  description = "Ownership and lifecycle metadata."
  type        = map(string)
}


variable "subscription_id" {
  description = "Explicit target Azure subscription UUID, used for provider binding and a stable account-name suffix."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be an Azure subscription UUID."
  }
}

variable "operator_ipv4" {
  description = "Your current public egress IPv4 address, as one host without a CIDR suffix. No broad network rule is accepted."
  type        = string
  nullable    = false
  validation {
    condition = (
      can(regex("^[0-9]{1,3}(\\.[0-9]{1,3}){3}$", var.operator_ipv4)) &&
      can(cidrhost("${var.operator_ipv4}/32", 0)) &&
      !contains(["0.0.0.0", "127.0.0.1", "255.255.255.255"], var.operator_ipv4)
    )
    error_message = "operator_ipv4 must be one valid IPv4 host, not a CIDR range, wildcard or loopback address. Use your public egress address."
  }
}

variable "name_prefix" {
  description = "Lowercase account prefix. A stable subscription-derived suffix reduces global subdomain collisions."
  type        = string
  default     = "bee-tf-review"
  nullable    = false
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}[a-z0-9]$", var.name_prefix))
    error_message = "Use 3-32 lowercase letters, digits or hyphens; start with a letter and end with a letter or digit."
  }
}

variable "location" {
  description = "Azure region for the account. Check current model/SKU availability and subscription quota before applying."
  type        = string
  default     = "eastus2"
  nullable    = false
  validation {
    condition     = can(regex("^[a-z][a-z0-9]+$", var.location))
    error_message = "Use a nonblank Azure region identifier such as eastus2."
  }
}

variable "model" {
  description = "Explicit model/version pair. Both must support Azure chat completions with strict structured outputs."
  type = object({
    name    = string
    version = string
  })
  default = {
    name    = "gpt-4.1-mini"
    version = "2025-04-14"
  }
  nullable = false
  validation {
    condition = (
      can(regex("^[A-Za-z0-9_.-]{1,128}$", var.model.name)) &&
      can(regex("^[A-Za-z0-9_.-]{1,64}$", var.model.version))
    )
    error_message = "Specify a nonblank model name and explicit version using letters, digits, dots, underscores or hyphens."
  }
}

variable "capacity" {
  description = "Deployment quota units, 1-20 for this demo. Units and request limits are model-dependent; this is not a spending cap."
  type        = number
  default     = 10
  nullable    = false
  validation {
    condition     = var.capacity >= 1 && var.capacity <= 20 && var.capacity == floor(var.capacity)
    error_message = "Demo capacity must be a whole number from 1 through 20."
  }
}

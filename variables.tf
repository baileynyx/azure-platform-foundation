variable "prefix" {
  description = "Short lowercase workload identifier used in Azure resource names."
  type        = string
  default     = "portfolio"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,15}$", var.prefix))
    error_message = "prefix must be 3-16 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "location" {
  description = "Azure region for the demonstration."
  type        = string
  default     = "eastus2"
}

variable "owner" {
  description = "Accountable team recorded on taggable resources."
  type        = string
  default     = "platform-engineering"
  validation {
    condition     = length(trimspace(var.owner)) > 0
    error_message = "An accountable owner is required."
  }
}

variable "environment" {
  description = "Controlled environment label; this repository is a lab."
  type        = string
  default     = "lab"
  validation {
    condition     = contains(["lab", "dev", "test"], var.environment)
    error_message = "Use lab, dev or test; production needs a separate reviewed design."
  }
}

variable "base_cidr" {
  description = "IPv4 /16 allocation split into non-overlapping hub and spoke /20 networks."
  type        = string
  default     = "10.42.0.0/16"
  validation {
    condition     = can(cidrnetmask(var.base_cidr)) && endswith(var.base_cidr, "/16")
    error_message = "Supply a valid IPv4 /16 CIDR."
  }
}

variable "team_a_owner" {
  description = "Optional Team A owner tag. Null preserves the existing platform owner tag."
  type        = string
  default     = null
  validation {
    condition     = var.team_a_owner == null ? true : length(trimspace(var.team_a_owner)) > 0
    error_message = "team_a_owner must be null or a nonblank accountable team."
  }
}

variable "team_b" {
  description = "Optional second spoke. Null disables it. Index 0 is the hub and 1 is Team A; use an unused integer slot from 2 to 15."
  type = object({
    owner            = string
    allocation_index = optional(number, 2)
  })
  default = null
  validation {
    condition     = var.team_b == null ? true : try(length(trimspace(var.team_b.owner)) > 0, false)
    error_message = "An enabled Team B spoke requires a nonblank owner."
  }
  validation {
    condition = var.team_b == null ? true : (
      var.team_b.allocation_index >= 2 &&
      var.team_b.allocation_index <= 15 &&
      floor(var.team_b.allocation_index) == var.team_b.allocation_index
    )
    error_message = "Team B allocation_index must be an integer from 2 to 15; 0 and 1 are reserved."
  }
}

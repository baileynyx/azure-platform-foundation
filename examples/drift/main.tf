# This isolated root is copied into a NEW temporary directory by rehearse_drift.py.
# It deliberately has no Azure provider, backend, variables or provisioners.
terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "2.5.3"
    }
  }
}

# A content mismatch is reported by this provider as an absent managed object.
# The rehearsal separately hashes the on-disk bytes to show that the file was
# changed, not deleted, and checks that recovery proposes only this one create.
resource "local_file" "service_config" {
  filename        = "${path.module}/service.conf"
  content         = "environment=synthetic\nlog_level=info\n"
  file_permission = "0600"
}

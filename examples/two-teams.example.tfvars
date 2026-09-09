# Synthetic lab settings. The platform retains ownership of the resource group
# and hub; team tags identify the owners of the spoke VNets and their NSGs.
# Tags are metadata. This example still uses one state and one resource group.
owner        = "platform-engineering"
team_a_owner = "application-team-a"
team_b = {
  owner            = "application-team-b"
  allocation_index = 2
}

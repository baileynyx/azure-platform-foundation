# Non-secret connection details only. Do not add primary/secondary key outputs;
# fetch a key into the current process with the documented Azure CLI procedure.
output "reviewer_environment" {
  description = "Non-secret environment values expected by ai_review.py. API key intentionally excluded."
  value = {
    AZURE_OPENAI_ENDPOINT   = "https://${azurerm_cognitive_account.demo.custom_subdomain_name}.openai.azure.com"
    AZURE_OPENAI_DEPLOYMENT = azurerm_cognitive_deployment.reviewer.name
  }
}

output "resource_group_name" {
  description = "Resource group used when retrieving a key or inspecting the isolated demo."
  value       = azurerm_resource_group.demo.name
}

output "account_name" {
  description = "Azure OpenAI account used by the key retrieval command."
  value       = azurerm_cognitive_account.demo.name
}

output "model_configuration" {
  description = "Configured model provenance. The live response model identifier must still be recorded by the reviewer."
  value = {
    name    = azurerm_cognitive_deployment.reviewer.model[0].name
    version = azurerm_cognitive_deployment.reviewer.model[0].version
    sku     = azurerm_cognitive_deployment.reviewer.sku[0].name
  }
}

# mlops-workshop-ai

**Bundle 2 of 3** in the MLOps Workshop monorepo (`mlOpsWorkshop2026`).

Deploys the **Model Serving endpoint** with AI Gateway inference table logging. Requires the `-infra` bundle to be deployed first with at least one registered model version.

---

## What This Bundle Deploys

| Resource | Key | Description |
|----------|-----|-------------|
| Model Serving endpoint | `churn_serving` | Serves the churn prediction model with Feature Store auto-lookup from Lakebase Online Store. Scale-to-zero enabled. |
| AI Gateway inference table | (auto-created) | Logs all serving requests to `${catalog}.${schema}.churn_serving_v2_payload` for monitoring by `-monitors` bundle. |

## Cross-Bundle Dependencies

| Dependency | Source | Variable |
|------------|--------|----------|
| UC Catalog | `-infra` `var.catalog` | `${var.catalog}` |
| UC Schema (with dev-mode prefix) | `-infra` `workshop_schema` resource | `${var.user_schema}` |
| Registered model (3-level name) | `-infra` `churn_model` resource | `${var.registered_model_name}` |
| Online Feature Store | Manual setup (Lakebase) | `mlops-workshop-churn-features` online store with 2 published tables |

## Prerequisites

1. `-infra` bundle deployed (`bundle deploy --target dev`)
2. At least one model version registered in `churn_model`
3. **Online Feature Store** provisioned and feature tables published:
   - Online store: `mlops-workshop-churn-features` (Lakebase, CU_1)
   - `churn_windowed_features_online` — synced from windowed feature table
   - `churn_profile_features_online` — synced from profile feature table
   - CDF enabled on both source tables

## Deploy

```bash
# Validate first
databricks bundle validate --strict --target dev

# Deploy
databricks bundle deploy --target dev
```

Or use the **deployment rocket** in the left sidebar.

## Variables

| Variable | Dev | Prod |
|----------|-----|------|
| `catalog` | `hls_fde_dev` | `mlops_workshop` |
| `user_schema` | `dev_<user>_mlops_workshop` | `mlops_prod` |
| `registered_model_name` | `hls_fde_dev.dev_<user>_mlops_workshop.dev_<user>_churn_model` | `mlops_workshop.mlops_prod.churn_model` |

## Version Lifecycle

The serving endpoint is initially deployed with `entity_version: "1"`. The `churn_deployment_job` in `-infra` updates the served version via SDK `update_config()` when a new Champion is promoted. Re-deploying this bundle resets the version to `"1"` (known DABs limitation; acceptable for workshop).

## Documentation

- [Declarative Automation Bundles in the workspace](https://docs.databricks.com/aws/en/dev-tools/bundles/workspace-bundles)
- [Declarative Automation Bundles Configuration reference](https://docs.databricks.com/aws/en/dev-tools/bundles/reference)
- [Databricks Online Feature Stores](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-feature-store/)

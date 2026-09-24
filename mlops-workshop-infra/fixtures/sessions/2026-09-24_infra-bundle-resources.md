# Session: Infra Bundle Resource YAML

**Date:** 2026-09-24
**Branch:** `mg-genie-infra-bundle-resources`
**Bundle:** `mlops-workshop-infra`

---

## Problem

The `-infra` bundle had boilerplate `databricks.yml` (targets + includes only) with no variables, no `resources/` directory, and no resource YAML. The L300 implementation spec defined 8 resources (schema, volume, experiment, registered model, 4 jobs) that needed to be authored.

## Root Cause

Greenfield — design docs were complete but implementation had not started.

## Changes Made

### 1. Wired `databricks.yml` variables

**File:** `mlops-workshop-infra/databricks.yml`

* Added 3 variables: `catalog`, `user_schema`, `use_zerobus`
* Added per-target variable overrides:
  * dev: `user_schema: "user_${bundle.user_name}"`, `use_zerobus: "false"`
  * prod: `user_schema: mlops_prod`, `use_zerobus: "true"`
* Removed boilerplate comments

### 2. Created 7 resource YAML files

**Directory:** `mlops-workshop-infra/resources/`

| File | Resources | Notes |
|------|-----------|-------|
| `schema.yml` | `workshop_schema` + `landing_volume` | Volume refs derive from schema resource |
| `experiment.yml` | `churn_experiment` | User-scoped MLflow experiment path |
| `registered_model.yml` | `churn_model` | Schema-derived catalog/schema refs |
| `data_ingestion_job.yml` | `data_ingestion` (7 tasks) | Condition gate on `use_zerobus`; `AT_LEAST_ONE_SUCCESS` convergence at flatten_to_silver |
| `training_job.yml` | `churn_model_training` (6 tasks) | Runtime `{{tasks.*.values.*}}` refs; dual condition gates (validation + promotion) |
| `deployment_job.yml` | `churn_deployment_job` (3 tasks) | `MODEL_VERSION_READY` trigger; evaluate → approve gate → promote_champion |
| `batch_inference_job.yml` | `churn_batch_inference` (1 task) | Standalone `@Champion` alias loader |

## Decisions

* **Schema + volume in one file** — `schema.yml` holds both since they're the foundational UC resources and volume derives from schema refs.
* **Deploy-time condition gate** — `${var.use_zerobus}` resolves at deploy time; the condition task still shows which path was taken in the job run UI.
* **3-level model_name parameter** — All notebooks receive the fully-qualified UC model name (`catalog.schema.model`) via `base_parameters`, constructed from resource references.
* **`.ipynb` notebook paths** — Per project convention (not `.py`), even though design docs listed `.py`.
* **Job naming convention** — `[${bundle.target}] mlops-workshop-<purpose>` for easy target identification.

## Files Modified

* `mlops-workshop-infra/databricks.yml` (modified)
* `mlops-workshop-infra/resources/schema.yml` (new)
* `mlops-workshop-infra/resources/experiment.yml` (new)
* `mlops-workshop-infra/resources/registered_model.yml` (new)
* `mlops-workshop-infra/resources/data_ingestion_job.yml` (new)
* `mlops-workshop-infra/resources/training_job.yml` (new)
* `mlops-workshop-infra/resources/deployment_job.yml` (new)
* `mlops-workshop-infra/resources/batch_inference_job.yml` (new)

## Next Steps

* Create `src/` directory tree and 13 notebook stubs per L300 contracts
* Author `-ai` and `-monitors` bundle resources
* `databricks bundle validate -t dev` on the infra bundle
* Clean up stray empty files at `~/mlops-workshop-infra/resources/` (outside repo)

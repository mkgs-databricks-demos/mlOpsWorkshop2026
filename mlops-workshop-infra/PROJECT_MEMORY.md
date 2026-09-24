# PROJECT_MEMORY.md — mlops-workshop-infra

**Bundle:** `mlops-workshop-infra` (Bundle 1 of 3)  
**Monorepo:** `mlOpsWorkshop2026`  
**Purpose:** Deploy foundational UC resources and all ML lifecycle jobs for the MLOps Workshop

---

## Bundle Identity

| Key | Value |
|-----|-------|
| Bundle name | `mlops-workshop-infra` |
| Bundle root | `mlOpsWorkshop2026/mlops-workshop-infra/` |
| Default target | `dev` (mode: development) |
| Workspace | `https://fevm-hls-fde.cloud.databricks.com` |
| Monorepo PROJECT_MEMORY | `../PROJECT_MEMORY.md` |

---

## Variables

| Variable | Default | Dev Override | Prod Override |
|----------|---------|-------------|---------------|
| `catalog` | `hls_fde_dev` | `hls_fde_dev` | `mlops_workshop` |
| `user_schema` | `mlops_workshop` | `mlops_workshop` | `mlops_prod` |
| `use_zerobus` | `"false"` | *(default)* | `"true"` |

---

## Resources (8 total)

| Resource | Type | Key | File |
|----------|------|-----|------|
| Workshop schema | `schemas` | `workshop_schema` | `resources/schema.yml` |
| Landing volume | `volumes` | `landing_volume` | `resources/schema.yml` |
| MLflow experiment | `experiments` | `churn_experiment` | `resources/experiment.yml` |
| Registered model | `registered_models` | `churn_model` | `resources/registered_model.yml` |
| Data ingestion job | `jobs` | `data_ingestion` | `resources/data_ingestion_job.yml` |
| Training + promotion job | `jobs` | `churn_model_training` | `resources/training_job.yml` |
| MLflow 3 deployment job | `jobs` | `churn_deployment_job` | `resources/deployment_job.yml` |
| Batch inference job | `jobs` | `churn_batch_inference` | `resources/batch_inference_job.yml` |

---

## Notebooks (13 total)

| Notebook | Path | Job | Parameters | Task Values |
|----------|------|-----|-----------|-------------|
| create_bronze_tables | `src/data/create_bronze_tables.ipynb` | data_ingestion | catalog, schema | — |
| generate_ndjson | `src/data/generate_ndjson.ipynb` | data_ingestion | catalog, schema | ndjson_path, record_count |
| post_to_zerobus | `src/data/post_to_zerobus.ipynb` | data_ingestion | catalog, schema | — |
| write_to_volume | `src/data/write_to_volume.ipynb` | data_ingestion | volume_path | — |
| autoload_to_bronze | `src/data/autoload_to_bronze.ipynb` | data_ingestion | catalog, schema, volume_path | — |
| flatten_to_silver | `src/data/flatten_to_silver.ipynb` | data_ingestion | catalog, schema | — |
| feature_definitions | `src/train/feature_definitions.ipynb` | churn_model_training* | catalog, schema | — |
| train | `src/train/train.ipynb` | churn_model_training | experiment_name, model_name, catalog, schema | model_version |
| validate | `src/validate/validate.ipynb` | churn_model_training | model_name, model_version | validation_passed |
| promote | `src/promote/promote.ipynb` | churn_model_training | model_name | promoted |
| evaluate | `src/deploy/evaluate.ipynb` | churn_deployment_job | model_name | should_deploy |
| promote_champion | `src/deploy/promote_champion.ipynb` | churn_deployment_job | model_name | — |
| batch_predict | `src/inference/batch_predict.ipynb` | churn_batch_inference | model_name, catalog, schema | — |

\* `feature_definitions` task not yet in YAML — pending addition to `training_job.yml`

---

## Conventions

* **Notebook paths:** `.ipynb` default (per workspace conventions)
* **Schema refs:** `${resources.schemas.workshop_schema.*}` in all resource definitions — never raw `${var.schema}`
* **Model name pattern:** `${catalog}.${schema}.churn_model` (3-level UC name)
* **Task values:** All string — condition tasks compare string equality
* **First cell:** `%pip install --upgrade databricks-sdk mlflow` + `dbutils.library.restartPython()` (not `%restart_python`)
* **Idempotent DDL:** CREATE IF NOT EXISTS / CREATE OR REPLACE throughout
* **VARIANT-first bronze:** `parse_json()` + VARIANT path notation, never `spark.read.json()` with schema inference

---

## Key Technical Decisions

* **All serverless compute** — no cluster definitions in job YAML, no ML Runtime
* **Dual-path ingestion** — `use_zerobus` variable gates ZeroBus API vs Auto Loader; silver reads from `bronze_unified` (UNION ALL)
* **Champion/Challenger aliases** — Champion, Challenger, PreviousChampion. Promotion: F1 > 0.75, AUC within 0.005. First model auto-promotes.
* **Feature Views (declarative)** — `databricks-feature-engineering>=0.16.0`. Eliminates training-serving skew via `fe.score_batch()`.
* **Shared dev schema** — `mlops_workshop` in dev; per-participant override possible via `user_schema` variable
* **Two promotion paths** — training job has a fast-path promote, deployment job has a governed event-driven promote on MODEL_VERSION_READY

---

## Silver Tables

| Table | Key | Grain | Source record_type |
|-------|-----|-------|--------------------|
| `customer_profiles` | customer_id | per customer | `customer_profile` |
| `product_usage_events` | customer_id + event_date | per customer per day | `usage_event` |
| `billing_history` | customer_id + billing_date | per billing event | `billing` |
| `support_interactions` | customer_id + ticket_id | per ticket | `support_interaction` |
| `churn_labels` | customer_id + observation_date | per observation | `churn_label` |

---

## Feature Views

| Feature | Source | Aggregation | Window |
|---------|--------|-------------|--------|
| `avg_daily_sessions_30d` | `product_usage_events` | Avg(session_count) | Tumbling 30d |
| `support_tickets_7d` | `support_interactions` | Count(ticket_id) | Sliding 7d/1d |
| `total_revenue_90d` | `billing_history` | Sum(amount) | Tumbling 90d |
| `max_api_calls_7d` | `product_usage_events` | Max(api_calls) | Sliding 7d/1d |
| `overdue_payment_count` | `billing_history` | Count(*) where overdue | Tumbling 90d |
| `escalated_tickets_30d` | `support_interactions` | Count(*) where escalated | Tumbling 30d |

---

## Implementation Status

| Component | Status |
|-----------|--------|
| `databricks.yml` | Complete (defaults: `hls_fde_dev` / `mlops_workshop`) |
| Resource YAML (8 resources) | Complete (paths fixed, register_features task added, trigger commented) |
| `src/` notebooks (13) | Scaffolded — valid .ipynb stubs, implementation pending |
| `tests/` | Not started |
| Bundle validation | Passing (`--strict`, target dev) |

### Known Issues

1. ~~`${bundle.user_name}`~~ — **RESOLVED.** Variable defaults updated; schema.yml comment fixed.
2. ~~`model_update` trigger~~ — **RESOLVED.** Commented out with TODO note in deployment_job.yml.
3. ~~Notebook path resolution~~ — **RESOLVED.** Changed `./src/` to `../src/` in all job YAML.
4. ~~Notebooks not found~~ — **RESOLVED.** Created as `.ipynb` files (Git folder requires file-based notebooks, not native workspace notebooks).

---

## Dependencies

| Depends On | Provided By |
|------------|-------------|
| Customer catalog (USE CATALOG + CREATE SCHEMA) | Customer admin |
| ZeroBus endpoint (optional) | Secret scope `mlops-workshop` |
| Downstream: `-ai` bundle | Requires >=1 model version registered |
| Downstream: `-monitors` bundle | Requires batch inference to have run |

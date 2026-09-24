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
| `user_schema` | `mlops_workshop` | `dev_matthew_giglia_mlops_workshop` (dev mode prefixes schema name) | `mlops_prod` |
| `use_zerobus` | `"false"` | *(default)* | `"true"` |

---

## Resources (9 total)

| Resource | Type | Key | File |
|----------|------|-----|------|
| Workshop schema | `schemas` | `workshop_schema` | `resources/schema.yml` |
| Landing volume | `volumes` | `landing_volume` | `resources/schema.yml` |
| MLflow experiment | `experiments` | `churn_experiment` | `resources/experiment.yml` |
| Registered model | `registered_models` | `churn_model` | `resources/registered_model.yml` |
| Data ingestion pipeline | `pipelines` | `data_ingestion_pipeline` | `resources/data_ingestion_pipeline.yml` |
| Data prep job | `jobs` | `data_ingestion` | `resources/data_ingestion_job.yml` |
| Training + promotion job | `jobs` | `churn_model_training` | `resources/training_job.yml` |
| MLflow 3 deployment job | `jobs` | `churn_deployment_job` | `resources/deployment_job.yml` |
| Batch inference job | `jobs` | `churn_batch_inference` | `resources/batch_inference_job.yml` |

---

## Pipeline Source Files

| File | Purpose |
|------|----------|
| `src/pipeline/ingestion/bronze.py` | `bronze_autoload` (Auto Loader streaming table), `bronze_zerobus` (placeholder), `bronze_unified` (temp view) |
| `src/pipeline/ingestion/silver.py` | 5 materialized views: `customer_profiles`, `product_usage_events`, `billing_history`, `support_interactions`, `churn_labels` |

## Notebooks

### Implemented

| Notebook | Path | Job | Parameters | Task Values | Status |
|----------|------|-----|-----------|-------------|--------|
| generate_ndjson | `src/data/generate_ndjson.py` | data_ingestion | catalog, schema, volume_path | ndjson_path, record_count | **Complete** |
| post_to_zerobus | `src/data/post_to_zerobus.py` | data_ingestion | catalog, schema | — | Placeholder |
| write_to_volume | `src/data/write_to_volume.py` | (standalone only) | volume_path | — | **Complete** (not in job) |
| feature_definitions | `src/train/feature_definitions.py` | churn_model_training* | catalog, schema | — | **Complete** — 6 Feature Views |
| feature_tables_classic | `src/train/feature_tables_classic` | (standalone) | catalog, schema | — | **Complete** — classic comparison |

### Stubs (implementation pending)

| Notebook | Path | Job | Parameters | Task Values |
|----------|------|-----|-----------|-------------|
| train | `src/train/train.py` | churn_model_training | experiment_name, model_name, catalog, schema | model_version |
| validate | `src/validate/validate.py` | churn_model_training | model_name, model_version | validation_passed |
| promote | `src/promote/promote.py` | churn_model_training | model_name | promoted |
| evaluate | `src/deploy/evaluate.py` | churn_deployment_job | model_name | should_deploy |
| promote_champion | `src/deploy/promote_champion.py` | churn_deployment_job | model_name | — |
| batch_predict | `src/inference/batch_predict.py` | churn_batch_inference | model_name, catalog, schema | — |

\* `feature_definitions` task not yet in YAML — pending addition to `training_job.yml`

### UC Feature Objects

| Object | Type | Source |
|--------|------|--------|
| `avg_daily_sessions_30d` | Feature (View) | `product_usage_events_fv` |
| `max_api_calls_7d` | Feature (View) | `product_usage_events_fv` |
| `total_revenue_90d` | Feature (View) | `billing_history_fv` |
| `overdue_payment_count_90d` | Feature (View) | `billing_history_overdue_fv` |
| `support_tickets_7d` | Feature (View) | `support_interactions` |
| `escalated_tickets_30d` | Feature (View) | `support_interactions` |
| `churn_windowed_features` | Feature Table | Classic — 6 windowed features, PK: customer_id + observation_date |
| `churn_profile_features` | Feature Table | Classic — 3 static features, PK: customer_id |

Helper views (DATE→TIMESTAMP cast): `product_usage_events_fv`, `billing_history_fv`, `billing_history_overdue_fv`

### Obsolete (to delete)

| File | Replaced By |
|------|-------------|
| `src/data/create_bronze_tables.py` | SDP pipeline (`bronze.py`) |
| `src/data/autoload_to_bronze.py` | SDP pipeline (`bronze.py`) |
| `src/data/flatten_to_silver.py` | SDP pipeline (`silver.py`) |

---

## Conventions

* **Notebook paths:** `.py` files on disk (Git folder convention — YAML must match actual extension)
* **Schema refs:** `${resources.schemas.workshop_schema.*}` in all resource definitions — never raw `${var.schema}`
* **Model name pattern:** `${catalog}.${schema}.churn_model` (3-level UC name)
* **Task values:** All string — condition tasks compare string equality
* **First cell:** `%pip install --upgrade databricks-sdk mlflow` + `dbutils.library.restartPython()` (not `%restart_python`)
* **Idempotent DDL:** CREATE IF NOT EXISTS / CREATE OR REPLACE throughout
* **VARIANT-first bronze:** `parse_json()` + VARIANT path notation, never `spark.read.json()` with schema inference
* **SDP pipeline:** `from pyspark import pipelines as dp` — never `import dlt`
* **Serverless I/O:** Use `os`/`shutil` for local filesystem; `dbutils.fs` only for cloud/UC paths. Never `dbutils.fs.rm("file:...")` or `dbutils.fs.ls("file:...")` on serverless.

---

## Key Technical Decisions

* **All serverless compute** — no cluster definitions in job YAML, no ML Runtime
* **SDP pipeline for ingestion** — streaming tables (bronze) + materialized views (silver); replaces 3 notebook tasks. Pipeline YAML uses `glob: include: ../src/pipeline/ingestion/**`.
* **Direct-to-volume data generation** — `generate_ndjson` writes NDJSON partitioned by `record_type/` directly to the landing volume. Avoids `/tmp/` cross-task sharing on serverless.
* **Dual-path ingestion** — `use_zerobus` variable gates ZeroBus API vs Auto Loader; `bronze_unified` (temporary view, UNION ALL) feeds silver. Downstream is path-agnostic.
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

Validated by EDA (see `docs/design/feature-engineering-design.md` for full statistical justification).

| Feature | Source | Aggregation | Window | EDA Signal |
|---------|--------|-------------|--------|------------|
| `avg_daily_sessions_30d` | `product_usage_events` | Avg(session_count) | Tumbling 30d | 3.3x active/churned ratio |
| `support_tickets_7d` | `support_interactions` | Count(ticket_id) | Sliding 7d/1d | 2.4x ratio, |r|=0.665 |
| `total_revenue_90d` | `billing_history` | Sum(amount) | Tumbling 90d | 4.9x revenue gap |
| `max_api_calls_7d` | `product_usage_events` | Max(api_calls) | Sliding 7d/1d | |r|=0.766 |
| `overdue_payment_count_90d` | `billing_history` | Count(*) where overdue | Tumbling 90d | 3.8x overdue rate |
| `escalated_tickets_30d` | `support_interactions` | Count(*) where escalated | Tumbling 30d | 9.0x count ratio |

### Static Features

| Feature | Source | Encoding | EDA Signal |
|---------|--------|----------|------------|
| `plan_type` | `customer_profiles` | Ordinal (free=0..enterprise=3) | 37% → 2.5% churn, monotonic |
| `company_size` | `customer_profiles` | Ordinal (1-10=0..1000+=4) | Moderate signal |
| `tenure_days` | `customer_profiles` | datediff(current_date, signup_date) | Weak control variable |

### Excluded Features (EDA-justified)

`region` (no signal), `avg_feature_depth` (no signal), `max_sessions`/`max_api_calls` (collinear), `avg_invoice` (collinear with plan+revenue), `invoice_count` (r=1.0 with tenure), `overdue_count`/`pending_count` (use rate instead), `escalated_count`/`pending_tickets` (use rate+count instead)

---

## Implementation Status

| Component | Status |
|-----------|--------|
| `databricks.yml` | Complete |
| Resource YAML (9 resources) | Complete (pipeline + 4 jobs + schema/volume/experiment/model) |
| SDP pipeline (`src/pipeline/ingestion/`) | **Complete** — bronze + silver, verified with data |
| Data generation (`generate_ndjson.py`) | **Complete** — 500 customers, ~22K total records |
| Data prep job (end-to-end) | **Complete** — `bundle run` succeeds, silver tables populated |
| EDA notebook (`fixtures/eda_churn_exploration`) | **Complete** — 30 cells, correlation matrix, VIF, distributions, box plots |
| Feature engineering design (`docs/design/feature-engineering-design.md`) | **Complete** — 6 Feature Views + 3 static features specified |
| Feature definitions (`src/train/feature_definitions.py`) | **Complete** — 6 Feature Views registered to UC, 3 helper views (DATE→TIMESTAMP) |
| Training notebooks (`src/train/train.py`) | Stub |
| Validation notebooks (`src/validate/`) | Stub |
| Promotion notebooks (`src/promote/`) | Stub |
| Deployment notebooks (`src/deploy/`) | Stub |
| Inference notebooks (`src/inference/`) | Stub |
| `tests/` | Not started |
| Bundle validation | Passing (`--strict`, target dev) |
| Bundle deployment | Deployed (source-linked, 9 resources) |

### Known Issues

1. ~~`${bundle.user_name}`~~ — **RESOLVED.** Variable defaults updated; schema.yml comment fixed.
2. ~~`model_update` trigger~~ — **RESOLVED.** Commented out with TODO note in deployment_job.yml.
3. ~~Notebook path resolution~~ — **RESOLVED.** Changed `./src/` to `../src/` in all job YAML.
4. ~~Notebooks not found~~ — **RESOLVED.** Created as `.py` files (Git folder convention).
5. ~~`.ipynb` vs `.py` mismatch~~ — **RESOLVED.** All 4 job YAMLs fixed to `.py` (14 refs).
6. ~~Serverless `/tmp/` restrictions~~ — **RESOLVED.** Three fixes: `shutil` for local I/O, direct volume writes, subdirectory-only cleanup.
7. **3 obsolete stubs remain on disk** — `create_bronze_tables.py`, `autoload_to_bronze.py`, `flatten_to_silver.py`. Not referenced; safe to delete.

---

## Gotchas

* **Git folder notebook creation:** `createAsset` with `assetType: "notebook"` creates native workspace notebooks (type `NOTEBOOK`) that `bundle validate` cannot find. In Git folders, the CLI resolves paths against the workspace file API which only sees `FILE` objects. Fix: use `createAsset` with `assetType: "file"` and name ending in `.py`, then populate with valid Python content.
* **Serverless `/tmp/`:** Local `/tmp/` is ephemeral per task — not shared between job tasks. Use UC volumes for inter-task data transfer.
* **`dbutils.fs` on serverless:** Cannot access `file:/tmp/...` or `file:/local/...`. Use Python `os`/`shutil` for local filesystem operations.
* **Volume root is immutable:** `shutil.rmtree("/Volumes/.../volume_name")` fails with `OSError: Operation not supported`. Clean subdirectories individually instead.
* **Feature Views DATE columns:** `timeseries_column` must be TIMESTAMP, not DATE — the API internally calls `unix_micros()` which rejects DATE. Fix: create helper views that CAST(date_col AS TIMESTAMP). The `transformation_sql` parameter on `DeltaTableSource` has an internal backtick-quoting bug (PARSE_SYNTAX_ERROR); use views instead.
* **Feature Views Count input:** `Count(input=col)` cannot reference the `timeseries_column` — the API renames it internally. Use any other non-null column (e.g. `amount` instead of `billing_date`).

---

## Dependencies

| Depends On | Provided By |
|------------|-------------|
| Customer catalog (USE CATALOG + CREATE SCHEMA) | Customer admin |
| ZeroBus endpoint (optional) | Secret scope `mlops-workshop` |
| Downstream: `-ai` bundle | Requires >=1 model version registered |
| Downstream: `-monitors` bundle | Requires batch inference to have run |

# Implementation Plan — `mlops-workshop-infra` Bundle

**Status:** Draft — for review  
**Bundle:** `mlops-workshop-infra` (Bundle 1 of 3)  
**Spec references:** L200-01-infra-bundle.md, L300-implementation-specs.md  
**Monorepo PROJECT_MEMORY:** `../../PROJECT_MEMORY.md`

---

## Current State

### What Exists

| Asset | Status | Notes |
|-------|--------|-------|
| `databricks.yml` | Authored | Variables, includes, dev/prod targets |
| `resources/schema.yml` | Authored | workshop_schema + landing_volume |
| `resources/registered_model.yml` | Authored | churn_model |
| `resources/experiment.yml` | Authored | churn_experiment |
| `resources/data_ingestion_job.yml` | Authored | Data generation + pipeline trigger |
| `resources/data_ingestion_pipeline.yml` | **Planned** | SDP pipeline: bronze → silver |
| `resources/training_job.yml` | Authored | 6-task training + promotion |
| `resources/deployment_job.yml` | Authored | 3-task MLflow 3 deployment |
| `resources/batch_inference_job.yml` | Authored | 1-task standalone inference |
| `src/` directory | Scaffolded | 10 .py notebook stubs + 2 SDP pipeline source files, implementation pending |
| `tests/` directory | **Missing** | No unit or integration tests |

### Validation Errors (Blocking)

1. **`${bundle.user_name}` is not a valid substitution**
   - Locations: `databricks.yml` line 28, `resources/schema.yml` line 7
   - Fix: Variable defaults updated to `hls_fde_dev` / `mlops_workshop`; schema.yml comment fixed to `${workspace.current_user.short_name}`
   - Status: **RESOLVED**

2. **`model_update` trigger is an unknown field**
   - Location: `resources/deployment_job.yml` line 13
   - The MLflow 3 model-triggered job may require a newer CLI version or different field path
   - Impact: Warning only — bundle deploys but trigger may not function
   - Fallback: Remove trigger, run deployment job manually or on schedule

---

## Phase 1: Validation Fixes — COMPLETE

**Goal:** Clean `bundle validate --strict` pass. **STATUS: ACHIEVED.**

### 1.1 Fix `${bundle.user_name}` References

| File | Line | Current | Fix |
|------|------|---------|-----|
| `databricks.yml` | 9, 12 | defaults `mlops_workshop` | defaults `hls_fde_dev` / `mlops_workshop` (done) |
| `databricks.yml` | 28–29 | `user_${bundle.user_name}` | `hls_fde_dev` / `mlops_workshop` (done) |
| `resources/schema.yml` | 7 | `${bundle.user_name}` | `${workspace.current_user.short_name}` (done) |

### 1.2 Resolve `model_update` Trigger

**Option A (recommended):** Keep the trigger, verify CLI support with `databricks bundle schema`. If the installed CLI supports it, no change needed.  
**Option B:** Remove the trigger block, add a comment noting it requires manual invocation or schedule.  
**Option C:** Replace with a schedule-based trigger as a temporary workaround.

### 1.3 Acceptance Criteria

```bash
databricks bundle validate --strict --target dev
# Exit 0, no errors, no warnings
```

---

## Phase 2: Directory Structure — COMPLETE

Created the `src/` tree matching job YAML notebook paths:

> **Note:** All notebooks are `.py` format (Python source with `# Databricks notebook source` header). Job YAML `notebook_path` values use `.py` extension to match.

```
src/
├── data/                          # Notebook tasks (data generation)
│   ├── generate_ndjson.py
│   ├── post_to_zerobus.py
│   └── write_to_volume.py
├── pipeline/                      # SDP source files (multi-file editor)
│   └── ingestion/
│       ├── bronze.py              #   Auto Loader → bronze streaming tables + unified view
│       └── silver.py              #   bronze → 5 silver materialized views
├── train/
│   ├── feature_definitions.py
│   └── train.py
├── validate/
│   └── validate.py
├── promote/
│   └── promote.py
├── deploy/
│   ├── evaluate.py
│   └── promote_champion.py
└── inference/
    └── batch_predict.py
```

**Changes from original scaffold:**
- **Removed** `create_bronze_tables.py`, `autoload_to_bronze.py`, `flatten_to_silver.py` — replaced by SDP pipeline source files
- **Added** `pipeline/ingestion/bronze.py` and `silver.py` — plain `.py` files with `from pyspark import pipelines as dp` decorators (not notebooks)

**Decision required:** `feature_definitions.py` is documented in the monorepo PROJECT_MEMORY but not referenced by any current job task. Recommended resolution:

- **(a) Add a `register_features` task to `training_job.yml` before `model_training`** — features depend on silver tables (created by ingestion) and must exist before training. Keeping them in the training job makes the dependency explicit.
- (b) Add to `data_ingestion_job.yml` after pipeline completes — couples feature registration to data freshness.
- (c) Import feature definitions from within `train.py` — simplest, but hides a dependency.

---

## Phase 3: Data Generation & Ingestion

Phase 3 is split into two parts:
- **3A** — Data generation notebooks (job tasks that produce synthetic data and stage it to the landing volume)
- **3B** — SDP ingestion pipeline (multi-file editor; declaratively manages bronze → silver lifecycle)

### 3A: Data Generation Notebooks

These remain as notebook tasks in `data_ingestion_job.yml`. Conventions:
- First cell: `%pip install` + `dbutils.library.restartPython()`
- Second cell: `dbutils.widgets.get()` for parameters
- Task values via `dbutils.jobs.taskValues.set()`

#### 3A.1 generate_ndjson.py

| | |
|---|---|
| **Path** | `src/data/generate_ndjson.py` |
| **Parameters** | `catalog`, `schema` |
| **Task Values** | `ndjson_path` (str), `record_count` (int) |
| **Logic** | Generate synthetic data for ~500 customers. 5 record types with realistic distributions. ~60 records per customer ≈ 30K total. Write as NDJSON to a temp path. Set task values for downstream. |
| **Spec** | L200-01 §4, L300 §4.3 |

**Record types and fields** (from L300 §4.3 silver schemas):

| record_type | Fields |
|---|---|
| `customer_profile` | customer_id, signup_date, plan_type, region, company_size |
| `usage_event` | customer_id, event_date, session_count, feature_usage, api_calls |
| `billing` | customer_id, billing_date, amount, payment_status |
| `support_interaction` | customer_id, ticket_id, created_at, category, resolution |
| `churn_label` | customer_id, observation_date, churned |

#### 3A.2 write_to_volume.py

| | |
|---|---|
| **Path** | `src/data/write_to_volume.py` |
| **Parameters** | `volume_path` |
| **Task Values** | — |
| **Logic** | Read ndjson_path from upstream task value. Copy NDJSON files to landing volume at `volume_path`. Partition files by record_type for clean Auto Loader consumption. The landing volume is the input for the SDP pipeline’s Auto Loader source. |
| **Spec** | L200-01 §4.1 |

#### 3A.3 post_to_zerobus.py

| | |
|---|---|
| **Path** | `src/data/post_to_zerobus.py` |
| **Parameters** | `catalog`, `schema` |
| **Task Values** | — |
| **Logic** | Read ndjson_path from upstream task value. POST records to ZeroBus API endpoint. Credentials from secret scope `mlops-workshop`. |
| **Note** | ZeroBus path only — used when `use_zerobus=true`. Can be deferred if ZeroBus SDK is not yet available. |
| **Spec** | L200-01 §4.1 |

---

### 3B: Ingestion Pipeline (Spark Declarative Pipeline)

The ingestion pipeline uses the **multi-file SDP editor**. Source files are plain `.py` files (not notebooks) with `from pyspark import pipelines as dp` decorators. The pipeline manages bronze and silver tables declaratively — no imperative DDL or manual table creation.

#### 3B.1 Pipeline Resource

New file: `resources/data_ingestion_pipeline.yml`

```yaml
resources:
  pipelines:
    data_ingestion_pipeline:
      name: "[${bundle.target}] mlops-workshop-data-ingestion-pipeline"
      catalog: ${var.catalog}
      target: ${resources.schemas.workshop_schema.name}
      libraries:
        - glob:
            include: ../src/pipeline/ingestion/**
      root_path: ../src/pipeline/ingestion
      serverless: true
      continuous: false
      development: true
      photon: true
      channel: current
      tags:
        bundle: mlops-workshop-infra
        workshop: mlops-workshop-2026
```

#### 3B.2 Job Resource Update

Update `resources/data_ingestion_job.yml`: remove `create_bronze_tables`, `autoload_to_bronze`, and `flatten_to_silver` notebook tasks. Add `run_ingestion_pipeline` as a `pipeline_task` that runs after data staging completes.

**Updated task graph:**
```
generate_ndjson → check_zerobus_gate
  ├─ TRUE:  post_to_zerobus
  └─ FALSE: write_ndjson_to_volume
run_ingestion_pipeline (converge, AT_LEAST_ONE_SUCCESS)
```

**Pipeline task reference:**
```yaml
- task_key: run_ingestion_pipeline
  depends_on:
    - task_key: post_to_zerobus
    - task_key: write_ndjson_to_volume
  run_if: AT_LEAST_ONE_SUCCESS
  pipeline_task:
    pipeline_id: ${resources.pipelines.data_ingestion_pipeline.id}
```

#### 3B.3 bronze.py

| | |
|---|---|
| **Path** | `src/pipeline/ingestion/bronze.py` |
| **Type** | SDP source file (multi-file editor, not a notebook) |
| **Import** | `from pyspark import pipelines as dp` |
| **Decorators** | `@dp.table` (streaming tables), `@dp.temporary_view()` |
| **Logic** | **`bronze_autoload`**: Streaming table via Auto Loader (`cloudFiles`) reading NDJSON from the landing volume. Extracts `record_type` from JSON, stores raw payload as STRING, adds `ingested_at` timestamp. **`bronze_zerobus`**: Streaming table for ZeroBus path (placeholder until ZeroBus SDK available). **`bronze_unified`**: Temporary view — UNION ALL of both bronze tables with a `source` column. |
| **Expectations** | `@dp.expect_or_drop("valid_payload", "payload IS NOT NULL")` on bronze tables |
| **Configuration** | Volume path passed via pipeline `configuration` block or `spark.conf` |
| **Spec** | L200-01 §4.1–4.2, L300 §4.1 |

#### 3B.4 silver.py

| | |
|---|---|
| **Path** | `src/pipeline/ingestion/silver.py` |
| **Type** | SDP source file (multi-file editor, not a notebook) |
| **Import** | `from pyspark import pipelines as dp` |
| **Decorators** | `@dp.materialized_view` |
| **Logic** | 5 materialized views, each reading from `bronze_unified` and filtering by `record_type`. Extracts typed fields from JSON payload using `parse_json(payload):field::TYPE` pattern. |
| **Spec** | L200-01 §4.4–4.5, L300 §4.3 |

**Silver tables (materialized views):**

| Table | record_type | Extracted Fields |
|---|---|---|
| `customer_profiles` | `customer_profile` | customer_id, signup_date, plan_type, region, company_size |
| `product_usage_events` | `usage_event` | customer_id, event_date, session_count, feature_usage, api_calls |
| `billing_history` | `billing` | customer_id, billing_date, amount, payment_status |
| `support_interactions` | `support_interaction` | customer_id, ticket_id, created_at, category, resolution |
| `churn_labels` | `churn_label` | customer_id, observation_date, churned |

---

## Phase 4: Feature Engineering

### 4.1 feature_definitions.py

| | |
|---|---|
| **Path** | `src/train/feature_definitions.py` |
| **Parameters** | `catalog`, `schema` |
| **Task Values** | — |
| **Installs** | `databricks-feature-engineering>=0.16.0` |
| **Logic** | Define 6 Feature Views using the declarative API. Register with `FeatureEngineeringClient.create_feature()`. Idempotent — safe to re-run. |
| **Spec** | L300 §6, Monorepo PROJECT_MEMORY §Feature Views |

**Feature definitions:**

| Feature | Source | Entity | Timeseries Col | Aggregation | Window |
|---|---|---|---|---|---|
| `avg_daily_sessions_30d` | `product_usage_events` | `customer_id` | `event_date` | `Avg(session_count)` | Tumbling 30d |
| `support_tickets_7d` | `support_interactions` | `customer_id` | `created_at` | `Count(ticket_id)` | Sliding 7d/1d |
| `total_revenue_90d` | `billing_history` | `customer_id` | `billing_date` | `Sum(amount)` | Tumbling 90d |
| `max_api_calls_7d` | `product_usage_events` | `customer_id` | `event_date` | `Max(api_calls)` | Sliding 7d/1d |
| `overdue_payment_count` | `billing_history` | `customer_id` | `billing_date` | `Count(*)` where overdue | Tumbling 90d |
| `escalated_tickets_30d` | `support_interactions` | `customer_id` | `created_at` | `Count(*)` where escalated | Tumbling 30d |

### 4.2 YAML Change Required

Add `register_features` task to `resources/training_job.yml` before `model_training`:

```yaml
- task_key: register_features
  notebook_task:
    notebook_path: ./src/train/feature_definitions.py
    base_parameters:
      catalog: ${var.catalog}
      schema: ${resources.schemas.workshop_schema.name}
```

Update `model_training` to depend on `register_features`:

```yaml
- task_key: model_training
  depends_on:
    - task_key: register_features
  ...
```

---

## Phase 5: Training & Validation

### 5.1 train.py

| | |
|---|---|
| **Path** | `src/train/train.py` |
| **Parameters** | `experiment_name`, `model_name`, `catalog`, `schema` |
| **Task Values** | `model_version` (str) |
| **Installs** | `databricks-feature-engineering>=0.16.0`, `scikit-learn`, `xgboost`, `mlflow` |
| **Logic** | Set MLflow experiment. Use Feature Views to create training set (`compute_features` + `create_training_set`). Join with `churn_labels` for target variable. Train XGBoost classifier. Log params, metrics, model to MLflow. Register model in UC via `fe.log_model()`. Set task value: `model_version`. |
| **Spec** | L200-01 §5, L300 §5 |

### 5.2 validate.py

| | |
|---|---|
| **Path** | `src/validate/validate.py` |
| **Parameters** | `model_name`, `model_version` |
| **Task Values** | `validation_passed` (str: `"true"` / `"false"`) |
| **Logic** | Load model version from UC. Run validation checks: schema validation, performance on holdout data. Set tag `validation_status=PASSED` or `FAILED`. If passed, assign `Challenger` alias via `set_registered_model_alias()`. Set task value. |
| **Spec** | L200-01 §5.2–5.3 |

---

## Phase 6: Promotion

### 6.1 promote.py

| | |
|---|---|
| **Path** | `src/promote/promote.py` |
| **Parameters** | `model_name` |
| **Task Values** | `promoted` (str: `"true"` / `"false"`) |
| **Logic** | Compare Challenger vs Champion metrics. Promotion criteria: `F1 > 0.75` AND `AUC >= champion_AUC - 0.005`. First model (no existing Champion) auto-promotes. |
| **Spec** | L200-01 §5.2–5.4 |

**Alias lifecycle on promotion:**

| Step | Action |
|------|--------|
| Promote | `set_registered_model_alias("PreviousChampion", old_champion)` |
| Promote | `set_registered_model_alias("Champion", challenger_version)` |
| Promote | Tag `promotion_status=CHAMPION`, `promoted_at=<ISO timestamp>` |
| Reject | Tag `promotion_status=REJECTED` |

---

## Phase 7: Deployment

The deployment job is a separate, event-driven path triggered by `MODEL_VERSION_READY`. It provides a governed evaluation and promotion layer distinct from the training job's fast-path promotion in Phase 6.

### 7.1 evaluate.py

| | |
|---|---|
| **Path** | `src/deploy/evaluate.py` |
| **Parameters** | `model_name` |
| **Task Values** | `should_deploy` (str: `"true"` / `"false"`) |
| **Logic** | Evaluate the new model version (triggered by MODEL_VERSION_READY event). Log evaluation metrics to model version page via MLflow 3 tracking. Determine deployment readiness based on evaluation results. Set task value. |
| **Spec** | L200-01 §6 |

### 7.2 promote_champion.py

| | |
|---|---|
| **Path** | `src/deploy/promote_champion.py` |
| **Parameters** | `model_name` |
| **Task Values** | — |
| **Logic** | Promote evaluated model to Champion alias. Set PreviousChampion on old Champion. This is the deployment job's final gate — separate from training's `promote.py`. |
| **Spec** | L200-01 §6 |

**Design note — two promotion paths:**
- **Training job** (`promote.py`): Immediate Challenger→Champion comparison during training pipeline. Fast path for first-time models and clear improvements.
- **Deployment job** (`promote_champion.py`): Event-driven evaluation on MODEL_VERSION_READY. Governance layer with optional human-in-the-loop approval. Decouples registration from deployment.

---

## Phase 8: Inference

### 8.1 batch_predict.py

| | |
|---|---|
| **Path** | `src/inference/batch_predict.py` |
| **Parameters** | `model_name`, `catalog`, `schema` |
| **Task Values** | — |
| **Logic** | Load model via `models:/{model_name}@Champion`. Use `fe.score_batch()` for feature-consistent inference (eliminates training-serving skew). Write predictions to `{catalog}.{schema}.churn_predictions` (overwrite mode). |
| **Spec** | L200-01 §7, L300 §4.4 |

**Output schema** (from L300 §4.4):

| Column | Type |
|--------|------|
| `customer_id` | STRING |
| `churn_probability` | DOUBLE |
| `prediction_timestamp` | TIMESTAMP |
| `model_version` | STRING |
| `avg_daily_sessions_30d` | DOUBLE |
| `support_tickets_7d` | INT |
| `total_revenue_90d` | DOUBLE |
| `actual_churned` | BOOLEAN |

---

## Phase 9: Integration Testing

### 9.1 Bundle Validation

```bash
databricks bundle validate --strict --target dev
```

### 9.2 Deployment Test

```bash
databricks bundle deploy --target dev
```

Verify: schema created, volume exists, experiment created, registered model exists, 4 jobs visible in workspace, 1 SDP pipeline visible.

### 9.3 Data Generation + Pipeline End-to-End

```bash
# Run data generation job (generates NDJSON, writes to volume, triggers pipeline)
databricks bundle run --target dev data_ingestion
```

Verify:
- Landing volume contains NDJSON files partitioned by record_type
- Pipeline update completes successfully (check pipeline UI or events)
- `bronze_autoload` streaming table populated via Auto Loader
- `bronze_unified` temporary view returns data
- 5 silver materialized views have expected row counts
- `customer_profiles` ≈ 500 rows, `product_usage_events` ≈ many thousands

**Standalone pipeline run** (without data generation, useful for re-processing):

```bash
databricks bundle run --target dev data_ingestion_pipeline
```

### 9.4 Training End-to-End

```bash
databricks bundle run --target dev churn_model_training
```

Verify:
- Feature Views registered in catalog
- Model version registered in UC
- `Challenger` alias assigned after validation
- `Champion` alias assigned after promotion (first run auto-promotes)
- `churn_predictions` table populated by final batch_inference task

### 9.5 Batch Inference Standalone

```bash
databricks bundle run --target dev churn_batch_inference
```

Verify: `churn_predictions` table refreshed with current @Champion model version.

---

## Implementation Order

| Step | Phase | Description | Dependency | Estimate |
|------|-------|-------------|-----------|----------|
| 1 | Phase 1 | Validation fixes | None | 15 min |
| 2 | Phase 2 | Create directory structure + stubs | Phase 1 | 15 min |
| 3 | Phase 3A.1 | `generate_ndjson.py` | Phase 2 | 1 hr |
| 4 | Phase 3A.2 | `write_to_volume.py` | Step 3 | 20 min |
| 5 | Phase 3A.3 | `post_to_zerobus.py` (can defer) | Step 3 | 30 min |
| 6 | Phase 3B.1 | Pipeline YAML + job YAML update | Phase 2 | 30 min |
| 7 | Phase 3B.3 | `bronze.py` (SDP — Auto Loader, bronze tables, unified view) | Step 6 | 1 hr |
| 8 | Phase 3B.4 | `silver.py` (SDP — 5 materialized views) | Step 7 | 45 min |
| 9 | Phase 4 | `feature_definitions.py` + YAML update | Step 8 | 1 hr |
| 10 | Phase 5.1 | `train.py` | Step 9 | 1.5 hr |
| 11 | Phase 5.2 | `validate.py` | Step 10 | 45 min |
| 12 | Phase 6 | `promote.py` | Step 11 | 45 min |
| 13 | Phase 7.1 | `evaluate.py` | Step 10 | 30 min |
| 14 | Phase 7.2 | `promote_champion.py` | Step 13 | 20 min |
| 15 | Phase 8 | `batch_predict.py` | Step 12 | 30 min |
| 16 | Phase 9 | Integration testing | All above | 1 hr |

**Total estimate:** ~9–10 hours of implementation

**Critical path:** Phases 2 → 3A.1 → 3B.1 → 3B.3 → 3B.4 → 4 → 5.1 (stubs → data gen → pipeline YAML → bronze SDP → silver SDP → features → training)

---

## Open Decisions

- [ ] **Feature registration task placement** — training job before model_training (recommended) vs data ingestion job after pipeline completes?
- [ ] **`model_update` trigger** — keep (requires CLI version check) or remove with manual/scheduled fallback?
- [ ] **ZeroBus path in SDP** — `bronze_zerobus` streaming table needs a source. If ZeroBus writes to a Delta table, the pipeline reads it. If ZeroBus is deferred, the streaming table is a placeholder. Requires ZeroBus SDK + secret scope `mlops-workshop` setup.
- [ ] **Two promotion paths** — training job's `promote.py` and deployment job's `promote_champion.py` overlap. Clarify when each is the canonical path. Is the deployment job a replacement or complement?
- [ ] **Resource file naming** — rename to `<name>.<resource_type>.yml` convention or keep current?
- [ ] **Pipeline volume_path configuration** — pass landing volume path via pipeline `configuration` block or `spark.conf`? Must match the path used by `write_to_volume.py`.

---

*Document Level: Implementation Plan*  
*Bundle: mlops-workshop-infra*  
*References: L200-01 (infra design), L300 (implementation specs), Monorepo PROJECT_MEMORY*

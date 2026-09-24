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
| `resources/data_ingestion_job.yml` | Authored | 7-task dual-path ingestion |
| `resources/training_job.yml` | Authored | 6-task training + promotion |
| `resources/deployment_job.yml` | Authored | 3-task MLflow 3 deployment |
| `resources/batch_inference_job.yml` | Authored | 1-task standalone inference |
| `src/` directory | Scaffolded | 13 .ipynb stubs created, implementation pending |
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

```
src/
├── data/
│   ├── create_bronze_tables.ipynb
│   ├── generate_ndjson.ipynb
│   ├── post_to_zerobus.ipynb
│   ├── write_to_volume.ipynb
│   ├── autoload_to_bronze.ipynb
│   └── flatten_to_silver.ipynb
├── train/
│   ├── feature_definitions.ipynb
│   └── train.ipynb
├── validate/
│   └── validate.ipynb
├── promote/
│   └── promote.ipynb
├── deploy/
│   ├── evaluate.ipynb
│   └── promote_champion.ipynb
└── inference/
    └── batch_predict.ipynb
```

**Decision required:** `feature_definitions.ipynb` is documented in the monorepo PROJECT_MEMORY but not referenced by any current job task. Recommended resolution:

- **(a) Add a `register_features` task to `training_job.yml` before `model_training`** — features depend on silver tables (created by ingestion) and must exist before training. Keeping them in the training job makes the dependency explicit.
- (b) Add to `data_ingestion_job.yml` after `flatten_to_silver` — couples feature registration to data freshness.
- (c) Import feature definitions from within `train.ipynb` — simplest, but hides a dependency.

---

## Phase 3: Data Pipeline Notebooks

All notebooks follow the project conventions:
- First cell: `%pip install` + `dbutils.library.restartPython()`
- Second cell: `dbutils.widgets.get()` for parameters
- Idempotent: CREATE IF NOT EXISTS / CREATE OR REPLACE / MERGE
- Task values via `dbutils.jobs.taskValues.set()`

### 3.1 create_bronze_tables.ipynb

| | |
|---|---|
| **Path** | `src/data/create_bronze_tables.ipynb` |
| **Parameters** | `catalog`, `schema` |
| **Task Values** | — |
| **Logic** | CREATE TABLE IF NOT EXISTS for `bronze_zerobus` and `bronze_autoload` (record_type STRING, payload STRING, ingested_at TIMESTAMP). CREATE OR REPLACE VIEW `bronze_unified` as UNION ALL of both with a `source` column. |
| **Spec** | L300 §4.1–4.2 |

### 3.2 generate_ndjson.ipynb

| | |
|---|---|
| **Path** | `src/data/generate_ndjson.ipynb` |
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

### 3.3 post_to_zerobus.ipynb

| | |
|---|---|
| **Path** | `src/data/post_to_zerobus.ipynb` |
| **Parameters** | `catalog`, `schema` |
| **Task Values** | — |
| **Logic** | Read ndjson_path from upstream task value. POST records to ZeroBus API endpoint. Credentials from secret scope `mlops-workshop`. |
| **Note** | ZeroBus path only — used when `use_zerobus=true`. Can be deferred if ZeroBus SDK is not yet available. |
| **Spec** | L200-01 §4.1 |

### 3.4 write_to_volume.ipynb

| | |
|---|---|
| **Path** | `src/data/write_to_volume.ipynb` |
| **Parameters** | `volume_path` |
| **Task Values** | — |
| **Logic** | Read ndjson_path from upstream task value. Copy NDJSON files to landing volume at `volume_path`. Partition files by record_type for clean Auto Loader consumption. |
| **Spec** | L200-01 §4.1 |

### 3.5 autoload_to_bronze.ipynb

| | |
|---|---|
| **Path** | `src/data/autoload_to_bronze.ipynb` |
| **Parameters** | `catalog`, `schema`, `volume_path` |
| **Task Values** | — |
| **Logic** | Auto Loader (`cloudFiles`) reads NDJSON from volume_path. Extracts `record_type` from JSON, stores raw payload as STRING. Writes to `bronze_autoload` with `trigger(availableNow=True)`. |
| **Spec** | L200-01 §4.1, L300 §4.1 |

### 3.6 flatten_to_silver.ipynb

| | |
|---|---|
| **Path** | `src/data/flatten_to_silver.ipynb` |
| **Parameters** | `catalog`, `schema` |
| **Task Values** | — |
| **Logic** | Read from `bronze_unified` view. For each record_type, apply `parse_json(payload):field::TYPE` extraction pattern. Write/overwrite 5 silver tables. |
| **Spec** | L200-01 §4.4–4.5, L300 §4.3 |

**Silver extraction pattern:**
```sql
CREATE OR REPLACE TABLE {catalog}.{schema}.{table} AS
SELECT
  parse_json(payload):field_name::TYPE AS column_name,
  ...
  source,
  ingested_at
FROM {catalog}.{schema}.bronze_unified
WHERE record_type = '{type}'
```

---

## Phase 4: Feature Engineering

### 4.1 feature_definitions.ipynb

| | |
|---|---|
| **Path** | `src/train/feature_definitions.ipynb` |
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
    notebook_path: ./src/train/feature_definitions.ipynb
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

### 5.1 train.ipynb

| | |
|---|---|
| **Path** | `src/train/train.ipynb` |
| **Parameters** | `experiment_name`, `model_name`, `catalog`, `schema` |
| **Task Values** | `model_version` (str) |
| **Installs** | `databricks-feature-engineering>=0.16.0`, `scikit-learn`, `xgboost`, `mlflow` |
| **Logic** | Set MLflow experiment. Use Feature Views to create training set (`compute_features` + `create_training_set`). Join with `churn_labels` for target variable. Train XGBoost classifier. Log params, metrics, model to MLflow. Register model in UC via `fe.log_model()`. Set task value: `model_version`. |
| **Spec** | L200-01 §5, L300 §5 |

### 5.2 validate.ipynb

| | |
|---|---|
| **Path** | `src/validate/validate.ipynb` |
| **Parameters** | `model_name`, `model_version` |
| **Task Values** | `validation_passed` (str: `"true"` / `"false"`) |
| **Logic** | Load model version from UC. Run validation checks: schema validation, performance on holdout data. Set tag `validation_status=PASSED` or `FAILED`. If passed, assign `Challenger` alias via `set_registered_model_alias()`. Set task value. |
| **Spec** | L200-01 §5.2–5.3 |

---

## Phase 6: Promotion

### 6.1 promote.ipynb

| | |
|---|---|
| **Path** | `src/promote/promote.ipynb` |
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

### 7.1 evaluate.ipynb

| | |
|---|---|
| **Path** | `src/deploy/evaluate.ipynb` |
| **Parameters** | `model_name` |
| **Task Values** | `should_deploy` (str: `"true"` / `"false"`) |
| **Logic** | Evaluate the new model version (triggered by MODEL_VERSION_READY event). Log evaluation metrics to model version page via MLflow 3 tracking. Determine deployment readiness based on evaluation results. Set task value. |
| **Spec** | L200-01 §6 |

### 7.2 promote_champion.ipynb

| | |
|---|---|
| **Path** | `src/deploy/promote_champion.ipynb` |
| **Parameters** | `model_name` |
| **Task Values** | — |
| **Logic** | Promote evaluated model to Champion alias. Set PreviousChampion on old Champion. This is the deployment job's final gate — separate from training's `promote.ipynb`. |
| **Spec** | L200-01 §6 |

**Design note — two promotion paths:**
- **Training job** (`promote.ipynb`): Immediate Challenger→Champion comparison during training pipeline. Fast path for first-time models and clear improvements.
- **Deployment job** (`promote_champion.ipynb`): Event-driven evaluation on MODEL_VERSION_READY. Governance layer with optional human-in-the-loop approval. Decouples registration from deployment.

---

## Phase 8: Inference

### 8.1 batch_predict.ipynb

| | |
|---|---|
| **Path** | `src/inference/batch_predict.ipynb` |
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

Verify: schema created, volume exists, experiment created, registered model exists, 4 jobs visible in workspace.

### 9.3 Data Ingestion End-to-End

```bash
databricks bundle run --target dev data_ingestion
```

Verify:
- `bronze_autoload` table populated (Auto Loader path)
- `bronze_unified` view returns data
- 5 silver tables have expected row counts
- `customer_profiles` ≈ 500 rows, `product_usage_events` ≈ many thousands

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
| 2 | Phase 2 | Create directory structure + stub notebooks | Phase 1 | 15 min |
| 3 | Phase 3.1 | `create_bronze_tables.ipynb` | Phase 2 | 30 min |
| 4 | Phase 3.2 | `generate_ndjson.ipynb` | Phase 2 | 1 hr |
| 5 | Phase 3.4 | `write_to_volume.ipynb` | Step 4 | 20 min |
| 6 | Phase 3.5 | `autoload_to_bronze.ipynb` | Step 5 | 45 min |
| 7 | Phase 3.6 | `flatten_to_silver.ipynb` | Step 3 | 45 min |
| 8 | Phase 3.3 | `post_to_zerobus.ipynb` (can defer) | Step 4 | 30 min |
| 9 | Phase 4 | `feature_definitions.ipynb` + YAML update | Step 7 | 1 hr |
| 10 | Phase 5.1 | `train.ipynb` | Step 9 | 1.5 hr |
| 11 | Phase 5.2 | `validate.ipynb` | Step 10 | 45 min |
| 12 | Phase 6 | `promote.ipynb` | Step 11 | 45 min |
| 13 | Phase 7.1 | `evaluate.ipynb` | Step 10 | 30 min |
| 14 | Phase 7.2 | `promote_champion.ipynb` | Step 13 | 20 min |
| 15 | Phase 8 | `batch_predict.ipynb` | Step 12 | 30 min |
| 16 | Phase 9 | Integration testing | All above | 1 hr |

**Total estimate:** ~9–10 hours of implementation

**Critical path:** Phases 1 → 3.1 → 3.2 → 3.6 → 4 → 5.1 (validation → bronze DDL → data gen → silver → features → training)

---

## Open Decisions

- [ ] **Feature registration task placement** — training job before model_training (recommended) vs data ingestion job after flatten_to_silver?
- [ ] **`model_update` trigger** — keep (requires CLI version check) or remove with manual/scheduled fallback?
- [ ] **ZeroBus notebook** — implement now or defer? Requires ZeroBus SDK + secret scope `mlops-workshop` setup.
- [ ] **Two promotion paths** — training job's `promote.ipynb` and deployment job's `promote_champion.ipynb` overlap. Clarify when each is the canonical path. Is the deployment job a replacement or complement?
- [ ] **Resource file naming** — rename to `<name>.<resource_type>.yml` convention or keep current?

---

*Document Level: Implementation Plan*  
*Bundle: mlops-workshop-infra*  
*References: L200-01 (infra design), L300 (implementation specs), Monorepo PROJECT_MEMORY*

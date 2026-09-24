# L200-01 — `-infra` Bundle: Infrastructure, Data, Training & Promotion

**Classification:** Level 200 — Per-Component Detailed Design
**Bundle:** `mlops-workshop-infra`
**Scope:** UC schema, volume, experiment, registered model, data ingestion (dual-path), training, validation, champion/challenger promotion, batch inference, MLflow 3 deployment job
**Cross-cutting patterns:** See L100 §3

---

## 1. Overview

The `-infra` bundle is the foundation of the workshop. It deploys first and creates every UC resource that downstream bundles depend on. It also contains all jobs: data ingestion, model training + promotion, MLflow 3 deployment automation, and batch inference.

**Deployment command:**
```bash
cd mlops-workshop-infra
databricks bundle deploy -t dev
```

---

## 2. Dependencies

| Depends On | Provided By | Contract |
|------------|-------------|----------|
| Customer catalog | Customer admin | USE CATALOG + CREATE SCHEMA grants |
| ZeroBus endpoint (optional) | Workspace config | Secret scope `mlops-workshop` with endpoint + SPN credentials |
| Databricks CLI | Participant machine | `databricks bundle validate` must succeed |

---

## 3. Bundle Resources

### 3.1 Schema

```yaml
resources:
  schemas:
    workshop_schema:
      catalog_name: ${var.catalog}
      name: ${var.user_schema}
      comment: "MLOps workshop schema for ${bundle.user_name}"
```

All other resources derive their catalog/schema from `${resources.schemas.workshop_schema.*}`.

### 3.2 Volume

```yaml
resources:
  volumes:
    landing_volume:
      catalog_name: ${resources.schemas.workshop_schema.catalog_name}
      schema_name: ${resources.schemas.workshop_schema.name}
      name: landing
      volume_type: MANAGED
      comment: "NDJSON landing zone for Auto Loader ingestion path"
```

### 3.3 Experiment

```yaml
resources:
  experiments:
    churn_experiment:
      name: "/Workspace/Users/${workspace.current_user.userName}/mlops-workshop-churn"
      tags:
        - key: mlflow.note.content
          value: "Churn prediction experiment — MLOps Workshop"
```

### 3.4 Registered Model

```yaml
resources:
  registered_models:
    churn_model:
      catalog_name: ${resources.schemas.workshop_schema.catalog_name}
      schema_name: ${resources.schemas.workshop_schema.name}
      name: churn_model
      comment: "Customer churn prediction model — MLOps Workshop"
```

### 3.5 Variables

```yaml
variables:
  catalog:
    description: "Customer-provided Unity Catalog"
    default: "mlops_workshop"
  user_schema:
    description: "Per-participant schema name"
  use_zerobus:
    description: "Route data through ZeroBus API (true) or Auto Loader (false)"
    default: "false"
```

---

## 4. Data Ingestion Job Design

### 4.1 Dual-Path Architecture

The `use_zerobus` variable (default `false`) controls which ingestion path is used. A condition task gates the routing. Silver reads from BOTH bronze tables via `bronze_unified` UNION ALL view regardless of which path was active.

> See docs/diagrams/02_data_ingestion_flow.md

### 4.2 Task Graph

```
create_bronze_tables
    ↓
generate_ndjson
    ↓
check_zerobus_gate (condition: use_zerobus == "true")
    ├── TRUE:  stream_via_zerobus → bronze_zerobus
    └── FALSE: write_ndjson_to_volume → autoload_to_bronze → bronze_autoload
                    ↓
            flatten_bronze_to_silver (UNION ALL → parse_json() → 5 Silver tables)
```

### 4.3 Bronze Table Schema (ZeroBus Contract)

```sql
CREATE TABLE bronze_zerobus / bronze_autoload (
  record_type STRING,    -- Entity type discriminator
  payload STRING,        -- JSON string (parsed in Silver via parse_json())
  ingested_at TIMESTAMP  -- Ingestion timestamp
)
```

### 4.4 Silver Extraction Pattern

```sql
-- All silver tables follow this pattern:
SELECT
  parse_json(payload):field_name::TARGET_TYPE AS column_name,
  ...
FROM bronze_unified
WHERE record_type = 'entity_type'
```

### 4.5 Silver Tables Produced

| Table | Key | Grain | Source record_type |
|-------|-----|-------|--------------------|
| `customer_profiles` | customer_id | One row per customer | `customer_profile` |
| `product_usage_events` | customer_id + event_date | One row per customer per day | `usage_event` |
| `billing_history` | customer_id + billing_date | One row per billing event | `billing` |
| `support_interactions` | customer_id + ticket_id | One row per ticket | `support_interaction` |
| `churn_labels` | customer_id + observation_date | One row per observation | `churn_label` |

---

## 5. Training + Promotion Job Design

### 5.1 Task Graph

```
model_training
    ↓
model_validation (assigns Challenger alias + validation tags)
    ↓
validation_gate (condition: validation_passed == true)
    ↓
champion_challenger_comparison (compares Challenger vs Champion)
    ↓
promotion_gate (condition: promoted == true)
    ↓
batch_inference (loads @Champion alias)
```

> See docs/diagrams/03_champion_challenger_flow.md

### 5.2 Alias Lifecycle

| Step | Action | Alias State |
|------|--------|-------------|
| After validation passes | `set_registered_model_alias("Challenger", new_version)` | Challenger → new version |
| After promotion | `set_registered_model_alias("PreviousChampion", old_champion)` | PreviousChampion → old |
| After promotion | `set_registered_model_alias("Champion", challenger_version)` | Champion → new version |
| After rejection | Tag `promotion_status=REJECTED` | Challenger removed |

### 5.3 Validation Tags

| Tag Key | Values | Set By |
|---------|--------|--------|
| `validation_status` | `PENDING`, `PASSED`, `FAILED` | validate.py |
| `promotion_status` | `CHAMPION`, `REJECTED` | promote.py |
| `promoted_at` | ISO timestamp | promote.py |

### 5.4 Promotion Criteria

```python
# Challenger must meet ALL:
candidate_f1 > 0.75                          # Minimum threshold
candidate_auc >= champion_auc - 0.005        # Within tolerance of Champion
# First model (no existing Champion) auto-promotes
```

---

## 6. MLflow 3 Deployment Job

Auto-triggers on `MODEL_VERSION_READY` for the registered model. Provides a governed, auditable deployment pipeline with optional human-in-the-loop approval.

```yaml
trigger:
  model_update:
    model_name: "${resources.registered_models.churn_model...}"
    events:
      - MODEL_VERSION_READY
```

### Task Graph

```
evaluate → approve (condition gate) → promote_champion
```

Evaluation metrics are logged to the model version page via MLflow 3 tracking.

---

## 7. Batch Inference Job

Loads the `@Champion` alias — automatically picks up promotions on next run.

```python
model_uri = f"models:/{model_name}@Champion"
predictions = fe.score_batch(model_uri=model_uri, df=customers_to_score_df)
predictions.write.mode("overwrite").saveAsTable(f"{catalog}.{schema}.churn_predictions")
```

---

## 8. Non-Functional Requirements

| NFR | Target |
|-----|--------|
| Deploy time | < 2 minutes for `bundle deploy`
| Compute | Serverless (latest environment, no ML Runtime) | |
| Data ingestion | 500 customers × ~60 records each ≈ 30K records in < 5 minutes |
| Training time | < 10 minutes on 2-worker cluster |
| Promotion | Atomic alias swap (< 1 second) |
| Participant isolation | Per-schema — no cross-participant data leakage |

---

## 9. Testing

| Test | What | How |
|------|------|-----|
| Bundle validation | YAML correctness | `databricks bundle validate -t dev` |
| Schema creation | Schema exists after deploy | Query `information_schema.schemata` |
| Data ingestion | Silver tables populated | `SELECT COUNT(*) FROM customer_profiles` |
| Model registration | Model version exists | `client.get_latest_versions()` |
| Alias assignment | Champion alias set | `client.get_model_version_by_alias("Champion")` |

---

## 10. Open Questions

- [ ] Should the workshop support protobuf ZeroBus ingestion in addition to JSON?
- [ ] Should the deployment job include a human-in-the-loop approval task for the workshop, or auto-approve?
- [ ] Should we add a `pipeline` resource for SDP-based silver flattening as an advanced module?

---

*Document Level: L200 — Per-Component Detailed Design*
*Bundle: mlops-workshop-infra*
*References: L100 §3 (cross-cutting patterns), L100 §4 (component inventory)*

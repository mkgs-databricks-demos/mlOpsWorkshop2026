# L200-01 — `-infra` Bundle: Infrastructure, Data, Training & Promotion

**Classification:** Level 200 — Per-Component Detailed Design
**Bundle:** `mlops-workshop-infra`
**Scope:** UC schema, volume, experiment, registered model, SDP ingestion pipeline, data prep job (dual-path), training, validation, champion/challenger promotion, batch inference, MLflow 3 deployment job
**Cross-cutting patterns:** See L100 §3

---

## 1. Overview

The `-infra` bundle is the foundation of the workshop. It deploys first and creates every UC resource that downstream bundles depend on. It contains the SDP ingestion pipeline (bronze → silver), a data prep job that lands synthetic data and triggers the pipeline, plus the model training + promotion, MLflow 3 deployment automation, and batch inference jobs.

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

### 3.4 Ingestion Pipeline (SDP)

```yaml
resources:
  pipelines:
    data_ingestion_pipeline:
      name: "[${bundle.target}] mlops-workshop-data-ingestion"
      catalog: ${resources.schemas.workshop_schema.catalog_name}
      target: ${resources.schemas.workshop_schema.name}
      channel: CURRENT
      serverless: true
      development: true
      libraries:
        - glob:
            include: ../src/pipeline/ingestion/**
      configuration:
        volume_path: "/Volumes/${resources.schemas.workshop_schema.catalog_name}/${resources.schemas.workshop_schema.name}/${resources.volumes.landing_volume.name}"
```

### 3.5 Registered Model

```yaml
resources:
  registered_models:
    churn_model:
      catalog_name: ${resources.schemas.workshop_schema.catalog_name}
      schema_name: ${resources.schemas.workshop_schema.name}
      name: churn_model
      comment: "Customer churn prediction model — MLOps Workshop"
```

### 3.6 Variables

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

## 4. Data Ingestion Design

Data ingestion is split into two resources:

1. **SDP Pipeline** (`data_ingestion_pipeline`) — declares bronze streaming tables, a unified temporary view, and five silver streaming tables with data quality expectations.
2. **Data Prep Job** (`data_ingestion`) — generates synthetic data, lands it via the appropriate path, then triggers the pipeline.

### 4.1 Dual-Path Architecture

The `use_zerobus` variable (default `false`) controls where data **lands**. The SDP pipeline declares both bronze streaming tables and processes whichever has data. Silver reads from BOTH via a `bronze_unified` temporary view.

> See docs/diagrams/02_data_ingestion_flow.md

### 4.2 Data Prep Job Task Graph

```
generate_ndjson
    ↓
check_zerobus_gate (condition: use_zerobus == "true")
    ├── TRUE:  post_to_zerobus
    └── FALSE: write_ndjson_to_volume
    ↓
run_ingestion_pipeline (converge, AT_LEAST_ONE_SUCCESS → pipeline_task)
```

### 4.3 SDP Pipeline Structure

The pipeline is a multi-file SDP under `src/pipeline/ingestion/`:

| File | SDP Object | Type | Purpose |
|------|-----------|------|---------|
| `bronze_autoload.py` | `bronze_autoload` | Streaming table | Auto Loader from landing volume |
| `bronze_zerobus.py` | `bronze_zerobus` | Streaming table | Reads from ZeroBus-populated raw table |
| `bronze_unified.py` | `bronze_unified` | Temporary view | UNION ALL of both bronze tables |
| `silver_tables.py` | 5 streaming tables | Streaming tables | `parse_json()` extraction per entity type |

### 4.4 Bronze Streaming Tables

```python
from pyspark import pipelines as dp

@dp.table(
    name="bronze_autoload",
    comment="Raw NDJSON ingested via Auto Loader from landing volume"
)
@dp.expect("valid_record_type", "record_type IS NOT NULL")
@dp.expect("valid_payload", "payload IS NOT NULL")
def bronze_autoload():
    volume_path = spark.conf.get("volume_path")
    return (
        spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "json")
            .option("cloudFiles.inferColumnTypes", "false")
            .load(volume_path)
            .selectExpr(
                "record_type",
                "CAST(payload AS STRING) AS payload",
                "current_timestamp() AS ingested_at"
            )
    )
```

### 4.5 Bronze Unified Temporary View

```python
@dp.temporary_view()
def bronze_unified():
    return spark.sql("""
        SELECT record_type, payload, ingested_at, 'autoload' AS source
        FROM STREAM(LIVE.bronze_autoload)
        UNION ALL
        SELECT record_type, payload, ingested_at, 'zerobus' AS source
        FROM STREAM(LIVE.bronze_zerobus)
    """)
```

### 4.6 Silver Streaming Tables

```python
@dp.table(
    name="customer_profiles",
    comment="Customer profile dimension"
)
@dp.expect_or_drop("valid_customer_id", "customer_id IS NOT NULL")
def customer_profiles():
    return spark.sql("""
        SELECT
            parse_json(payload):customer_id::STRING AS customer_id,
            parse_json(payload):signup_date::DATE AS signup_date,
            parse_json(payload):plan_type::STRING AS plan_type,
            parse_json(payload):region::STRING AS region,
            parse_json(payload):company_size::STRING AS company_size,
            source,
            ingested_at
        FROM STREAM(LIVE.bronze_unified)
        WHERE record_type = 'customer_profile'
    """)
```

### 4.7 Data Quality Expectations

| Layer | Expectation | Action | Applied To |
|-------|------------|--------|------------|
| Bronze | `valid_record_type` | Warn (track) | Both bronze tables |
| Bronze | `valid_payload` | Warn (track) | Both bronze tables |
| Silver | `valid_customer_id` | Drop | All silver tables |
| Silver | `valid_date` | Drop | Tables with date keys |

### 4.8 Silver Tables Produced

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
| Data prep + pipeline | 500 customers × ~60 records each ≈ 30K records; data landing < 2 min, pipeline refresh < 3 min |
| Training time | < 10 minutes on 2-worker cluster |
| Promotion | Atomic alias swap (< 1 second) |
| Participant isolation | Per-schema — no cross-participant data leakage |

---

## 9. Testing

| Test | What | How |
|------|------|-----|
| Bundle validation | YAML correctness | `databricks bundle validate -t dev` |
| Schema creation | Schema exists after deploy | Query `information_schema.schemata` |
| Pipeline refresh | Silver tables populated | `SELECT COUNT(*) FROM customer_profiles` |
| Pipeline expectations | No dropped rows at bronze | Pipeline event log: expectation metrics |
| Model registration | Model version exists | `client.get_latest_versions()` |
| Alias assignment | Champion alias set | `client.get_model_version_by_alias("Champion")` |

---

## 10. Open Questions

- [ ] Should the workshop support protobuf ZeroBus ingestion in addition to JSON?
- [ ] Should the deployment job include a human-in-the-loop approval task for the workshop, or auto-approve?
- [x] ~~Should we add a `pipeline` resource for SDP-based silver flattening as an advanced module?~~ → **Yes — adopted as the primary ingestion pattern.** Data ingestion now uses an SDP pipeline for bronze → silver processing.

---

*Document Level: L200 — Per-Component Detailed Design*
*Bundle: mlops-workshop-infra*
*References: L100 §3 (cross-cutting patterns), L100 §4 (component inventory)*

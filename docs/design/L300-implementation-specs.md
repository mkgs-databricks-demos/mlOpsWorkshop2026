# L300 — Implementation Specifications

**Classification:** Level 300 — Module-Level Implementation Specs
**Scope:** Complete YAML for all three bundles, notebook contracts, data schemas, Feature View definitions
**Cross-cutting patterns:** See L100 §3

---

## 1. Complete `-infra` Bundle YAML

```yaml
# mlops-workshop-infra/databricks.yml
bundle:
  name: mlops-workshop-infra

variables:
  catalog:
    description: "Customer-provided Unity Catalog (USE CATALOG + CREATE SCHEMA)"
    default: "mlops_workshop"
  user_schema:
    description: "Per-participant schema name"
  use_zerobus:
    description: "Route data through ZeroBus API (true) or Auto Loader (false)"
    default: "false"

targets:
  dev:
    default: true
    workspace:
      host: ${{var.workspace_url}}
    variables:
      catalog: "mlops_workshop"
      user_schema: "user_${{bundle.user_name}}"

resources:
  schemas:
    workshop_schema:
      catalog_name: ${{var.catalog}}
      name: ${{var.user_schema}}
      comment: "MLOps workshop schema for ${{bundle.user_name}}"

  volumes:
    landing_volume:
      catalog_name: ${{resources.schemas.workshop_schema.catalog_name}}
      schema_name: ${{resources.schemas.workshop_schema.name}}
      name: landing
      volume_type: MANAGED

  experiments:
    churn_experiment:
      name: "/Workspace/Users/${{workspace.current_user.userName}}/mlops-workshop-churn"
      tags:
        - key: mlflow.note.content
          value: "Churn prediction experiment"

  registered_models:
    churn_model:
      catalog_name: ${{resources.schemas.workshop_schema.catalog_name}}
      schema_name: ${{resources.schemas.workshop_schema.name}}
      name: churn_model
      comment: "Customer churn prediction model"
```

---

## 2. Complete `-ai` Bundle YAML

```yaml
# mlops-workshop-ai/databricks.yml
bundle:
  name: mlops-workshop-ai

variables:
  catalog:
    default: "mlops_workshop"
  user_schema:
    description: "Must match -infra schema"
  registered_model_name:
    description: "Full 3-level name from -infra"

targets:
  dev:
    default: true
    workspace:
      host: ${{var.workspace_url}}
    variables:
      catalog: "mlops_workshop"
      user_schema: "user_${{bundle.user_name}}"
      registered_model_name: "mlops_workshop.user_${{bundle.user_name}}.churn_model"

resources:
  model_serving_endpoints:
    churn_serving:
      name: "churn-serving-${{var.user_schema}}"
      config:
        served_entities:
          - entity_name: ${{var.registered_model_name}}
            entity_version: "1"
            workload_size: "Small"
            scale_to_zero_enabled: true
      ai_gateway:
        inference_table_config:
          catalog_name: ${{var.catalog}}
          schema_name: ${{var.user_schema}}
          table_name_prefix: "churn_serving"
          enabled: true
```

---

## 3. Complete `-monitors` Bundle YAML

```yaml
# mlops-workshop-monitors/databricks.yml
bundle:
  name: mlops-workshop-monitors

variables:
  catalog:
    default: "mlops_workshop"
  user_schema:
    description: "Must match -infra schema"
  warehouse_id:
    description: "SQL warehouse for dashboard"
  training_job_id:
    description: "Job ID of -infra training job"

targets:
  dev:
    default: true
    workspace:
      host: ${{var.workspace_url}}
    variables:
      catalog: "mlops_workshop"
      user_schema: "user_${{bundle.user_name}}"

resources:
  quality_monitors:
    predictions_monitor:
      table_name: ${{var.catalog}}.${{var.user_schema}}.churn_predictions
      output_schema_name: ${{var.catalog}}.${{var.user_schema}}
      assets_dir: /Workspace/Users/${{workspace.current_user.userName}}/monitors/predictions
      inference_log:
        granularities: ["1 day"]
        timestamp_col: prediction_timestamp
        model_id_col: model_version
        prediction_col: churn_probability
        label_col: actual_churned
        problem_type: PROBLEM_TYPE_CLASSIFICATION
      schedule:
        quartz_cron_expression: "0 0 10 * * ?"
        timezone_id: "UTC"

    features_monitor:
      table_name: ${{var.catalog}}.${{var.user_schema}}.churn_features_avg_daily_sessions_30d
      output_schema_name: ${{var.catalog}}.${{var.user_schema}}
      assets_dir: /Workspace/Users/${{workspace.current_user.userName}}/monitors/features
      time_series:
        granularities: ["1 day"]
        timestamp_col: window_end
      schedule:
        quartz_cron_expression: "0 0 9 * * ?"
        timezone_id: "UTC"

    serving_monitor:
      table_name: ${{var.catalog}}.${{var.user_schema}}.churn_serving_payload
      output_schema_name: ${{var.catalog}}.${{var.user_schema}}
      assets_dir: /Workspace/Users/${{workspace.current_user.userName}}/monitors/serving
      time_series:
        granularities: ["1 hour"]
        timestamp_col: timestamp_ms
      schedule:
        quartz_cron_expression: "0 */30 * * * ?"
        timezone_id: "UTC"
```

---

## 4. Data Schemas

### 4.1 Bronze Tables

```sql
-- Both tables share the same schema (ZeroBus contract)
CREATE TABLE bronze_zerobus / bronze_autoload (
  record_type STRING COMMENT 'Entity type discriminator',
  payload STRING COMMENT 'JSON string — parsed via parse_json() in Silver',
  ingested_at TIMESTAMP COMMENT 'Ingestion timestamp'
)
```

### 4.2 Bronze Unified View

```sql
CREATE OR REPLACE VIEW bronze_unified AS
SELECT record_type, payload, ingested_at, 'zerobus' AS source FROM bronze_zerobus
UNION ALL
SELECT record_type, payload, ingested_at, 'autoload' AS source FROM bronze_autoload
```

### 4.3 Silver Tables

| Table | Columns | Types |
|-------|---------|-------|
| `customer_profiles` | customer_id, signup_date, plan_type, region, company_size, source, ingested_at | STRING, DATE, STRING, STRING, STRING, STRING, TIMESTAMP |
| `product_usage_events` | customer_id, event_date, session_count, feature_usage, api_calls, source, ingested_at | STRING, DATE, INT, INT, INT, STRING, TIMESTAMP |
| `billing_history` | customer_id, billing_date, amount, payment_status, source, ingested_at | STRING, DATE, DOUBLE, STRING, STRING, TIMESTAMP |
| `support_interactions` | customer_id, ticket_id, created_at, category, resolution, source, ingested_at | STRING, STRING, TIMESTAMP, STRING, STRING, STRING, TIMESTAMP |
| `churn_labels` | customer_id, observation_date, churned, source, ingested_at | STRING, DATE, BOOLEAN, STRING, TIMESTAMP |

### 4.4 Predictions Table

```sql
CREATE TABLE churn_predictions (
  customer_id STRING,
  churn_probability DOUBLE,
  prediction_timestamp TIMESTAMP,
  model_version STRING,
  avg_daily_sessions_30d DOUBLE,
  support_tickets_7d INT,
  total_revenue_90d DOUBLE,
  actual_churned BOOLEAN
)
```

---

## 5. Notebook Interface Contracts

| Notebook | Parameters | Task Value Outputs |
|----------|-----------|-------------------|
| `create_bronze_tables.py` | catalog, schema | — |
| `generate_ndjson.py` | catalog, schema | ndjson_path, record_count |
| `post_to_zerobus.py` | catalog, schema | — |
| `write_to_volume.py` | volume_path | — |
| `autoload_to_bronze.py` | catalog, schema, volume_path | — |
| `flatten_to_silver.py` | catalog, schema | — |
| `feature_definitions.py` | catalog, schema | — |
| `train.py` | experiment_name, model_name, catalog, schema | model_version |
| `validate.py` | model_name, model_version | validation_passed |
| `promote.py` | model_name | promoted |
| `evaluate.py` | model_name | should_deploy |
| `promote_champion.py` | model_name | — |
| `batch_predict.py` | model_name, catalog, schema | — |
| `check_metrics.py` | catalog, schema, max_psi, min_accuracy, max_consecutive_drift_days | retrain_needed |

---

## 6. Feature View Definitions

| Feature | Source Table | Entity | Timeseries Col | Aggregation | Window |
|---------|-------------|--------|----------------|-------------|--------|
| `avg_daily_sessions_30d` | `product_usage_events` | `customer_id` | `event_date` | `Avg(session_count)` | Tumbling 30d |
| `support_tickets_7d` | `support_interactions` | `customer_id` | `created_at` | `Count(ticket_id)` | Sliding 7d/1d |
| `total_revenue_90d` | `billing_history` | `customer_id` | `billing_date` | `Sum(amount)` | Tumbling 90d |
| `max_api_calls_7d` | `product_usage_events` | `customer_id` | `event_date` | `Max(api_calls)` | Sliding 7d/1d |
| `overdue_payment_count` | `billing_history` | `customer_id` | `billing_date` | `Count(*)` where overdue | Tumbling 90d |
| `escalated_tickets_30d` | `support_interactions` | `customer_id` | `created_at` | `Count(*)` where escalated | Tumbling 30d |

---

## 7. CI/CD Pipeline Spec

### 7.1 GitHub Actions — Three-Stage Deploy

```yaml
jobs:
  test-and-validate:
    steps:
      - pytest tests/unit/
      - databricks bundle validate -t staging (all 3 bundles)

  deploy-infra:
    needs: test-and-validate
    steps:
      - cd mlops-workshop-infra && databricks bundle deploy -t $TARGET
      - databricks bundle run -t $TARGET churn_model_training

  deploy-ai:
    needs: deploy-infra
    steps:
      - cd mlops-workshop-ai && databricks bundle deploy -t $TARGET

  deploy-monitors:
    needs: deploy-ai
    steps:
      - cd mlops-workshop-monitors && databricks bundle deploy -t $TARGET
```

### 7.2 Environment Matrix

| Variable | dev | staging | prod |
|----------|-----|---------|------|
| catalog | mlops_workshop | staging_catalog | prod_catalog |
| user_schema | user_${{bundle.user_name}} | mlops_staging | mlops_prod |
| use_zerobus | false | true | true |

---

## 8. Dashboard Dataset Queries

### 8.1 Model Accuracy Over Time
```sql
SELECT window.start AS period_start, model_id_col AS model_version,
  MAX(CASE WHEN column_name = ':table' THEN accuracy END) AS accuracy,
  MAX(CASE WHEN column_name = ':table' THEN f1_score END) AS f1_score
FROM churn_predictions_profile_metrics
WHERE log_type = 'INPUT' AND slice_key IS NULL
GROUP BY window.start, model_id_col ORDER BY period_start
```

### 8.2 Feature Drift Heatmap
```sql
SELECT window.start AS period_start, column_name AS feature,
  ks_test.pvalue AS ks_pvalue, wasserstein_distance,
  CASE WHEN ks_test.pvalue < 0.01 THEN 'HIGH'
       WHEN ks_test.pvalue < 0.05 THEN 'MEDIUM' ELSE 'LOW' END AS drift_severity
FROM churn_features_avg_daily_sessions_30d_drift_metrics
WHERE drift_type = 'CONSECUTIVE' AND column_name != ':table'
ORDER BY period_start, feature
```

### 8.3 Serving Health
```sql
SELECT window.start AS period_start, count AS request_count, avg AS avg_value
FROM churn_serving_payload_profile_metrics
WHERE column_name = 'status_code' AND log_type = 'INPUT'
ORDER BY period_start
```

---

## 9. Retraining Trigger Logic

```python
# Thresholds (job parameters)
max_psi = 0.25
min_accuracy = 0.70
max_consecutive_drift_days = 5

# Check PSI
high_drift_days = spark.sql("""
  SELECT COUNT(*) FROM (
    SELECT population_stability_index AS psi
    FROM {catalog}.{schema}.churn_predictions_drift_metrics
    WHERE column_name = ':table' AND drift_type = 'CONSECUTIVE'
    ORDER BY window.start DESC LIMIT {max_consecutive_drift_days}
  ) WHERE psi > {max_psi}
""").collect()[0][0]

# Check accuracy
latest_accuracy = spark.sql("""
  SELECT MAX(CASE WHEN column_name = ':table' THEN accuracy END)
  FROM {catalog}.{schema}.churn_predictions_profile_metrics
  WHERE log_type = 'INPUT' AND slice_key IS NULL
  ORDER BY window.start DESC LIMIT 1
""").collect()[0][0] or 1.0

retrain_needed = (high_drift_days >= max_consecutive_drift_days) or (latest_accuracy < min_accuracy)
```

---

*Document Level: L300 — Implementation Specifications*
*References: L100 (cross-cutting patterns), L200-01/02/03 (component designs)*

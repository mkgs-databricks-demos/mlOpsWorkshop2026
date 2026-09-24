# L200-03 — `-monitors` Bundle: Quality Monitors, Dashboard & Retraining

**Classification:** Level 200 — Per-Component Detailed Design
**Bundle:** `mlops-workshop-monitors`
**Scope:** 3 quality monitors, serialized MLOps dashboard, retraining trigger job
**Cross-cutting patterns:** See L100 §3

---

## 1. Overview

The `-monitors` bundle deploys last because its resources require tables that only exist after the `-infra` and `-ai` bundles have run. It provides the observability and automation layer: quality monitors on predictions, features, and serving data; a serialized MLOps dashboard; and a retraining trigger job that closes the feedback loop.

**Deployment command:**
```bash
cd mlops-workshop-monitors
databricks bundle deploy -t dev
```

---

## 2. Dependencies

| Depends On | Provided By | Contract |
|------------|-------------|----------|
| `churn_predictions` table with data | `-infra` batch inference job | Table exists after training + inference run |
| Feature tables with data | Feature Views materialization | Tables exist after `materialize_features()` |
| `churn_serving_payload` table | `-ai` endpoint after first request | Table auto-created by AI Gateway |
| SQL warehouse | Customer workspace | `${var.warehouse_id}` for dashboard |

---

## 3. Quality Monitor Resources

### 3.1 Predictions Monitor (inference_log profile)

```yaml
quality_monitors:
  predictions_monitor:
    table_name: ${var.catalog}.${var.user_schema}.churn_predictions
    output_schema_name: ${var.catalog}.${var.user_schema}
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
```

**Output tables:**
- `churn_predictions_profile_metrics` — accuracy, F1, precision, recall, per-column stats
- `churn_predictions_drift_metrics` — KS test, PSI, Wasserstein distance, chi-squared

### 3.2 Features Monitor (time_series profile)

```yaml
quality_monitors:
  features_monitor:
    table_name: ${var.catalog}.${var.user_schema}.churn_features_avg_daily_sessions_30d
    output_schema_name: ${var.catalog}.${var.user_schema}
    time_series:
      granularities: ["1 day"]
      timestamp_col: window_end
    schedule:
      quartz_cron_expression: "0 0 9 * * ?"
      timezone_id: "UTC"
```

### 3.3 Serving Monitor (time_series profile)

```yaml
quality_monitors:
  serving_monitor:
    table_name: ${var.catalog}.${var.user_schema}.churn_serving_payload
    output_schema_name: ${var.catalog}.${var.user_schema}
    time_series:
      granularities: ["1 hour"]
      timestamp_col: timestamp_ms
    schedule:
      quartz_cron_expression: "0 */30 * * * ?"
      timezone_id: "UTC"
```

> **Why time_series for serving (not inference_log)?** The serving payload table has a Databricks-defined schema with JSON request/response columns — not the clean prediction_col/label_col structure that inference_log expects.

### 3.4 Monitor Summary

| Monitor | Profile | Table | Catches |
|---------|---------|-------|---------|
| `predictions_monitor` | `inference_log` | `churn_predictions` | Prediction drift, model accuracy, scoring input quality |
| `features_monitor` | `time_series` | Feature table(s) | Upstream feature distribution drift |
| `serving_monitor` | `time_series` | `churn_serving_payload` | Online request anomalies, volume, latency |

---

## 4. MLOps Dashboard

### 4.1 Design Decision: serialized_dashboard

The dashboard is defined as `serialized_dashboard` inline in the YAML — not as a `file_path` to a `.lvdash.json`. A `file_path` dashboard validates queries at deploy time, which fails because monitoring output tables don't exist yet. `serialized_dashboard` deploys without query validation — panels show empty until monitors populate the output tables.

### 4.2 Dashboard Pages

| Page | Dataset(s) | KPIs |
|------|-----------|------|
| **Model Accuracy Over Time** | `accuracy_over_time` | Accuracy, F1, precision, recall by model version |
| **Prediction & Feature Drift** | `prediction_drift`, `feature_drift_heatmap` | KS p-values, PSI, per-feature drift severity |
| **Data Quality & Volume** | `data_quality`, `volume_trend` | Null rates, distinct counts, prediction volume |
| **Serving Endpoint Health** | `serving_health` | Request volume, error rate, latency |

### 4.3 Parameterization

All dataset queries use `${var.catalog}.${var.user_schema}` — resolved at deploy time. Same dashboard works across participants and environments.

---

## 5. Retraining Trigger Job

### 5.1 Design

A scheduled job that queries monitoring output tables and kicks off the `-infra` training job when thresholds are breached.

> See docs/diagrams/04_retraining_loop.md

### 5.2 Task Graph

```
check_drift_metrics → should_retrain (condition) → trigger_retraining (run_job_task)
```

### 5.3 Thresholds

| Metric | Threshold | Source Table |
|--------|-----------|-------------|
| PSI | > 0.25 | `_drift_metrics` |
| Accuracy | < 0.70 | `_profile_metrics` |
| Consecutive drift days | ≥ 5 | `_drift_metrics` (last N windows) |

### 5.4 Anti-Pattern Protection

- Cooldown: no more than one automatic retraining per 24 hours
- Do not retrain when previous run is active
- Separate workflows: monitoring → retraining, model version → deployment, alias → verification

---

## 6. Non-Functional Requirements

| NFR | Target |
|-----|--------|
| Monitor refresh | Daily (predictions, features), every 30 min (serving) |
| Dashboard load | < 5 seconds |
| Retraining trigger | Daily check at 3 PM UTC |
| Alert delivery | Email on retraining trigger failure |

---

## 7. Testing

| Test | What | How |
|------|------|-----|
| Monitor creation | Monitors exist | `GET /api/2.1/unity-catalog/tables/{table}/monitor` |
| Output tables | Profile + drift tables created after first refresh | `SELECT COUNT(*) FROM _profile_metrics` |
| Dashboard | Dashboard renders | Open in workspace UI |
| Retraining trigger | Job fires correctly | Simulate drift by writing skewed predictions |

---

*Document Level: L200 — Per-Component Detailed Design*
*Bundle: mlops-workshop-monitors*
*References: L100 §3.6 (observability), L100 §3.7 (retraining automation)*

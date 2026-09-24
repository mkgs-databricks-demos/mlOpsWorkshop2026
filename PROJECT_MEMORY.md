# PROJECT_MEMORY.md — mlOpsWorkshop2026

**Repo:** `mlOpsWorkshop2026`
**Purpose:** One-day hands-on MLOps workshop curriculum using Declarative Automation Bundles
**Use case:** Customer churn prediction (domain-agnostic code, Rx Rebate leakage verbal overlay)
**Customer context:** Healthcare / Rx Rebates, pre-sales engagement
**License:** MIT — MKG Solutions Databricks Demos

---

## Architecture

### Three-Bundle Deployment Model

| Order | Bundle | Deploys | Depends On |
|-------|--------|---------|------------|
| 1 | `mlops-workshop-infra` | UC schema, volume, experiment, registered model, 4 jobs (ingestion, training+promotion, MLflow 3 deployment, batch inference) | Customer catalog with USE CATALOG + CREATE SCHEMA |
| 2 | `mlops-workshop-ai` | Model Serving endpoint + AI Gateway inference table | `-infra` deployed + >=1 model version |
| 3 | `mlops-workshop-monitors` | 3 quality monitors, serialized dashboard, retraining trigger job | `-infra` batch inference has run (tables have data) |

### 14 Resources Total

| Resource | Bundle | Key |
|----------|--------|-----|
| Workshop schema | `-infra` | `workshop_schema` |
| Landing volume | `-infra` | `landing_volume` |
| MLflow experiment | `-infra` | `churn_experiment` |
| Registered model | `-infra` | `churn_model` |
| Data ingestion job | `-infra` | `data_ingestion` |
| Training + promotion job | `-infra` | `churn_model_training` |
| MLflow 3 deployment job | `-infra` | `churn_deployment_job` |
| Batch inference job | `-infra` | `churn_batch_inference` |
| Model Serving endpoint | `-ai` | `churn_serving` |
| Predictions monitor | `-monitors` | `predictions_monitor` |
| Features monitor | `-monitors` | `features_monitor` |
| Serving monitor | `-monitors` | `serving_monitor` |
| MLOps dashboard | `-monitors` | `mlops_dashboard` |
| Retraining trigger job | `-monitors` | `churn_retraining_trigger` |

---

## Key Technical Decisions

* **All serverless compute** — no ML Runtime required. Feature Views, scikit-learn, XGBoost, MLflow all install via `%pip install`.
* **VARIANT-first bronze** — `parse_json()` + VARIANT path notation. Never `spark.read.json()` with schema inference.
* **Dual-path ingestion** — `use_zerobus` variable gates ZeroBus API vs Auto Loader. Silver reads from `bronze_unified` (UNION ALL) — downstream is path-agnostic.
* **Champion/Challenger aliases** — `Champion`, `Challenger`, `PreviousChampion`. Promotion criteria: F1 > 0.75, AUC within 0.005 of champion. First model auto-promotes.
* **Feature Views (declarative)** — `databricks-feature-engineering>=0.16.0`. Eliminates training-serving skew.
* **Serialized dashboard** — inline in YAML (not `file_path`), deploys without query validation.
* **Per-participant isolation** — schema `user_${bundle.user_name}` per participant.
* **Resource references only** — `${resources.<type>.<name>.<field>}` within bundles, `${var.<name>}` cross-bundle. No hard-coded names.

---

## Conventions

* Notebook paths: `.ipynb` default, `.sql` only with `warehouse_id`.
* Schema refs: `${resources.schemas.workshop_schema.*}` in resource definitions.
* All notebooks receive parameters via `base_parameters`, read via `dbutils.widgets.get()`.
* Retraining anti-pattern: never create loops where alias changes trigger retraining. 24h cooldown.

---

## Notebooks (14 total)

| Notebook | Parameters | Outputs |
|----------|-----------|--------|
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

## Silver Tables

| Table | Key | Grain | Source `record_type` |
|-------|-----|-------|---------------------|
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

## CI/CD

* GitHub Actions three-stage deploy: `test-and-validate` -> `deploy-infra` -> `deploy-ai` -> `deploy-monitors`
* Environment matrix: dev / staging / prod with catalog + schema + use_zerobus overrides

---

## Workshop Delivery

* 7 modules, 09:00-17:00, solo instructor
* Rx Rebates narrative overlay (see `docs/design/instructor-delivery-guide.md`)
* 10 diagrams: 6 platform architecture + 4 Rx domain (HTML in `docs/diagrams/html/`)

---

## Workspace

* **Host:** `https://fevm-hls-fde.cloud.databricks.com`
* **Targets:** dev (default, `mode: development`) / prod (`mode: production`, `run_as: matthew.giglia@databricks.com`)
* **All bundles** include `resources/*.yml` and `resources/*/*.yml`
* **Catalog:** TBD — design defaults to `mlops_workshop`, needs to be wired into variables

---

## Implementation Status

**Design docs: COMPLETE.** All L100/L200/L300 specs and instructor guide written.

**Bundle scaffolding: CREATED.** Three bundle directories exist with boilerplate `databricks.yml`, `.gitignore`, and template READMEs. No `resources/`, `src/`, or `tests/` directories yet.

**Source code: NOT STARTED.** Resource YAML, notebooks, and tests still need to be authored per L300 specs.

---

## Open Questions

- [ ] Protobuf ZeroBus ingestion in addition to JSON?
- [ ] Human-in-the-loop approval in deployment job for workshop?
- [ ] SDP-based silver flattening as advanced module?

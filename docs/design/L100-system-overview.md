# L100 — MLOps Workshop: System-Level Overview

**Project:** MLOps Workshop — Reusable One-Day Curriculum
**Prepared for:** Instructors, Field Engineers, Solution Architects
**Classification:** Level 100 — System Overview / Constitution

---

## 1. Mission

Deliver a **one-day, hands-on MLOps workshop** that teaches customers the modern Databricks ML lifecycle — from data ingestion through model monitoring — using Declarative Automation Bundles as the infrastructure-as-code foundation. The workshop is a **reusable reference architecture**: if it's worth building for one customer, it's worth building for all.

**Use case:** Customer churn prediction — universally relatable, covers every MLOps stage.

---

## 2. Architecture Overview

### Three-Bundle Deployment Model

| Bundle | Name | Deploys | Depends On |
|--------|------|---------|------------|
| **1** | `mlops-workshop-infra` | UC schema, volume, experiment, registered model, SDP ingestion pipeline, data prep job, training + promotion job, MLflow 3 deployment job, batch inference job | Customer catalog with USE CATALOG + CREATE SCHEMA |
| **2** | `mlops-workshop-ai` | Model Serving endpoint with AI Gateway inference table logging | `-infra` deployed + ≥1 model version exists |
| **3** | `mlops-workshop-monitors` | 3 quality monitors, serialized MLOps dashboard, retraining trigger job | `-infra` batch inference has run (tables have data) |

### Deployment Sequence

```
-infra (deploy)
    → data_ingestion (run)  ← lands data + triggers SDP pipeline
    → churn_model_training (run)
-ai (deploy)
    → send test requests
-monitors (deploy)
```

> See docs/diagrams/01_three_bundle_deployment.md

---

## 3. Cross-Cutting Patterns

These patterns apply to ALL bundles and ALL code. L200 components reference this section.

### 3.1 Resource Reference Pattern

**Rule:** Every parameter that touches a catalog, schema, experiment, model, or volume name MUST use `${resources.<type>.<name>.<field>}` within a bundle, or `${var.<name>}` for cross-bundle references. Never hard-code names.

| Context | Pattern | Example |
|---------|---------|---------|
| Same bundle | `${resources.schemas.workshop_schema.catalog_name}` | Catalog from schema resource |
| Same bundle | `${resources.registered_models.churn_model.name}` | Model name |
| Same bundle | `${resources.volumes.landing_volume.name}` | Volume name |
| Cross-bundle | `${var.registered_model_name}` | Variable matching -infra output |
| Notebook params | `dbutils.widgets.get("model_name")` | Bundle-injected via base_parameters |

### 3.2 Catalog & Schema Model

- **Single customer-provided catalog** with USE CATALOG + CREATE SCHEMA grants
- **Per-participant schema** created as a bundle resource: `user_${bundle.user_name}`
- All tables, features, models, and volumes live within the participant's schema
- **Production recommendation:** separate catalogs per environment (dev/staging/prod)

### 3.3 Dual-Path Ingestion (SDP Pipeline)

Data ingestion uses a **Spark Declarative Pipeline** (SDP) for bronze → silver processing. A separate data prep job generates synthetic data and lands it; the job's final task triggers the pipeline.

| Path | Gate | SDP Streaming Table | When Used |
|------|------|---------------------|-----------|
| **ZeroBus API** | `use_zerobus=true` | `bronze_zerobus` | Production / ZeroBus-enabled workspaces |
| **Auto Loader** | `use_zerobus=false` (default) | `bronze_autoload` | Workshop default / file-based ingestion |

The pipeline declares both bronze streaming tables — whichever path has data flows through. `bronze_unified` (temporary view, UNION ALL) feeds five silver streaming tables with `parse_json()` extraction and data quality expectations. Downstream is path-agnostic.

### 3.4 VARIANT-First Data Pattern

- **Bronze:** `payload` column is a JSON STRING
- **Silver:** `parse_json(payload)` + VARIANT path notation for extraction
- **Never** use `spark.read.json()` with schema inference or struct-based approaches
- VARIANT preserves the full JSON tree, handles schema evolution

### 3.5 Champion/Challenger Model Lifecycle

| Alias | Purpose |
|-------|---------|
| `Champion` | Model version currently serving production traffic |
| `Challenger` | Candidate model being evaluated |
| `PreviousChampion` | Rollback target |

**Flow:** Train → Validate (assign Challenger + tags) → Compare vs Champion → Promote (or reject) → Batch inference loads `@Champion`

**Tags:** `validation_status: PENDING → PASSED/FAILED`, `promotion_status: CHAMPION/REJECTED`

### 3.6 Observability Standards

| Layer | Tool | What's Tracked |
|-------|------|----------------|
| Data quality | Quality monitors | Null rates, schema changes, freshness, volume |
| Feature drift | Quality monitors (time_series) | Distribution changes in input features |
| Prediction drift | Quality monitors (inference_log) | KS test, PSI, Wasserstein distance |
| Model quality | Quality monitors (inference_log) | Accuracy, F1, AUC by model version |
| Serving health | Quality monitors (time_series on payload) | Request volume, error rate, latency |
| MLOps dashboard | Serialized AI/BI dashboard | All of the above in one pane |

### 3.7 Retraining Automation

| Trigger | Mechanism |
|---------|-----------|
| Scheduled | Cron on training job |
| Drift-driven | Monitor drift_metrics → retraining trigger job → run_job_task |
| Performance-driven | Monitor profile_metrics → accuracy threshold → run_job_task |
| Model-version-driven | MLflow 3 deployment job auto-triggers on MODEL_VERSION_READY |

**Anti-pattern:** Never create a loop where alias changes trigger retraining.

---

## 4. Component Inventory

| Component | Bundle | Resource Type | Resource Key |
|-----------|--------|---------------|--------------|
| Workshop schema | `-infra` | `schemas` | `workshop_schema` |
| Landing volume | `-infra` | `volumes` | `landing_volume` |
| MLflow experiment | `-infra` | `experiments` | `churn_experiment` |
| Registered model | `-infra` | `registered_models` | `churn_model` |
| Data ingestion pipeline | `-infra` | `pipelines` | `data_ingestion_pipeline` |
| Data prep job | `-infra` | `jobs` | `data_ingestion` |
| Training + promotion job | `-infra` | `jobs` | `churn_model_training` |
| MLflow 3 deployment job | `-infra` | `jobs` | `churn_deployment_job` |
| Batch inference job | `-infra` | `jobs` | `churn_batch_inference` |
| Model Serving endpoint | `-ai` | `model_serving_endpoints` | `churn_serving` |
| Predictions monitor | `-monitors` | `quality_monitors` | `predictions_monitor` |
| Features monitor | `-monitors` | `quality_monitors` | `features_monitor` |
| Serving monitor | `-monitors` | `quality_monitors` | `serving_monitor` |
| MLOps dashboard | `-monitors` | `dashboards` | `mlops_dashboard` |
| Retraining trigger job | `-monitors` | `jobs` | `churn_retraining_trigger` |

---

## 5. Interface Contracts

### Bundle → Bundle

| Producer | Consumer | Contract |
|----------|----------|----------|
| `-infra` schema | `-ai`, `-monitors` | `${var.catalog}` + `${var.user_schema}` must match |
| `-infra` registered model | `-ai` endpoint | `${var.registered_model_name}` = `catalog.schema.churn_model` |
| `-infra` training job | `-ai` endpoint | ≥1 model version must exist before `-ai` deploy |
| `-infra` batch inference | `-monitors` monitors | `churn_predictions` table must exist with data |
| `-ai` endpoint | `-monitors` serving monitor | `churn_serving_payload` auto-created after first request |

### Notebook → Bundle

All notebooks receive parameters via `base_parameters`. Notebooks read via `dbutils.widgets.get()`. No notebook ever hard-codes a catalog, schema, model, or experiment name.

---

## 6. Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| IaC | Declarative Automation Bundles | Databricks-native, source-controlled, CI/CD-ready |
| Feature engineering | Feature Views (declarative) | Databricks-managed, eliminates training-serving skew |
| Model registry | UC registered models | Governance, lineage, cross-workspace discovery |
| Model lifecycle | Aliases (Champion/Challenger) | Mutable pointers, not deprecated stages |
| Deployment automation | MLflow 3 deployment jobs | Auto-triggers on new model version |
| Monitoring | Quality monitors (bundle resource) | Declarative, version-controlled |
| Dashboard | Serialized inline | Deploys without query validation, parameterized |
| Ingestion | SDP pipeline (ZeroBus + Auto Loader dual-path) | Streaming tables for bronze + silver; `use_zerobus` gates data landing; pipeline processes both |
| Bronze pattern | VARIANT via parse_json() | Schema-as-contract, no schema inference |

---

## 7. Repo Structure

```
mlops-workshop/
├── mlops-workshop-infra/
│   ├── databricks.yml
│   ├── resources/
│   │   ├── schema.yml
│   │   ├── experiment.yml
│   │   ├── registered_model.yml
│   │   ├── data_ingestion_pipeline.yml  # SDP pipeline resource
│   │   ├── data_ingestion_job.yml       # Data prep + pipeline trigger
│   │   ├── training_job.yml
│   │   ├── deployment_job.yml
│   │   └── batch_inference_job.yml
│   ├── src/
│   │   ├── pipeline/
│   │   │   └── ingestion/               # SDP pipeline notebooks
│   │   │       ├── bronze_autoload.py
│   │   │       ├── bronze_zerobus.py
│   │   │       ├── bronze_unified.py
│   │   │       └── silver_tables.py
│   │   ├── data/
│   │   │   ├── generate_ndjson.py
│   │   │   ├── post_to_zerobus.py
│   │   │   └── write_to_volume.py
│   │   ├── features/
│   │   │   └── feature_definitions.py
│   │   ├── train/
│   │   │   └── train.py
│   │   ├── validate/
│   │   │   └── validate.py
│   │   ├── promote/
│   │   │   └── promote.py
│   │   ├── deploy/
│   │   │   ├── evaluate.py
│   │   │   └── promote_champion.py
│   │   └── inference/
│   │       └── batch_predict.py
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   └── notebooks/
│       └── exploration/
│
├── mlops-workshop-ai/
│   ├── databricks.yml
│   └── resources/
│       └── serving_endpoint.yml
│
├── mlops-workshop-monitors/
│   ├── databricks.yml
│   └── resources/
│       ├── predictions_monitor.yml
│       ├── features_monitor.yml
│       ├── serving_monitor.yml
│       ├── mlops_dashboard.yml
│       └── retraining_trigger_job.yml
│
├── docs/
│   ├── design/
│   │   ├── L100-system-overview.md
│   │   ├── L200-01-infra-bundle.md
│   │   ├── L200-02-ai-bundle.md
│   │   ├── L200-03-monitors-bundle.md
│   │   └── L300-implementation-specs.md
│   └── diagrams/
│       ├── 01_three_bundle_deployment.md
│       ├── 02_data_ingestion_flow.md
│       ├── 03_champion_challenger_flow.md
│       └── 04_retraining_loop.md
│
└── README.md
```

---

## 8. Compute Requirements

**All serverless compute -- no ML Runtime required.** Feature Views, scikit-learn, XGBoost, and MLflow all install cleanly on serverless via `%pip install`. The only workloads that require ML Runtime are GPU-based deep learning (not in scope for this workshop). Use the **latest serverless environment version** for all notebooks and jobs.

| Component | Compute | Why Serverless Works |
|-----------|---------|---------------------|
| Feature Views | Serverless | `databricks-feature-engineering>=0.16.0` installs via pip |
| Model training (scikit-learn/XGBoost) | Serverless | Standard pip packages, no GPU needed |
| MLflow tracking + registration | Serverless | Built into the platform |
| Batch inference | Serverless | `fe.score_batch()` runs on Spark |
| Data ingestion (SDP pipeline) | Serverless | SDP serverless with Photon; Auto Loader + streaming tables |
| ZeroBus SDK | Serverless | Pure Python SDK, no cluster dependency |

## 9. Prerequisites

- Customer-provided catalog with USE CATALOG + CREATE SCHEMA grants
- Databricks CLI installed on participant machines
- Service principal for CI/CD demos
- ZeroBus endpoint (optional -- Auto Loader is the default)
- Feature Views (Public Preview) enabled
- Lakehouse Monitoring enabled
- Model Serving available

## 10. Customer Context: Healthcare / Rx Rebates

This workshop is designed for **pre-sales delivery to healthcare customers**, specifically framed around **Rx Rebate leakage prediction**. The code is domain-agnostic (customer churn), but the verbal narrative maps every concept to the Rx Rebates domain:

| Workshop Concept | Rx Rebates Translation |
|---|---|
| Customer = `customer_id` | Drug manufacturer or PBM contract |
| Churn = `churned` | Rebate leakage (contract underperformance) |
| Usage events | Claim volume, formulary utilization, market share |
| Billing history | Rebate payments, invoice amounts, true-up adjustments |
| Support interactions | Dispute tickets, audit findings, contract amendments |
| Champion model | Current rebate leakage predictor in production |
| Drift detection | Formulary changes, new generics, seasonal patterns |

For the full delivery playbook, see `docs/design/instructor-delivery-guide.md`.

## Related Documents

| Document | Purpose |
|----------|---------|
| L200-01-infra-bundle.md | -infra bundle detailed design |
| L200-02-ai-bundle.md | -ai bundle detailed design |
| L200-03-monitors-bundle.md | -monitors bundle detailed design |
| L300-implementation-specs.md | Complete YAML, schemas, notebook contracts |
| instructor-delivery-guide.md | Module-by-module teaching playbook |
| docs/diagrams/*.html | Interactive architecture diagrams |

*Document Level: L100 -- System Overview / Constitution*
*All L200 and L300 documents reference this document for cross-cutting patterns.*

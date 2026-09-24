# MLOps Workshop 2026

**Databricks MLOps Workshop — Reusable One-Day Curriculum**

A hands-on workshop teaching the modern Databricks ML lifecycle — from data ingestion through model monitoring — using Declarative Automation Bundles as the infrastructure-as-code foundation.

**Use case:** Customer churn prediction (universally relatable, covers every MLOps stage).

## Architecture

Three bundles deployed in sequence:

```
mlops-workshop-infra  →  mlops-workshop-ai  →  mlops-workshop-monitors
       (deploy)               (deploy)               (deploy)
   SDP pipeline            serving endpoint        quality monitors
   data prep job           AI Gateway              MLOps dashboard
   model training          inference table         retraining trigger
   batch inference
```

| Bundle | What It Deploys |
|--------|-----------------|
| **`-infra`** | UC schema, volume, experiment, registered model, SDP ingestion pipeline, data prep job, training + promotion job, MLflow 3 deployment job, batch inference job |
| **`-ai`** | Model Serving endpoint with AI Gateway inference table logging |
| **`-monitors`** | 3 quality monitors, serialized MLOps dashboard, retraining trigger job |

## Key Patterns

* **All serverless compute** — no ML Runtime required
* **VARIANT-first bronze** — `parse_json()`, no schema inference
* **SDP ingestion pipeline** — streaming tables for bronze → silver; dual-path data landing (ZeroBus or Auto Loader) gated by `use_zerobus`
* **Champion/Challenger aliases** — governed promotion with validation gates
* **Feature Views** — declarative, eliminates training-serving skew
* **Per-participant isolation** — `user_${bundle.user_name}` schemas

## Repo Structure

```
mlOpsWorkshop2026/
├── mlops-workshop-infra/           # Bundle 1: UC resources + jobs
│   ├── databricks.yml              # Variables: catalog, user_schema, use_zerobus
│   ├── resources/
│   │   ├── schema.yml                   # UC schema + landing volume
│   │   ├── experiment.yml               # MLflow experiment
│   │   ├── registered_model.yml         # UC registered model
│   │   ├── data_ingestion_pipeline.yml  # SDP pipeline: bronze → silver
│   │   ├── data_ingestion_job.yml       # Data prep + pipeline trigger
│   │   ├── training_job.yml             # 6-task training + promotion
│   │   ├── deployment_job.yml           # MLflow 3 auto-trigger
│   │   └── batch_inference_job.yml      # Standalone @Champion scoring
│   └── src/                             # Pipeline + job notebooks
├── mlops-workshop-ai/              # Bundle 2: serving endpoint
│   ├── databricks.yml              # Variables: catalog, user_schema, registered_model_name
│   └── resources/
│       └── serving_endpoint.yml    # Model Serving + AI Gateway
├── mlops-workshop-monitors/        # Bundle 3: monitors + dashboard
│   ├── databricks.yml              # Variables: catalog, user_schema, warehouse_id, training_job_id
│   ├── resources/
│   │   ├── predictions_monitor.yml     # inference_log on churn_predictions
│   │   ├── features_monitor.yml        # time_series on Feature View
│   │   ├── serving_monitor.yml         # time_series on serving payload
│   │   ├── mlops_dashboard.yml         # serialized 4-page MLOps dashboard
│   │   └── retraining_trigger_job.yml  # drift-driven retraining loop
│   └── src/                        # (next) check_metrics.ipynb
├── docs/
│   ├── design/                     # L100/L200/L300 design docs
│   └── diagrams/                   # Mermaid sources + rendered HTML
├── PROJECT_MEMORY.md
├── README.md
└── LICENSE
```

## Quick Start

```bash
# 0. Validate all bundles
for bundle in mlops-workshop-infra mlops-workshop-ai mlops-workshop-monitors; do
  (cd $bundle && databricks bundle validate --target dev)
done

# 1. Deploy infrastructure
cd mlops-workshop-infra
databricks bundle deploy --target dev

# 2. Run data prep (generates data + triggers SDP pipeline)
databricks bundle run --target dev data_ingestion
databricks bundle run --target dev churn_model_training

# 3. Deploy serving endpoint (requires >=1 model version)
cd ../mlops-workshop-ai
databricks bundle deploy --target dev

# 4. Send a test request to populate inference table
# (churn_serving_payload must exist before monitors deploy)

# 5. Deploy monitoring
cd ../mlops-workshop-monitors
databricks bundle deploy --target dev
```

## Prerequisites

* Customer-provided catalog with `USE CATALOG` + `CREATE SCHEMA` grants
* Databricks CLI installed
* Service principal for CI/CD demos
* Feature Views enabled (Public Preview)
* Lakehouse Monitoring enabled
* Model Serving available

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/design/L100-system-overview.md` | System overview — architecture, cross-cutting patterns, component inventory |
| `docs/design/L200-01-infra-bundle.md` | `-infra` bundle detailed design |
| `docs/design/L200-02-ai-bundle.md` | `-ai` bundle detailed design |
| `docs/design/L200-03-monitors-bundle.md` | `-monitors` bundle detailed design |
| `docs/design/L300-implementation-specs.md` | Complete YAML, schemas, notebook contracts, CI/CD |
| `docs/design/instructor-delivery-guide.md` | Module-by-module teaching playbook |
| `docs/diagrams/html/` | Interactive architecture diagrams (10 total) |

## Workshop Modules

| Time | Module | Focus |
|------|--------|-------|
| 09:00–09:45 | Set the Stage | MLOps pillars, failure modes |
| 09:45–10:30 | Bundles + Ingestion | Deploy `-infra`, run data pipeline |
| 10:45–12:00 | Feature Views | Define, compute, register features |
| 13:00–14:00 | Training + Promotion | Champion/Challenger lifecycle |
| 14:00–15:00 | CI/CD | GitHub Actions, deployment job |
| 15:15–16:00 | Deployment | `-ai` bundle, serving endpoint |
| 16:00–16:45 | Monitoring | `-monitors` bundle, dashboard, retraining |

## Implementation Status

| Component | Status |
|-----------|--------|
| Design docs (L100/L200/L300) | Complete |
| `-infra` bundle resource YAML | Complete |
| `-ai` bundle resource YAML | Complete |
| `-monitors` bundle resource YAML | Complete |
| Source notebooks (14 total) | Not started |
| Dashboard widget layout | Not started |
| Unit tests | Not started |

Active branch: `mg-genie-infra-bundle-resources`

## License

MIT — see [LICENSE](LICENSE).

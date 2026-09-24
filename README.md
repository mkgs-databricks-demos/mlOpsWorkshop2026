# MLOps Workshop 2026

**Databricks MLOps Workshop — Reusable One-Day Curriculum**

A hands-on workshop teaching the modern Databricks ML lifecycle — from data ingestion through model monitoring — using Declarative Automation Bundles as the infrastructure-as-code foundation.

**Use case:** Customer churn prediction (universally relatable, covers every MLOps stage).

## Architecture

Three bundles deployed in sequence:

```
mlops-workshop-infra  →  mlops-workshop-ai  →  mlops-workshop-monitors
       (deploy)               (deploy)               (deploy)
   data ingestion          serving endpoint        quality monitors
   model training          AI Gateway              MLOps dashboard
   batch inference         inference table         retraining trigger
```

| Bundle | What It Deploys |
|--------|-----------------|
| **`-infra`** | UC schema, volume, experiment, registered model, data ingestion job, training + promotion job, MLflow 3 deployment job, batch inference job |
| **`-ai`** | Model Serving endpoint with AI Gateway inference table logging |
| **`-monitors`** | 3 quality monitors, serialized MLOps dashboard, retraining trigger job |

## Key Patterns

* **All serverless compute** — no ML Runtime required
* **VARIANT-first bronze** — `parse_json()`, no schema inference
* **Dual-path ingestion** — ZeroBus API or Auto Loader, gated by `use_zerobus` variable
* **Champion/Challenger aliases** — governed promotion with validation gates
* **Feature Views** — declarative, eliminates training-serving skew
* **Per-participant isolation** — `user_${bundle.user_name}` schemas

## Repo Structure

```
mlOpsWorkshop2026/
├── mlops-workshop-infra/      # Bundle 1: UC resources + jobs
│   ├── databricks.yml
│   ├── resources/               # (planned) resource YAML
│   └── src/                     # (planned) notebooks
├── mlops-workshop-ai/         # Bundle 2: serving endpoint
│   ├── databricks.yml
│   └── resources/               # (planned) resource YAML
├── mlops-workshop-monitors/   # Bundle 3: monitors + dashboard
│   ├── databricks.yml
│   └── resources/               # (planned) resource YAML
├── docs/
│   ├── design/                  # L100/L200/L300 design docs
│   └── diagrams/                # Mermaid sources + rendered HTML
├── PROJECT_MEMORY.md
├── README.md
└── LICENSE
```

## Quick Start

```bash
# 1. Deploy infrastructure
cd mlops-workshop-infra
databricks bundle deploy -t dev

# 2. Run data ingestion + training
databricks bundle run -t dev data_ingestion
databricks bundle run -t dev churn_model_training

# 3. Deploy serving endpoint
cd ../mlops-workshop-ai
databricks bundle deploy -t dev

# 4. Deploy monitoring
cd ../mlops-workshop-monitors
databricks bundle deploy -t dev
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

## License

MIT — see [LICENSE](LICENSE).

# mlops-workshop-infra

**Bundle 1 of 3** — Infrastructure, data, training & promotion for the MLOps Workshop.

Deploys foundational Unity Catalog resources and all ML lifecycle jobs: data ingestion (dual-path), model training with Feature Views, champion/challenger promotion, MLflow 3 deployment automation, and batch inference.

## Resources Deployed

| Resource | Key | Description |
|----------|-----|-------------|
| UC Schema | `workshop_schema` | Per-participant isolated schema |
| UC Volume | `landing_volume` | NDJSON landing zone for Auto Loader |
| MLflow Experiment | `churn_experiment` | Churn prediction experiment |
| Registered Model | `churn_model` | UC-registered model with alias lifecycle |
| Data Ingestion Job | `data_ingestion` | Dual-path: ZeroBus or Auto Loader → bronze → silver |
| Training Job | `churn_model_training` | Train → validate → promote → batch inference |
| Deployment Job | `churn_deployment_job` | MLflow 3 auto-trigger on MODEL_VERSION_READY |
| Batch Inference Job | `churn_batch_inference` | Standalone @Champion scoring |

## Variables

| Variable | Description | Default |
|----------|-------------|--------|
| `catalog` | Customer-provided Unity Catalog | `mlops_workshop` |
| `user_schema` | Per-participant schema name | *(set per target)* |
| `use_zerobus` | Route data through ZeroBus API | `"false"` |

## Quick Start

```bash
# Validate
databricks bundle validate --target dev

# Deploy infrastructure
databricks bundle deploy --target dev

# Run data pipeline
databricks bundle run --target dev data_ingestion

# Train model
databricks bundle run --target dev churn_model_training

# Run batch inference
databricks bundle run --target dev churn_batch_inference
```

## Targets

| Target | Mode | Schema Pattern |
|--------|------|---------------|
| `dev` | development | `user_<short_name>` |
| `prod` | production | `mlops_prod` |

## Project Structure

```
mlops-workshop-infra/
├── databricks.yml
├── resources/
│   ├── schema.yml              # UC schema + volume
│   ├── experiment.yml          # MLflow experiment
│   ├── registered_model.yml    # UC registered model
│   ├── data_ingestion_job.yml  # 7-task dual-path ingestion
│   ├── training_job.yml        # 6-task training + promotion
│   ├── deployment_job.yml      # 3-task MLflow 3 deployment
│   └── batch_inference_job.yml # Standalone batch inference
├── src/
│   ├── data/                   # Data pipeline notebooks
│   ├── train/                  # Feature definitions + training
│   ├── validate/               # Model validation
│   ├── promote/                # Champion/Challenger promotion
│   ├── deploy/                 # MLflow 3 deployment
│   └── inference/              # Batch prediction
├── fixtures/
│   ├── eda_churn_exploration   # 30-cell EDA notebook (correlation, VIF, distributions)
│   └── sessions/               # Session summaries
├── docs/
│   └── design/                 # Implementation plan + feature engineering design
├── PROJECT_MEMORY.md
└── README.md
```

## Prerequisites

* Customer-provided catalog with `USE CATALOG` + `CREATE SCHEMA` grants
* Databricks CLI installed
* ZeroBus endpoint configured (optional — only if `use_zerobus=true`)

## Deploy Order

This bundle deploys **first**. Downstream bundles depend on it:

```
mlops-workshop-infra → mlops-workshop-ai → mlops-workshop-monitors
```

## Documentation

* [Feature Engineering Design](docs/design/feature-engineering-design.md) — EDA findings, collinearity analysis, feature specifications
* [Implementation Plan](docs/design/implementation-plan.md) — phased build plan with notebook contracts
* [L200 Design](../../docs/design/L200-01-infra-bundle.md) — component-level design
* [L300 Specs](../../docs/design/L300-implementation-specs.md) — complete implementation specifications
* [Declarative Automation Bundles in the workspace](https://docs.databricks.com/aws/en/dev-tools/bundles/workspace-bundles)
* [Declarative Automation Bundles Configuration reference](https://docs.databricks.com/aws/en/dev-tools/bundles/reference)

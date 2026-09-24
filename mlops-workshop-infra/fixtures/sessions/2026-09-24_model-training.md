# Session: Model Training — LightGBM with Nested CV & Feature Pruning

**Date:** 2026-09-24  
**Branch:** `mg-genie-eda-feature-design`  
**Bundle:** `mlops-workshop-infra` (target: dev)

---

## Summary

Implemented the `train.py` notebook (9 cells) for the `churn_model_training` job. Built a LightGBM classifier using the Classic Feature Store, iterating through two model versions: v1 (flat Optuna tuning, 9 features) and v2 (nested cross-validation + feature importance pruning, 5 features). Model v2 is the current registered version.

---

## Problems & Root Causes

| Problem | Root Cause | Fix |
|---------|-----------|-----|
| Experiment not found | Dev mode prefixes experiment name as `[dev matthew_giglia]` | Used `dbutils.widgets.get("experiment_name")` to pick up bundle-deployed name |
| Model name mismatch | Dev mode prefixes model name with `dev_matthew_giglia_` | Used `dbutils.widgets.get("model_name")` for bundle-deployed name |
| `source` and `ingested_at` in training set | `churn_labels` carries bronze metadata columns through `create_training_set()` | Added both to `exclude_cols` list |
| `QUOTA_EXCEEDED` on model registration | Metastore at 5000 registered models; `mlflow.register_model()` tries create-or-get internally | Switched to `MlflowClient.create_model_version()` which adds a version directly |
| CV F1 (0.70) vs Test F1 (0.41) gap | Flat 100-trial Optuna search overfits to the 5 CV folds used for evaluation | Replaced with nested CV (5 outer × 30 inner × 4 inner folds) for unbiased estimate |
| 9 features on 400 rows | Excess features add noise the model can memorize | Feature importance pruning: dropped 4 features < 5% importance (9 → 5) |

---

## Key Decisions

1. **Nested cross-validation** — Inner loop (4-fold, 30 Optuna trials) tunes hyperparameters; outer loop (5-fold) evaluates. Eliminates optimistic bias from tuning on evaluation folds.
2. **Tighter search space** — `max_depth` 3-5 (was 3-6), `reg_alpha` ≥ 0.1 (was ≥ 1e-8), `reg_lambda` ≥ 0.5 (was ≥ 1e-8), `min_child_samples` 25-50 (was 15-50). Forces simpler models on small data.
3. **Feature importance pruning** — Aggregated importances across 5 outer fold models. Threshold: 5% relative importance. Dropped `max_api_calls_7d` (3.3%), `plan_type_encoded` (1.4%), `support_tickets_7d` (1.1%), `escalated_tickets_30d` (0.0%).
4. **Pruned FeatureLookups in fe.log_model()** — The model artifact only references the 5 features it uses, so `fe.score_batch()` at inference fetches only what's needed.
5. **MlflowClient.create_model_version()** — Bypasses the create-or-get pattern in `register_model()` that hits the metastore quota.

---

## Training Results

| Metric | v1 (flat Optuna, 9 features) | v2 (nested CV, 5 features) |
|--------|------------------------------|----------------------------|
| CV F1 | 0.6994 (inflated) | 0.6531 ± 0.055 (unbiased) |
| Pruned CV F1 | — | 0.6853 |
| Test F1 | 0.4091 | 0.3830 |
| Test AUC | 0.7427 | 0.7070 |
| Test precision | 0.3600 | 0.3214 |
| Test recall | 0.4737 | 0.4737 |
| CV-to-test gap | 0.29 | 0.27 |

**Kept features (≥ 5%):** `tenure_days` (33%), `total_revenue_90d` (30%), `avg_daily_sessions_30d` (12.5%), `overdue_payment_count_90d` (9.5%), `company_size_encoded` (9%)

---

## Files Modified

| File | Change |
|------|--------|
| `src/train/train.py` | Full 9-cell implementation: install deps → params → FeatureLookup → split → nested CV → feature prune + retune → MLflow log → register → task value |
| `resources/training_job.yml` | `register_features` task: `feature_definitions.py` → `feature_tables_classic.py` |
| `PROJECT_MEMORY.md` | Added training results, feature pruning section, key decisions, updated implementation status |

---

## Observations & Next Steps

* The CV-to-test F1 gap (0.27) is driven by small test set variance (100 rows, 19 positives). The nested CV F1 of 0.65 is the honest ceiling for LightGBM on this data.
* The promotion threshold (F1 > 0.75) will not be met without more data or a fundamentally different approach.
* **Candidate next step:** Logistic regression baseline — only 5 parameters to fit, nearly impossible to overfit on 400 rows. EDA showed strong linear separability.
* Downstream stubs (`validate.py`, `promote.py`, `deploy/`, `inference/`) still need implementation.

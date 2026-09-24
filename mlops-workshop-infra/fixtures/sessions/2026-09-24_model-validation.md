# Session: Model Validation — Challenger Gate

**Date:** 2026-09-24  
**Branch:** `mg-genie-eda-feature-design`  
**Bundle:** `mlops-workshop-infra` (target: dev)

---

## Summary

Implemented the `validate.py` notebook (8 cells) for the `model_validation` task in the `churn_model_training` job. Validates newly trained model versions against minimum quality thresholds, runs an end-to-end smoke test, and assigns the Challenger alias if all checks pass. Outputs `validation_passed` task value for the downstream condition gate.

---

## Validation Checks

### Metric Thresholds (sanity gates)

| Check | Threshold | v2 Actual | Result |
|------|-----------|-----------|--------|
| `test_f1` | ≥ 0.30 | 0.3830 | PASS |
| `test_auc` | ≥ 0.60 | 0.7070 | PASS |
| `test_precision` | ≥ 0.30 | 0.3214 | PASS |
| `test_recall` | ≥ 0.30 | 0.4737 | PASS |
| `cv_stability` (nested_cv_f1_std) | ≤ 0.15 | 0.0545 | PASS |

### Smoke Test

Loads the raw LightGBM model from `runs:/{run_id}/model/data/feature_store/raw_model` and predicts on a 10-row sample from the feature tables. Verifies predictions are non-empty and binary (0/1).

**Result:** PASS — 10 predictions, classes=[0, 1]

### Outcome

All checks passed. Model v2 assigned `Challenger` alias and tagged with validation results.

---

## Problems & Workarounds

| Problem | Root Cause | Workaround |
|---------|-----------|------------|
| `fe.score_batch()` / `pyfunc.load_model()` fail | `create_training_set()` in train.py is missing `exclude_columns=["source", "ingested_at"]` — bronze metadata recorded as passthrough features | Smoke test loads raw LightGBM model directly from run artifacts |
| SCPAP005 lint on cell 6 | Spark transformations (`.join()`, `.toPandas()`) inside `try/except` flagged as lazy | False positive — `.toPandas()` is an action inside the try block; lint persists |

---

## Key Decisions

1. **Sanity gates, not promotion thresholds** — Metric thresholds (F1 ≥ 0.30, AUC ≥ 0.60, precision/recall ≥ 0.30) are minimum quality bars. Actual promotion thresholds (F1 > 0.75, AUC within 0.005) live in `promote.py`.
2. **CV stability check** — Added `nested_cv_f1_std ≤ 0.15` check using the std from nested CV outer folds, ensuring the model is not overly sensitive to fold selection.
3. **Raw model smoke test** — Loads LightGBM directly rather than through pyfunc, bypassing the `source`/`ingested_at` passthrough column issue. TODO: fix train.py with `exclude_columns`, retrain, switch to `fe.score_batch()`.
4. **Validation tags on model version** — All check results written as UC model version tags (`validation_*`, `validation_*_passed`) for auditability in Catalog Explorer.

---

## Files Modified

| File | Change |
|------|--------|
| `src/validate/validate.py` | Full 8-cell implementation: install → params → load metrics → threshold checks → smoke test → alias + tags → task value |
| `PROJECT_MEMORY.md` | Moved validate to Implemented, added fe.score_batch known issue, lint note |
| `README.md` | Updated validate/ tree comment |

---

## Next Steps

* Fix `exclude_columns=["source", "ingested_at"]` in train.py, retrain, then switch smoke test to `fe.score_batch()` for full Feature Store E2E coverage
* Implement `promote.py` — champion/challenger comparison with F1 > 0.75 threshold
* Implement `deploy/` notebooks — MLflow 3 deployment automation
* Implement `inference/batch_predict.py` — @Champion batch scoring

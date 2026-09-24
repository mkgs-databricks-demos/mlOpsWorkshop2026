# Session: Serving Endpoint Deploy — 2026-09-24

**Bundle:** `mlops-workshop-ai`  
**Target:** dev  
**Branch:** `mg-genie-eda-feature-design`

---

## Objective

Review the full `mlOpsWorkshop2026` monorepo, align the `-ai` bundle variables with what `-infra` actually deployed, and bring up the model serving endpoint.

---

## Problems Found

### 1. `databricks.yml` — Three broken dev-target variables

| Variable | Before (broken) | Root Cause | After (fixed) |
|----------|-----------------|------------|----------------|
| `catalog` | `mlops_workshop` | Wrong catalog — infra uses `hls_fde_dev` | `hls_fde_dev` |
| `user_schema` | `user_${bundle.user_name}` | `${bundle.user_name}` does not exist in DABs | `dev_${workspace.current_user.short_name}_mlops_workshop` |
| `registered_model_name` | `mlops_workshop.user_${bundle.user_name}.churn_model` | Cascading from wrong catalog + broken interpolation | `hls_fde_dev.dev_${workspace.current_user.short_name}_mlops_workshop.dev_${workspace.current_user.short_name}_churn_model` |

Prod-target variables were already correct.

### 2. `serving_endpoint.yml` — Endpoint name too long

Original: `churn-serving-${var.user_schema}` would produce `[dev matthew_giglia] churn-serving-dev_matthew_giglia_mlops_workshop` (redundant, very long).  
Fixed to: `churn-serving` — dev mode adds `[dev <user>]` prefix automatically for isolation.

### 3. Online Feature Store not provisioned

Model logged with `fe.log_model()` embeds `FeatureLookup`s against two feature tables. The serving endpoint auto-tries to create online tables but no online store existed.

**Error:** `No suitable online store found for feature tables: churn_windowed_features, churn_profile_features`

### 4. Inference table prefix conflict

First failed deploy auto-created `churn_serving_payload` table. Re-deploy blocked with `Table already exists`. Changed prefix to `churn_serving_v2`.

### 5. Raw model receives non-feature columns

Feature lookup succeeds (Lakebase pipelined lookup works), but the `fe.log_model()` wrapper passes ALL columns to the raw LightGBM model, including `customer_id`, `observation_date`, `source`, `ingested_at`. LightGBM rejects non-numeric types.

**Error:** `ValueError: pandas dtypes must be int, float or bool. Fields with bad pandas dtypes: customer_id: object, observation_date: datetime64[ns], source: object, ingested_at: datetime64[ns]`

This is a **training/logging issue** in `-infra`'s `train.py` — the model needs a pyfunc wrapper that drops non-feature columns before calling `predict()`. Flagged for the other genie session working on `-infra`.

---

## Changes Made

### Files Modified

| File | Change |
|------|--------|
| `databricks.yml` | Fixed all 3 dev variables; updated default catalog to `hls_fde_dev`; added inline comments documenting cross-bundle dependency |
| `resources/serving_endpoint.yml` | Simplified endpoint name to `churn-serving`; added version lifecycle comments; changed inference table prefix to `churn_serving_v2` |

### Infrastructure Created (outside bundle)

| Resource | Details |
|----------|----------|
| Online Store | `mlops-workshop-churn-features` (Lakebase, CU_1 capacity) |
| Online Table | `hls_fde_dev.dev_matthew_giglia_mlops_workshop.churn_windowed_features_online` (FOREIGN, 500 rows) |
| Online Table | `hls_fde_dev.dev_matthew_giglia_mlops_workshop.churn_profile_features_online` (FOREIGN, 500 rows) |
| CDF enabled | `churn_windowed_features`, `churn_profile_features` (required for TRIGGERED publish) |

### Serving Endpoint Deployed

| Field | Value |
|-------|-------|
| Name | `dev_matthew_giglia_churn-serving` |
| Entity | `hls_fde_dev.dev_matthew_giglia_mlops_workshop.dev_matthew_giglia_churn_model` v1 |
| State | **READY** (provisioned in \~350s) |
| Feature Lookup | Working (Lakebase pipelined, 2 sub-requests) |
| Prediction | **BLOCKED** — raw model dtype error (training issue) |

---

## Decisions

1. **Endpoint name simplification** — Removed `${var.user_schema}` from the name. Dev mode prefix provides per-user isolation; no need to duplicate schema in the name.
2. **Online Store capacity** — CU_1 (smallest). Sufficient for workshop; scales if needed.
3. **Inference table prefix workaround** — Used `churn_serving_v2` to avoid conflict with leftover `churn_serving_payload` from failed deploy. Original table should be cleaned up eventually.
4. **Model prediction issue deferred** — The raw-model dtype error is in `-infra`'s training code. Fix: wrap LightGBM in a pyfunc that drops `[customer_id, observation_date, source, ingested_at]` before `predict()`. Flagged for the parallel infra session.

---

## Resolved Variables (dev target)

```
catalog:               hls_fde_dev
user_schema:           dev_matthew_giglia_mlops_workshop
registered_model_name: hls_fde_dev.dev_matthew_giglia_mlops_workshop.dev_matthew_giglia_churn_model
endpoint_name:         dev_matthew_giglia_churn-serving
inference_table:       hls_fde_dev.dev_matthew_giglia_mlops_workshop.churn_serving_v2_*
```

---

## Model State (at session end)

* **3 versions** in `dev_matthew_giglia_churn_model`
* **Challenger** alias -> v2
* **Champion** alias -> not set (deployment job in `-infra` pending)
* **PreviousChampion** alias -> not set

---

## Open Items for Other Sessions

- [ ] **`-infra` training fix:** Re-log model with pyfunc wrapper that selects only `[total_revenue_90d, avg_daily_sessions_30d, overdue_payment_count_90d, tenure_days, company_size_encoded]` before `predict()`
- [ ] **`-infra` deployment job:** Promote Challenger -> Champion (other genie session active)
- [ ] **Cleanup:** Drop orphan `churn_serving_payload` table, revert prefix to `churn_serving`
- [ ] **Online store provisioning in bundle:** Consider adding online store + publish to `-infra` bundle or a setup notebook so it's reproducible per participant

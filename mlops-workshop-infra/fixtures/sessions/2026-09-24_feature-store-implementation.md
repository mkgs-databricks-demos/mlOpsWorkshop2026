# Session: Feature Store Implementation

**Date:** 2026-09-24  
**Bundle:** `mlops-workshop-infra`  
**Duration:** ~2 hours  

---

## Summary

Built two feature engineering notebooks implementing the same 9 features (6 time-windowed + 3 static) using contrasting Databricks Feature Store patterns:

1. **Declarative Feature Views** (`feature_definitions.py`) — `Feature` objects with `AggregationFunction` + time windows, registered as governed UC objects
2. **Classic Feature Tables** (`feature_tables_classic`) — manual PySpark aggregations written to Delta feature tables with primary keys, assembled via `FeatureLookup`

---

## Problems & Root Causes

### 1. Feature Views DATE → TIMESTAMP incompatibility
**Error:** `[DATATYPE_MISMATCH.UNEXPECTED_INPUT_TYPE] Cannot resolve "unix_micros(event_date)"` 
**Root cause:** Feature Views API internally calls `unix_micros()` which rejects DATE columns. The docs say DateType is supported for `timeseries_column`, but the implementation doesn’t handle it.  
**Fix:** Created 3 lightweight SQL views (`*_fv`) that CAST date columns to TIMESTAMP.

### 2. DeltaTableSource transformation_sql backtick bug
**Error:** `[PARSE_SYNTAX_ERROR] Syntax error at or near '\`hls_fde_dev\`'`  
**Root cause:** The `transformation_sql` parameter on `DeltaTableSource` triggers an internal code path that adds backtick-quoted identifiers, which the API’s own SQL parser rejects (SQLSTATE 42601 — PostgreSQL-style).  
**Fix:** Abandoned `transformation_sql`; used SQL views instead.

### 3. Count input cannot reference timeseries column
**Error:** `[UNRESOLVED_COLUMN.WITH_SUGGESTION] A column with name \`billing_date\` cannot be resolved`  
**Root cause:** The API internally renames the `timeseries_column` (e.g. to `source_ts_*`), making it unreferenceable as `Count(input=...)`.  
**Fix:** Changed `Count(input="billing_date")` to `Count(input="amount")` for `overdue_payment_count_90d`.

### 4. Standard v6 missing ML packages
**Finding:** Standard v6 base image only ships `databricks-sdk` (0.122.0). Both `mlflow` and `databricks-feature-engineering` are absent.  
**Resolution:** User configured dependencies via notebook environment panel (preferred over `%pip install` cell for interactive use). Pip install cell kept in classic notebook for portability.

### 5. .py file vs notebook type in Git folders
**Problem:** `createAsset` with `assetType: "file"` creates a plain workspace file, not a notebook — even with `.py` extension and Databricks notebook source format.  
**Fix:** Used `createAsset` with `assetType: "notebook"` for the classic notebook. The Git-folder gotcha (bundle validate can’t find NOTEBOOK objects) doesn’t apply since this notebook isn’t referenced in bundle YAML.

---

## Changes Made

### New Files

| File | Type | Description |
|------|------|-------------|
| `src/train/feature_definitions.py` | Notebook (.py) | 7 cells: declarative Feature Views, 6 registered UC features |
| `src/train/feature_tables_classic` | Notebook | 8 cells: classic Feature Store, 2 UC feature tables + FeatureLookup |
| `docs/design/feature-engineering-design.md` | Markdown | Feature engineering spec (from prior EDA session) |

### Modified Files

| File | Change |
|------|--------|
| `PROJECT_MEMORY.md` | Updated implementation status, added Feature Views gotchas, added classic notebook |
| `README.md` | *(pending update)* |

### UC Objects Created

| Object | Type | Details |
|--------|------|----------|
| `avg_daily_sessions_30d` | Feature (UC) | Avg(session_count), Tumbling 30d |
| `max_api_calls_7d` | Feature (UC) | Max(api_calls), Sliding 7d/1d |
| `total_revenue_90d` | Feature (UC) | Sum(amount), Tumbling 90d |
| `overdue_payment_count_90d` | Feature (UC) | Count(amount) WHERE overdue, Tumbling 90d |
| `support_tickets_7d` | Feature (UC) | Count(ticket_id), Sliding 7d/1d |
| `escalated_tickets_30d` | Feature (UC) | Count(ticket_id) WHERE escalated, Tumbling 30d |
| `product_usage_events_fv` | View | DATE→TIMESTAMP cast for event_date |
| `billing_history_fv` | View | DATE→TIMESTAMP cast for billing_date |
| `billing_history_overdue_fv` | View | Cast + filter for overdue payments |
| `churn_windowed_features` | Feature Table | Time series (PK: customer_id + observation_date), 6 features |
| `churn_profile_features` | Feature Table | Static (PK: customer_id), 3 features |

---

## Key Decisions

1. **Helper views over transformation_sql** — The `transformation_sql` parameter is buggy; SQL views are reliable and idempotent.
2. **Environment panel over %pip install** — Standard v6 + environment dependencies eliminates the Python restart overhead (~10-15s per run). Pip install cell kept in classic notebook for standalone portability.
3. **Two notebooks, one feature set** — Both notebooks compute the same 9 features for pedagogical comparison. The training notebook will use the Feature Views approach (eliminates training-serving skew via `fe.score_batch()`).
4. **Static features deferred** — `plan_type`, `company_size`, and `tenure_days` are NOT Feature Views (they require transformations). In the declarative notebook, they’re joined in the training notebook via `create_training_set()`. In the classic notebook, they’re a separate static feature table.
5. **Non-destructive registration** — Registration cell uses try/except (register, skip if exists) instead of delete+re-register, to avoid safety guardrail issues.

---

## Cleanup Required

* Stray `feature_tables_classic` notebook at bundle root (manual delete)

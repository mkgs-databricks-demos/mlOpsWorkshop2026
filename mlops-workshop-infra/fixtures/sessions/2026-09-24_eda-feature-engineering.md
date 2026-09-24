# Session: EDA & Feature Engineering Design

**Date:** 2026-09-24  
**Bundle:** `mlops-workshop-infra`  
**Target:** dev

---

## Summary

Full exploratory data analysis of the 5 silver tables in `hls_fde_dev.dev_matthew_giglia_mlops_workshop`, culminating in a comprehensive feature engineering design document that specifies the exact features, collinearity resolutions, and implementation pattern for `feature_definitions.py`.

---

## Problems Encountered

1. **`statsmodels` not available on serverless compute** — VIF cell in EDA notebook failed with `ModuleNotFoundError: No module named 'statsmodels'`.
   - **Root cause:** Serverless compute does not include `statsmodels` by default.
   - **Fix:** Rewrote VIF calculation using manual OLS via `numpy.linalg.lstsq` (VIF_j = 1/(1-R²_j)).

2. **`createAsset` relative path misresolution** — Creating `../docs/design/feature-engineering-design.md` resolved one level too high (monorepo root instead of bundle root).
   - **Root cause:** Relative path resolution from the active notebook context.
   - **Fix:** Used absolute workspace path. Stray empty file at `mlOpsWorkshop2026/docs/design/` remains (safe to delete).

3. **Matplotlib deprecation warning** — `labels` parameter of `boxplot()` renamed to `tick_labels` in matplotlib 3.9.
   - **Impact:** Warning only, no functional issue. Can fix in future with `tick_labels=` kwarg.

---

## Work Completed

### 1. Exploratory Data Analysis Notebook

**File:** `fixtures/eda_churn_exploration` (30-cell notebook, all cells executed successfully)

**Sections:**
- Schema inventory & row counts (5 silver MVs, ~22K total records)
- Data quality audit (zero nulls across all columns in all tables)
- Join topology verification (customer_id universal key, perfect referential integrity)
- Target variable analysis (18.8% churn rate, 94/500, moderate imbalance)
- Churn rate by plan type, region, company size
- Usage, billing, and support metrics by churn status
- Feature usage depth and adoption analysis
- Tenure comparison
- Correlation matrix heatmap (19×19, annotated)
- Top correlated pairs (40 pairs with |r| ≥ 0.5)
- Variance Inflation Factor table (18 features)
- Distribution histograms (12-panel, active vs churned overlay)
- Box plots (6 key features, outlier detection)
- Target correlation ranking (horizontal bar chart)
- Collinearity clusters and feature selection summary

### 2. Feature Engineering Design Document

**File:** `docs/design/feature-engineering-design.md` (9 sections)

Consolidates all EDA findings into an actionable spec for `feature_definitions.py`:
- Data landscape (5 tables, schemas, row counts)
- Join topology with cardinality stats
- Target variable analysis with class balance strategy
- Feature candidate ranking with |r|, VIF, and discriminative ratios
- Collinearity analysis: 6 clusters identified, resolution for each
- Distribution characteristics and outlier assessment
- Final feature set: 6 Feature Views + 3 static features + 11 exclusions with justification
- Implementation guidance: code pattern, YAML integration, key decisions

---

## Key Findings

### Strongest Churn Predictors (by |r| with target)

| Feature | |r| | Active Mean | Churned Mean | Ratio |
|---------|-----|------------|-------------|-------|
| avg_api_calls | 0.883 | 100.0 | 37.9 | 2.6x |
| escalated_count | 0.802 | 0.5 | 4.5 | 9.0x |
| max_api_calls | 0.766 | — | — | — |
| overdue_rate | 0.762 | 8.9% | 34.1% | 3.8x |
| overdue_count | 0.681 | 1.6 | 6.2 | 3.9x |
| ticket_count | 0.665 | 5.5 | 13.1 | 2.4x |

### Critical Collinearity Finding

`tenure_days` ↔ `invoice_count`: r = 1.0, VIF ~1100. Perfectly collinear — monthly billing creates a deterministic relationship with account age.

### Final Feature Set (9 features)

**Time-windowed (6):** avg_daily_sessions_30d, max_api_calls_7d, total_revenue_90d, overdue_payment_count_90d, support_tickets_7d, escalated_tickets_30d

**Static (3):** plan_type (ordinal), company_size (ordinal), tenure_days

**Dropped (11):** region, avg_feature_depth, max_sessions, max_api_calls, usage_event_count, avg_invoice, invoice_count, overdue_count, pending_count, escalated_count, pending_tickets

---

## Decisions Made

1. **No preprocessing needed** — zero nulls, no imputation, no scaling (tree-based model)
2. **Class imbalance strategy** — `class_weight='balanced'` + stratified splits; SMOTE unnecessary at 94 positives
3. **Primary metric** — F1 score (over accuracy) due to 18.8% positive rate
4. **Feature Views over manual aggregations** — declarative API eliminates training-serving skew
5. **Ordinal encoding for plan_type and company_size** — clear monotonic churn relationships

---

## Files Created / Modified

| File | Action |
|------|--------|
| `fixtures/eda_churn_exploration` | **Created** — 30-cell EDA notebook |
| `docs/design/feature-engineering-design.md` | **Created** — feature engineering spec |
| `fixtures/sessions/2026-09-24_eda-feature-engineering.md` | **Created** — this session summary |
| `fixtures/sessions/INDEX.md` | **Updated** — added this session entry |
| `PROJECT_MEMORY.md` | **Updated** — EDA status, design doc reference |
| `README.md` | **Updated** — design doc and fixtures references |

---

## Next Steps

1. **Implement `feature_definitions.py`** — using the spec from `docs/design/feature-engineering-design.md`
2. **Wire `feature_definitions` into `training_job.yml`** — as first task before model_training
3. **Delete 3 obsolete files** — `create_bronze_tables.py`, `autoload_to_bronze.py`, `flatten_to_silver.py`
4. **Implement `train.py`** — LightGBM/XGBoost with Feature Views training set
5. **Implement `validate.py`** — F1 > 0.75 gate, AUC within 0.005
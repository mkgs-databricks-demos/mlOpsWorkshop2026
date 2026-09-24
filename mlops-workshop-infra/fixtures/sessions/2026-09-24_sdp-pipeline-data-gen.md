# Session: SDP Ingestion Pipeline + Data Generation

**Date:** 2026-09-24  
**Branch:** `mg-genie-infra-bundle-resources`  
**Bundle:** `mlops-workshop-infra`  
**Predecessor:** [2026-09-24_infra-bundle-resources.md](2026-09-24_infra-bundle-resources.md)

---

## Problem

Bundle validation was failing (`.ipynb` vs `.py` mismatch), and the data ingestion job needed to be converted from a 7-task notebook job to an SDP pipeline architecture. All 13 notebook stubs existed as `.py` files on disk but 4 job YAMLs referenced `.ipynb`.

## Root Causes

1. **Extension mismatch:** Job YAMLs authored with `.ipynb` paths; Git folder stored files as `.py`.
2. **Architecture gap:** Design called for SDP pipeline (bronze → silver), but original job YAML had notebook tasks for each ingestion step.
3. **Serverless filesystem restrictions:** Three separate issues discovered during end-to-end testing.

## Changes Made

### 1. Fixed `.ipynb` → `.py` in all job YAMLs (14 references)

| File | Refs Fixed |
|------|------------|
| `resources/data_ingestion_job.yml` | 6 |
| `resources/training_job.yml` | 5 |
| `resources/batch_inference_job.yml` | 1 |
| `resources/deployment_job.yml` | 2 |

### 2. SDP pipeline architecture

**New files:**

| File | Purpose |
|------|----------|
| `resources/data_ingestion_pipeline.yml` | SDP pipeline resource — serverless, Photon, volume_path config |
| `src/pipeline/ingestion/bronze.py` | `bronze_autoload` (Auto Loader, text, recursiveFileLookup), `bronze_zerobus` placeholder, `bronze_unified` temp view |
| `src/pipeline/ingestion/silver.py` | 5 `@dp.materialized_view` functions with `parse_json(payload):field::TYPE` extraction |

### 3. Data generation notebooks

| File | Purpose |
|------|----------|
| `src/data/generate_ndjson.py` | 500 customers, 5 record types (~30K records), plan-dependent churn signal, writes directly to landing volume |
| `src/data/post_to_zerobus.py` | Placeholder (ZeroBus SDK not yet available) |
| `src/data/write_to_volume.py` | Retained for standalone use; **removed from job** |

### 4. Job restructure: `data_ingestion_job.yml`

**Before (7 tasks):**
```
create_bronze → generate_ndjson → check_gate
  ├─ post_to_zerobus
  └─ write_to_volume
autoload_to_bronze → flatten_to_silver
```

**After (4 tasks):**
```
generate_ndjson (→ writes directly to volume)
  → check_zerobus_gate
    ├─ TRUE: post_to_zerobus
    └─ FALSE: (no-op)
  → run_ingestion_pipeline (AT_LEAST_ONE_SUCCESS)
```

Key change: `generate_ndjson` receives `volume_path` param and writes NDJSON directly to the landing volume, eliminating the `write_to_volume` intermediate task.

### 5. Three serverless compatibility fixes

| Problem | Root Cause | Fix |
|---------|-----------|-----|
| `LocalFilesystemAccessDeniedException` on `dbutils.fs.rm("file:/tmp/...")` | Serverless blocks `dbutils.fs` access to `file:` scheme for non-`/Workspace/` paths | `shutil.rmtree()` (Python native) |
| `FileNotFoundError: /tmp/mlops-workshop/ndjson` in downstream task | Each serverless task runs on separate compute; `/tmp/` is ephemeral per task | Write directly to UC volume instead of `/tmp/` |
| `OSError: Operation not supported` on `shutil.rmtree(volume_path)` | Volume root is a managed mount point; can't remove the root directory itself | Clean subdirectories only: `for item in os.listdir(volume_path): ...` |

### 6. Documentation updates

* `docs/design/implementation-plan.md` — Phase 3A/3B split, corrected `.py` extensions, updated directory structure
* `README.md`, `docs/design/L100-system-overview.md`, `docs/design/L200-01-infra-bundle.md`, `docs/design/L300-implementation-specs.md` — SDP architecture throughout

## Decisions

* **SDP over notebook tasks for ingestion** — Streaming tables + materialized views give automatic incremental processing, data quality expectations, and lineage. Eliminates 3 notebook tasks (create_bronze, autoload_to_bronze, flatten_to_silver).
* **Direct-to-volume writes** — `generate_ndjson` writes to the landing volume instead of `/tmp/`. Eliminates cross-task file sharing problem on serverless. The `write_to_volume` notebook is retained for standalone/interactive use.
* **Multi-file SDP layout** — `bronze.py` and `silver.py` as separate pipeline source files. The pipeline YAML uses `glob: include: ../src/pipeline/ingestion/**` to pick up all files.
* **Volume cleanup: subdirectories only** — Can't `rmtree` a managed volume root. Pattern: iterate `os.listdir(volume_path)` and `rmtree`/`remove` each item.
* **`pipeline_task` in job** — `run_ingestion_pipeline` uses `pipeline_task.pipeline_id` referencing `${resources.pipelines.data_ingestion_pipeline.id}` with `full_refresh: true` for workshop idempotency.

## Deployment & Verification

* `bundle validate --strict --target dev` — PASS
* `bundle deploy --target dev` — 9 resources created (schema, experiment, model, volume, pipeline, 4 jobs)
* `bundle run --target dev data_ingestion` — SUCCESS (after 3 iterations fixing serverless issues)
* Silver table verification:

| Table | Rows |
|-------|------|
| `customer_profiles` | 500 |
| `product_usage_events` | 8,301 |
| `billing_history` | 9,511 |
| `support_interactions` | 3,461 |
| `churn_labels` | 500 |

## Obsolete Files (to delete manually)

* `src/data/create_bronze_tables.py` — replaced by SDP pipeline
* `src/data/autoload_to_bronze.py` — replaced by SDP pipeline
* `src/data/flatten_to_silver.py` — replaced by SDP pipeline

## Files Modified

* `resources/data_ingestion_job.yml` (modified — restructured tasks, added volume_path param)
* `resources/data_ingestion_pipeline.yml` (new)
* `resources/training_job.yml` (modified — .ipynb → .py)
* `resources/batch_inference_job.yml` (modified — .ipynb → .py)
* `resources/deployment_job.yml` (modified — .ipynb → .py)
* `src/pipeline/ingestion/bronze.py` (new)
* `src/pipeline/ingestion/silver.py` (new)
* `src/data/generate_ndjson.py` (implemented — was stub)
* `src/data/post_to_zerobus.py` (implemented — placeholder)
* `src/data/write_to_volume.py` (implemented — retained, removed from job)
* `docs/design/implementation-plan.md` (modified)
* `README.md` (modified)
* `docs/design/L100-system-overview.md` (modified)
* `docs/design/L200-01-infra-bundle.md` (modified)
* `docs/design/L300-implementation-specs.md` (modified)

## Next Steps

* Phase 4: `feature_definitions.py` (Feature Views with declarative aggregations)
* Phase 5: `train.py`, `validate.py` (model training + validation gates)
* Phase 6: `promote.py` (champion/challenger promotion)
* Phase 7: `evaluate.py`, `promote_champion.py` (deployment job)
* Phase 8: `batch_predict.py`
* Delete 3 obsolete notebook stubs
* Commit session summary + project memory update

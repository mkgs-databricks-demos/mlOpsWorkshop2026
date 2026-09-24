# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Model Validation — Challenger Gate
# MAGIC %md
# MAGIC # Model Validation — Challenger Gate
# MAGIC
# MAGIC Validate a newly trained model version against minimum quality thresholds and an end-to-end smoke test using `fe.score_batch()`. If all checks pass, the version is assigned the **Challenger** alias and tagged with validation results. Outputs `validation_passed` task value for the downstream condition gate.

# COMMAND ----------

# DBTITLE 1,Install dependencies
# MAGIC %pip install --upgrade databricks-sdk mlflow databricks-feature-engineering lightgbm
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Parameters & setup
import mlflow

dbutils.widgets.text("model_name", "hls_fde_dev.dev_matthew_giglia_mlops_workshop.dev_matthew_giglia_churn_model")
dbutils.widgets.text("model_version", "")

model_name = dbutils.widgets.get("model_name")
model_version = dbutils.widgets.get("model_version")

# Derive catalog.schema from the 3-level UC model name
parts = model_name.split(".")
catalog = parts[0]
schema = parts[1]
CS = f"{catalog}.{schema}"

mlflow.set_registry_uri("databricks-uc")

print(f"Model:   {model_name}")
print(f"Version: {model_version}")
print(f"Schema:  {CS}")

# COMMAND ----------

# DBTITLE 1,Load model version & training run metrics
from mlflow import MlflowClient

client = MlflowClient(registry_uri="databricks-uc")

# Retrieve model version metadata
mv = client.get_model_version(name=model_name, version=model_version)
run_id = mv.run_id

# Retrieve training run metrics
run = client.get_run(run_id)
metrics = run.data.metrics

print(f"Model version: {model_name} v{model_version}")
print(f"Source run:    {run_id}")
print(f"Status:        {mv.status}")
print(f"\nTraining Metrics:")
print("=" * 50)
for k, v in sorted(metrics.items()):
    print(f"  {k:25s}: {v:.4f}")
print("=" * 50)

# COMMAND ----------

# DBTITLE 1,Metric threshold validation
# ── Minimum thresholds for a model to become Challenger ──────────
# These are sanity gates — promotion thresholds (F1>0.75) are in promote.py
METRIC_THRESHOLDS = {
    "test_f1":        0.30,   # better than random
    "test_auc":       0.60,   # discriminative power
    "test_precision": 0.30,   # minimum precision
    "test_recall":    0.30,   # minimum recall
}

print("Validation Checks")
print("=" * 65)

checks = {}
all_passed = True

for metric_name, min_val in METRIC_THRESHOLDS.items():
    actual = metrics.get(metric_name)
    if actual is None:
        passed = False
        status = "MISSING"
    elif actual >= min_val:
        passed = True
        status = "PASS"
    else:
        passed = False
        status = "FAIL"

    checks[metric_name] = {"actual": actual, "threshold": min_val, "passed": passed}
    all_passed = all_passed and passed

    actual_str = f"{actual:.4f}" if actual is not None else "N/A"
    icon = "\u2713" if passed else "\u2717"
    print(f"  {icon}  {metric_name:25s}  {actual_str:>8s}  \u2265  {min_val:.2f}   [{status}]")

# ── Cross-validation stability check ────────────────────────────
cv_std = metrics.get("nested_cv_f1_std")
if cv_std is not None:
    CV_STD_MAX = 0.15
    cv_stable = cv_std <= CV_STD_MAX
    checks["cv_stability"] = {"actual": cv_std, "threshold": CV_STD_MAX, "passed": cv_stable}
    all_passed = all_passed and cv_stable
    icon = "\u2713" if cv_stable else "\u2717"
    status = "PASS" if cv_stable else "FAIL"
    print(f"  {icon}  {'cv_stability':25s}  {cv_std:>8.4f}  \u2264  {CV_STD_MAX:.2f}   [{status}]")

print("=" * 65)
print(f"Metric checks: {'ALL PASSED' if all_passed else 'VALIDATION FAILED'}")

# COMMAND ----------

# DBTITLE 1,Smoke test — end-to-end inference via fe.score_batch()
from databricks.feature_engineering import FeatureEngineeringClient
from pyspark.sql import functions as F

fe = FeatureEngineeringClient()

# Small sample from labels table — validates full Feature Store inference path
sample_df = (
    spark.table(f"{CS}.churn_labels")
    .withColumn("observation_date", F.col("observation_date").cast("timestamp"))
    .limit(10)
)

model_uri = f"models:/{model_name}/{model_version}"
print(f"Smoke test: scoring {sample_df.count()} rows via fe.score_batch()")
print(f"Model URI:  {model_uri}")

try:
    predictions = fe.score_batch(model_uri=model_uri, df=sample_df)
    pred_pdf = predictions.select("customer_id", "prediction").toPandas()

    n_predictions = len(pred_pdf)
    unique_classes = sorted(pred_pdf["prediction"].unique().tolist())

    smoke_passed = n_predictions > 0 and all(p in [0, 1] for p in unique_classes)

    checks["smoke_test"] = {"passed": smoke_passed}
    all_passed = all_passed and smoke_passed

    icon = "\u2713" if smoke_passed else "\u2717"
    status = "PASS" if smoke_passed else "FAIL"
    print(f"\n  {icon}  Smoke test: {n_predictions} predictions, classes={unique_classes}  [{status}]")
    display(predictions.select("customer_id", "observation_date", "prediction").limit(5))

except Exception as e:
    checks["smoke_test"] = {"passed": False, "error": str(e)}
    all_passed = False
    print(f"\n  \u2717  Smoke test FAILED: {e}")

print(f"\nValidation verdict: {'PASSED' if all_passed else 'FAILED'}")

# COMMAND ----------

# DBTITLE 1,Assign Challenger alias & validation tags
from datetime import datetime

# ── Tag model version with validation results ────────────────────
tag_prefix = "validation"
client.set_model_version_tag(model_name, model_version, f"{tag_prefix}_passed", str(all_passed).lower())
client.set_model_version_tag(model_name, model_version, f"{tag_prefix}_timestamp", str(datetime.now()))

for check_name, result in checks.items():
    if result.get("actual") is not None:
        client.set_model_version_tag(
            model_name, model_version,
            f"{tag_prefix}_{check_name}", f"{result['actual']:.4f}",
        )
    client.set_model_version_tag(
        model_name, model_version,
        f"{tag_prefix}_{check_name}_passed", str(result["passed"]).lower(),
    )

# ── Assign Challenger alias if validation passed ────────────────
if all_passed:
    client.set_registered_model_alias(model_name, "Challenger", model_version)
    print(f"\u2713 Assigned 'Challenger' alias to {model_name} v{model_version}")
else:
    print(f"\u2717 Validation FAILED \u2014 no alias assigned to v{model_version}")

validation_passed = str(all_passed).lower()
print(f"\nvalidation_passed = {validation_passed}")

# COMMAND ----------

# DBTITLE 1,Set task value for downstream condition gate
try:
    dbutils.jobs.taskValues.set(key="validation_passed", value=validation_passed)
    print(f"Task value set: validation_passed = {validation_passed}")
except Exception:
    print(f"Not running in a job \u2014 validation_passed = {validation_passed}")
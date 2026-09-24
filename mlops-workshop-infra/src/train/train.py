# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Churn Model Training — Classic Feature Store
# MAGIC %md
# MAGIC # Churn Model Training — Classic Feature Store
# MAGIC
# MAGIC Train a LightGBM classifier for customer churn prediction using classic Feature Store (`FeatureLookup` + `fe.create_training_set`). Nested cross-validation (5 outer × 30 inner Optuna trials) for unbiased evaluation, followed by feature importance pruning and re-tuning. Model registered to Unity Catalog with `fe.log_model()` for `fe.score_batch()` parity at inference.

# COMMAND ----------

# DBTITLE 1,Install dependencies
# MAGIC %pip install --upgrade databricks-sdk mlflow databricks-feature-engineering lightgbm optuna scikit-learn
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Parameters & MLflow experiment
import mlflow

dbutils.widgets.text("experiment_name", "/Workspace/Users/matthew.giglia@databricks.com/[dev matthew_giglia] mlops-workshop-churn")
dbutils.widgets.text("model_name", "hls_fde_dev.dev_matthew_giglia_mlops_workshop.dev_matthew_giglia_churn_model")
dbutils.widgets.text("catalog", "hls_fde_dev")
dbutils.widgets.text("schema", "dev_matthew_giglia_mlops_workshop")

experiment_name = dbutils.widgets.get("experiment_name")
model_name = dbutils.widgets.get("model_name")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
CS = f"{catalog}.{schema}"

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(experiment_name)
mlflow.autolog(disable=True)

print(f"Experiment: {experiment_name}")
print(f"Model:      {model_name}")
print(f"Features:   {CS}")

# COMMAND ----------

# DBTITLE 1,Build training set via FeatureLookup
from databricks.feature_engineering import FeatureEngineeringClient, FeatureLookup
from pyspark.sql import functions as F

fe = FeatureEngineeringClient()

# Labels — cast observation_date to timestamp (timeseries feature table requirement)
labels_df = (
    spark.table(f"{CS}.churn_labels")
    .withColumn("observation_date", F.col("observation_date").cast("timestamp"))
)

feature_lookups = [
    # Time-windowed features (point-in-time via timestamp_lookup_key)
    FeatureLookup(
        table_name=f"{CS}.churn_windowed_features",
        lookup_key="customer_id",
        timestamp_lookup_key="observation_date",
        feature_names=[
            "avg_daily_sessions_30d", "max_api_calls_7d",
            "total_revenue_90d", "overdue_payment_count_90d",
            "support_tickets_7d", "escalated_tickets_30d",
        ],
    ),
    # Static profile features (latest value, no timestamp)
    FeatureLookup(
        table_name=f"{CS}.churn_profile_features",
        lookup_key="customer_id",
        feature_names=[
            "plan_type_encoded", "company_size_encoded", "tenure_days",
        ],
    ),
]

training_set = fe.create_training_set(
    df=labels_df,
    feature_lookups=feature_lookups,
    label="churned",
)

training_pdf = training_set.load_df().toPandas()
print(f"Training set: {training_pdf.shape[0]} rows \u00d7 {training_pdf.shape[1]} columns")
print(f"Columns: {list(training_pdf.columns)}")
print(f"\nTarget distribution:")
print(training_pdf["churned"].value_counts())
display(training_pdf.head(5))

# COMMAND ----------

# DBTITLE 1,Stratified train/test split
from sklearn.model_selection import train_test_split

# Separate features from lookup keys and label
exclude_cols = ["customer_id", "observation_date", "churned", "source", "ingested_at"]
feature_cols = [c for c in training_pdf.columns if c not in exclude_cols]

X = training_pdf[feature_cols]
y = training_pdf["churned"].astype(int)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y,
)

print(f"Features ({len(feature_cols)}): {feature_cols}")
print(f"Train: {X_train.shape[0]} rows  |  Test: {X_test.shape[0]} rows")
print(f"Train positive rate: {y_train.mean():.1%}")
print(f"Test  positive rate: {y_test.mean():.1%}")

# COMMAND ----------

# DBTITLE 1,Nested cross-validation (5 outer × 30 inner Optuna trials)
import optuna
import numpy as np
from lightgbm import LGBMClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import f1_score

optuna.logging.set_verbosity(optuna.logging.WARNING)

# ── Nested CV: outer loop evaluates, inner loop tunes ────────────
# Tighter search space (max_depth 3-5, higher regularisation floors)
# to reduce overfitting on 400 rows
outer_cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
outer_scores = []
outer_importances = []

print("Nested Cross-Validation (5 outer \u00d7 30 inner trials \u00d7 4 inner folds)")
print("=" * 65)

for fold_idx, (train_idx, val_idx) in enumerate(outer_cv.split(X_train, y_train)):
    X_of_train = X_train.iloc[train_idx]
    X_of_val   = X_train.iloc[val_idx]
    y_of_train = y_train.iloc[train_idx]
    y_of_val   = y_train.iloc[val_idx]

    def objective(trial):
        params = {
            "n_estimators":    trial.suggest_int("n_estimators", 50, 200),
            "learning_rate":   trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
            "max_depth":       trial.suggest_int("max_depth", 3, 5),
            "num_leaves":      trial.suggest_int("num_leaves", 7, 20),
            "min_child_samples": trial.suggest_int("min_child_samples", 25, 50),
            "subsample":       trial.suggest_float("subsample", 0.6, 0.9),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 0.9),
            "reg_alpha":       trial.suggest_float("reg_alpha", 0.1, 1.0, log=True),
            "reg_lambda":      trial.suggest_float("reg_lambda", 0.5, 5.0, log=True),
        }
        mdl = LGBMClassifier(
            **params, class_weight="balanced", random_state=42, verbosity=-1,
        )
        inner_cv = StratifiedKFold(n_splits=4, shuffle=True, random_state=42)
        return cross_val_score(
            mdl, X_of_train, y_of_train, cv=inner_cv, scoring="f1",
        ).mean()

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=30)

    bp = {**study.best_params, "class_weight": "balanced", "random_state": 42, "verbosity": -1}
    mdl = LGBMClassifier(**bp)
    mdl.fit(X_of_train, y_of_train)

    fold_f1 = f1_score(y_of_val, mdl.predict(X_of_val))
    outer_scores.append(fold_f1)
    outer_importances.append(mdl.feature_importances_)

    print(f"  Fold {fold_idx + 1}: F1 = {fold_f1:.4f}  (inner best: {study.best_value:.4f})")

print("=" * 65)
print(f"Nested CV F1: {np.mean(outer_scores):.4f} \u00b1 {np.std(outer_scores):.4f}")
print("  (unbiased \u2014 no information leakage from tuning)")
print("=" * 65)

# COMMAND ----------

# DBTITLE 1,Feature importance pruning & final model
import pandas as pd
from sklearn.metrics import (
    roc_auc_score, precision_score, recall_score, accuracy_score,
)

# ── Aggregate importances across outer folds ─────────────────────
avg_imp = np.mean(outer_importances, axis=0)
imp_df = (
    pd.DataFrame({"feature": feature_cols, "importance": avg_imp})
    .sort_values("importance", ascending=False)
)
imp_df["pct"] = imp_df["importance"] / imp_df["importance"].sum() * 100

print("Feature Importances (averaged across 5 nested CV folds)")
print("=" * 65)
for _, row in imp_df.iterrows():
    bar = "\u2588" * int(row["pct"] * 1.5)
    print(f"  {row['feature']:30s} {row['pct']:5.1f}%  {bar}")

# ── Prune weak features ─────────────────────────────────────────
THRESHOLD_PCT = 5.0
selected_features = imp_df[imp_df["pct"] >= THRESHOLD_PCT]["feature"].tolist()
dropped_features  = imp_df[imp_df["pct"] <  THRESHOLD_PCT]["feature"].tolist()

print(f"\n{'=' * 65}")
print(f"Keeping {len(selected_features)} features (\u2265 {THRESHOLD_PCT}%): {selected_features}")
if dropped_features:
    print(f"Dropping {len(dropped_features)} features (< {THRESHOLD_PCT}%): {dropped_features}")

# ── Re-tune with pruned features ────────────────────────────────
X_train_pruned = X_train[selected_features]
X_test_pruned  = X_test[selected_features]


def objective_pruned(trial):
    params = {
        "n_estimators":    trial.suggest_int("n_estimators", 50, 200),
        "learning_rate":   trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
        "max_depth":       trial.suggest_int("max_depth", 3, 5),
        "num_leaves":      trial.suggest_int("num_leaves", 7, 20),
        "min_child_samples": trial.suggest_int("min_child_samples", 25, 50),
        "subsample":       trial.suggest_float("subsample", 0.6, 0.9),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 0.9),
        "reg_alpha":       trial.suggest_float("reg_alpha", 0.1, 1.0, log=True),
        "reg_lambda":      trial.suggest_float("reg_lambda", 0.5, 5.0, log=True),
    }
    mdl = LGBMClassifier(
        **params, class_weight="balanced", random_state=42, verbosity=-1,
    )
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    return cross_val_score(mdl, X_train_pruned, y_train, cv=cv, scoring="f1").mean()


study_pruned = optuna.create_study(direction="maximize", study_name="churn_lgbm_pruned")
study_pruned.optimize(objective_pruned, n_trials=50)

# ── Train final model + evaluate on held-out test ────────────────
best_params = {
    **study_pruned.best_params,
    "class_weight": "balanced",
    "random_state": 42,
    "verbosity": -1,
}

final_model = LGBMClassifier(**best_params)
final_model.fit(X_train_pruned, y_train)

y_pred  = final_model.predict(X_test_pruned)
y_proba = final_model.predict_proba(X_test_pruned)[:, 1]

test_metrics = {
    "test_f1":          f1_score(y_test, y_pred),
    "test_auc":         roc_auc_score(y_test, y_proba),
    "test_precision":   precision_score(y_test, y_pred),
    "test_recall":      recall_score(y_test, y_pred),
    "test_accuracy":    accuracy_score(y_test, y_pred),
    "cv_f1_pruned":     study_pruned.best_value,
    "nested_cv_f1_mean": float(np.mean(outer_scores)),
    "nested_cv_f1_std":  float(np.std(outer_scores)),
}

print(f"\nPruned model \u2014 Best CV F1: {study_pruned.best_value:.4f}")
print(f"\n{'=' * 55}")
print(f"TEST SET EVALUATION ({len(selected_features)} features)")
print("=" * 55)
for k, v in test_metrics.items():
    print(f"  {k:25s}: {v:.4f}")
print("=" * 55)

# COMMAND ----------

# DBTITLE 1,Log to MLflow & register model via Feature Store
import mlflow.lightgbm
from sklearn.metrics import (
    confusion_matrix, ConfusionMatrixDisplay,
    RocCurveDisplay, PrecisionRecallDisplay,
)
import matplotlib.pyplot as plt

# ── Build pruned FeatureLookups for fe.log_model() ──────────────
windowed_all = [
    "avg_daily_sessions_30d", "max_api_calls_7d",
    "total_revenue_90d", "overdue_payment_count_90d",
    "support_tickets_7d", "escalated_tickets_30d",
]
profile_all = ["plan_type_encoded", "company_size_encoded", "tenure_days"]

pruned_windowed = [f for f in selected_features if f in windowed_all]
pruned_profile  = [f for f in selected_features if f in profile_all]

pruned_lookups = []
if pruned_windowed:
    pruned_lookups.append(FeatureLookup(
        table_name=f"{CS}.churn_windowed_features",
        lookup_key="customer_id",
        timestamp_lookup_key="observation_date",
        feature_names=pruned_windowed,
    ))
if pruned_profile:
    pruned_lookups.append(FeatureLookup(
        table_name=f"{CS}.churn_profile_features",
        lookup_key="customer_id",
        feature_names=pruned_profile,
    ))

pruned_training_set = fe.create_training_set(
    df=labels_df, feature_lookups=pruned_lookups, label="churned",
)

with mlflow.start_run(run_name="lgbm_churn_pruned") as run:
    # ── Parameters ────────────────────────────────────────────────────
    mlflow.log_params(best_params)
    mlflow.log_param("n_features", len(selected_features))
    mlflow.log_param("n_features_original", len(feature_cols))
    mlflow.log_param("dropped_features", str(dropped_features))
    mlflow.log_param("train_size", len(X_train))
    mlflow.log_param("test_size", len(X_test))
    mlflow.log_param("nested_cv_outer_folds", 5)
    mlflow.log_param("optuna_trials_pruned", len(study_pruned.trials))

    # ── Metrics ──────────────────────────────────────────────────────
    mlflow.log_metrics(test_metrics)

    # ── Confusion matrix ─────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(6, 5))
    ConfusionMatrixDisplay(
        confusion_matrix(y_test, y_pred),
        display_labels=["Active", "Churned"],
    ).plot(ax=ax, cmap="Blues")
    ax.set_title("Confusion Matrix \u2014 Pruned Features")
    mlflow.log_figure(fig, "confusion_matrix.png")
    plt.close(fig)

    # ── ROC curve ────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(6, 5))
    RocCurveDisplay.from_predictions(y_test, y_proba, ax=ax)
    ax.set_title(f"ROC Curve (AUC = {test_metrics['test_auc']:.3f})")
    mlflow.log_figure(fig, "roc_curve.png")
    plt.close(fig)

    # ── Precision-Recall curve ────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(6, 5))
    PrecisionRecallDisplay.from_predictions(y_test, y_proba, ax=ax)
    ax.set_title("Precision-Recall Curve")
    mlflow.log_figure(fig, "pr_curve.png")
    plt.close(fig)

    # ── Log model with pruned Feature Store metadata ──────────────
    model_info = fe.log_model(
        model=final_model,
        artifact_path="model",
        flavor=mlflow.lightgbm,
        training_set=pruned_training_set,
    )

    # ── Register version under existing UC model ────────────────────
    from mlflow import MlflowClient
    client = MlflowClient(registry_uri="databricks-uc")
    mv = client.create_model_version(
        name=model_name,
        source=model_info.model_uri,
        run_id=run.info.run_id,
    )
    model_version = mv.version

print("=" * 65)
print("MODEL REGISTERED")
print("=" * 65)
print(f"  Run ID:     {run.info.run_id}")
print(f"  Model URI:  {model_info.model_uri}")
print(f"  Registered: {model_name} v{model_version}")
print(f"  Features:   {selected_features}")
print("=" * 65)

# COMMAND ----------

# DBTITLE 1,Set task value for downstream job tasks
try:
    dbutils.jobs.taskValues.set(key="model_version", value=str(model_version))
    print(f"Task value set: model_version = {model_version}")
except Exception:
    print(f"Not running in a job \u2014 model_version = {model_version}")
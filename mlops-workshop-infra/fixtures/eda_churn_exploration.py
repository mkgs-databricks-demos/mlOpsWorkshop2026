# Databricks notebook source
# DBTITLE 1,EDA: Customer Churn Exploration
# MAGIC %md
# MAGIC # Exploratory Data Analysis — Customer Churn
# MAGIC
# MAGIC **Schema:** `hls_fde_dev.dev_matthew_giglia_mlops_workshop`  
# MAGIC **Tables:** 5 silver materialized views + 1 bronze streaming table  
# MAGIC **Target variable:** `churn_labels.churned` (boolean)  
# MAGIC **Generated:** from `generate_ndjson.py` → SDP pipeline (bronze → silver)
# MAGIC
# MAGIC ## Key Findings Summary
# MAGIC
# MAGIC | Finding | Detail |
# MAGIC |---------|--------|
# MAGIC | **Dataset size** | 500 customers, ~22K total records across 5 tables |
# MAGIC | **Data quality** | Zero nulls in all columns, all tables. Pristine synthetic data. |
# MAGIC | **Class balance** | 18.8% churned (94) vs 81.2% active (406) — moderate imbalance |
# MAGIC | **Join topology** | `customer_id` is universal key. 1:1 profiles↔labels. 1:many for usage/billing/support |
# MAGIC | **Strongest signals** | `avg_sessions` (3.3x), `overdue_rate` (3.8x), `escalation_rate` (3.7x), `plan_type` (37% free → 2.5% enterprise) |
# MAGIC | **Weakest signals** | `region` (~uniform churn), `feature_usage` depth (nearly identical), `tenure` (small delta) |

# COMMAND ----------

# DBTITLE 1,Configuration
CATALOG = "hls_fde_dev"
SCHEMA = "dev_matthew_giglia_mlops_workshop"
CS = f"{CATALOG}.{SCHEMA}"

TABLES = [
    "customer_profiles",
    "product_usage_events",
    "billing_history",
    "support_interactions",
    "churn_labels",
]

# COMMAND ----------

# DBTITLE 1,Table Inventory & Row Counts
# MAGIC %sql
# MAGIC SELECT
# MAGIC   table_name,
# MAGIC   table_type,
# MAGIC   comment
# MAGIC FROM hls_fde_dev.information_schema.tables
# MAGIC WHERE table_schema = 'dev_matthew_giglia_mlops_workshop'
# MAGIC   AND table_name NOT LIKE '__materialization%'
# MAGIC   AND table_name NOT LIKE 'event_log%'
# MAGIC ORDER BY table_name

# COMMAND ----------

# DBTITLE 1,Row Counts & Schema Overview
from pyspark.sql import functions as F

print("=" * 60)
print("TABLE ROW COUNTS")
print("=" * 60)
for t in TABLES:
    fqn = f"{CS}.{t}"
    cnt = spark.table(fqn).count()
    print(f"  {t:.<40s} {cnt:>8,}")

print("\n" + "=" * 60)
print("TABLE SCHEMAS")
print("=" * 60)
for t in TABLES:
    fqn = f"{CS}.{t}"
    df = spark.table(fqn)
    print(f"\n--- {t} ---")
    for field in df.schema.fields:
        print(f"  {field.name:.<35s} {str(field.dataType):>20s}  nullable={field.nullable}")

# COMMAND ----------

# DBTITLE 1,Data Quality — Schema-Wide
# MAGIC %md
# MAGIC ## 1. Data Quality
# MAGIC
# MAGIC **Zero nulls across all columns in all 5 tables.** This is clean synthetic data — no imputation needed.
# MAGIC
# MAGIC All 500 customers appear in every table. No orphan records in any direction.

# COMMAND ----------

# DBTITLE 1,Null Check — All Tables
print("=" * 60)
print("NULL COUNTS PER COLUMN PER TABLE")
print("=" * 60)
for t in TABLES:
    fqn = f"{CS}.{t}"
    df = spark.table(fqn)
    print(f"\n--- {t} ---")
    for c in df.columns:
        n = df.filter(F.col(c).isNull()).count()
        print(f"  {c:.<35s} {n}")

# COMMAND ----------

# DBTITLE 1,Join Topology
# MAGIC %md
# MAGIC ## 2. Join Topology
# MAGIC
# MAGIC All tables join on `customer_id` (string, format `C00001`–`C00500`).
# MAGIC
# MAGIC | Relationship | Left | Right | Cardinality | Grain |
# MAGIC |---|---|---|---|---|
# MAGIC | Profile ↔ Label | `customer_profiles` | `churn_labels` | **1:1** | per customer |
# MAGIC | Profile → Usage | `customer_profiles` | `product_usage_events` | **1:many** (avg 16.6) | per customer per day |
# MAGIC | Profile → Billing | `customer_profiles` | `billing_history` | **1:many** (avg 19.0) | per month |
# MAGIC | Profile → Support | `customer_profiles` | `support_interactions` | **1:many** (avg 6.9) | per ticket |
# MAGIC
# MAGIC **Referential integrity is perfect** — zero orphan records in any direction.

# COMMAND ----------

# DBTITLE 1,Verify Referential Integrity
cp = spark.table(f"{CS}.customer_profiles")
cl = spark.table(f"{CS}.churn_labels")
ue = spark.table(f"{CS}.product_usage_events")
bh = spark.table(f"{CS}.billing_history")
si = spark.table(f"{CS}.support_interactions")

print("Referential integrity checks:")
for name, df in [("usage_events", ue), ("billing_history", bh), ("support_interactions", si), ("churn_labels", cl)]:
    orphans = df.join(cp, "customer_id", "left_anti").count()
    missing = cp.join(df, "customer_id", "left_anti").count()
    print(f"  {name:.<35s} orphans={orphans}, missing={missing}")

print(f"\n  Labels per customer (should be 1):")
cl.groupBy("customer_id").count().select(
    F.min("count").alias("min"), F.max("count").alias("max")
).show()

# COMMAND ----------

# DBTITLE 1,Target Variable Analysis
# MAGIC %md
# MAGIC ## 3. Target Variable — `churn_labels.churned`
# MAGIC
# MAGIC **Class balance:** 18.8% churned (94) vs 81.2% active (406)  
# MAGIC **Observation window:** Last 30 days (2026-08-25 to 2026-09-24)  
# MAGIC **One label per customer** (no duplicates)
# MAGIC
# MAGIC This is moderately imbalanced. We'll want to consider:
# MAGIC * Stratified train/test splits
# MAGIC * F1 as the primary metric (over accuracy)
# MAGIC * Possibly class weights or SMOTE (though 94 positive examples is reasonable for 500 total)

# COMMAND ----------

# DBTITLE 1,Target Variable Distribution
labels = spark.table(f"{CS}.churn_labels").select("customer_id", "churned", "observation_date")

print("Class balance:")
labels.groupBy("churned").agg(
    F.count("*").alias("count"),
    F.round(F.count("*") / labels.count() * 100, 1).alias("pct")
).orderBy("churned").show(truncate=False)

print("Observation date range:")
labels.select(
    F.min("observation_date").alias("earliest"),
    F.max("observation_date").alias("latest")
).show()

# COMMAND ----------

# DBTITLE 1,Customer Profiles — Distributions
# MAGIC %md
# MAGIC ## 4. Customer Profiles — Distributions
# MAGIC
# MAGIC **500 customers**, signup dates spanning Oct 2023 to Jun 2026.
# MAGIC
# MAGIC | Dimension | Distribution |
# MAGIC |---|---|
# MAGIC | **Plan type** | starter 37%, pro 29%, free 18%, enterprise 16% |
# MAGIC | **Region** | us-east 37%, eu 24%, us-west 24%, apac 15% |
# MAGIC | **Company size** | 11–50 (30%), 51–200 (26%), 1–10 (23%), 201–1000 (15%), 1000+ (5%) |

# COMMAND ----------

# DBTITLE 1,Customer Profile Distributions
profiles = spark.table(f"{CS}.customer_profiles")

print("Plan type distribution:")
profiles.groupBy("plan_type").count().orderBy("count", ascending=False).show(truncate=False)

print("Region distribution:")
profiles.groupBy("region").count().orderBy("count", ascending=False).show(truncate=False)

print("Company size distribution:")
profiles.groupBy("company_size").count().orderBy("count", ascending=False).show(truncate=False)

print("Signup date range:")
profiles.select(
    F.min("signup_date").alias("earliest"),
    F.max("signup_date").alias("latest"),
    F.round(F.avg(F.datediff(F.current_date(), F.col("signup_date"))), 0).alias("avg_tenure_days")
).show()

# COMMAND ----------

# DBTITLE 1,Feature Candidates — Strong Signals
# MAGIC %md
# MAGIC ## 5. Feature Candidates — Churn vs Active Comparison
# MAGIC
# MAGIC ### Strong Signals (ranked by discriminative power)
# MAGIC
# MAGIC | Feature | Active | Churned | Ratio | Signal Strength |
# MAGIC |---------|--------|---------|-------|-----------------|
# MAGIC | **Overdue payment rate** | 8.9% | 34.1% | 3.8x | Very strong |
# MAGIC | **Escalation rate** | 9.6% | 35.3% | 3.7x | Very strong |
# MAGIC | **Avg daily sessions** | 12.6 | 3.8 | 3.3x | Very strong |
# MAGIC | **Avg API calls** | 100.0 | 37.9 | 2.6x | Very strong |
# MAGIC | **Usage event count** | 18.7 | 7.4 | 2.5x | Very strong |
# MAGIC | **Support tickets** | 5.5 | 13.1 | 2.4x | Strong |
# MAGIC | **Plan type churn rate** | free=37%, starter=25%, pro=8%, enterprise=2.5% | — | ordinal | Strong |
# MAGIC | **Avg invoice amount** | $204.7 | $52.7 | 3.9x | Strong (but correlated with plan) |
# MAGIC | **Overdue count** | 1.6 | 6.2 | 3.9x | Strong |
# MAGIC | **Escalated tickets** | 0.5 | 4.5 | 9.0x | Very strong |
# MAGIC
# MAGIC ### Weak Signals
# MAGIC
# MAGIC | Feature | Active | Churned | Note |
# MAGIC |---------|--------|---------|------|
# MAGIC | Region | ~18–20% churn across all | uniform | No regional effect |
# MAGIC | Feature usage depth | 2.50 features/event | 2.48 | Negligible difference |
# MAGIC | Feature adoption mix | ~16–17% per feature | ~16–17% | No feature preference difference |
# MAGIC | Tenure | 594 days | 559 days | Small delta, weak signal |

# COMMAND ----------

# DBTITLE 1,Churn Rate by Plan Type
churn = spark.table(f"{CS}.churn_labels").select("customer_id", "churned")
profiles = spark.table(f"{CS}.customer_profiles")

print("CHURN RATE BY PLAN TYPE")
profiles.join(churn, "customer_id").groupBy("plan_type").agg(
    F.count("*").alias("total"),
    F.sum(F.when(F.col("churned"), 1).otherwise(0)).alias("churned"),
    F.round(F.sum(F.when(F.col("churned"), 1).otherwise(0)) / F.count("*") * 100, 1).alias("churn_rate_pct")
).orderBy("churn_rate_pct", ascending=False).show(truncate=False)

print("CHURN RATE BY REGION")
profiles.join(churn, "customer_id").groupBy("region").agg(
    F.count("*").alias("total"),
    F.sum(F.when(F.col("churned"), 1).otherwise(0)).alias("churned"),
    F.round(F.sum(F.when(F.col("churned"), 1).otherwise(0)) / F.count("*") * 100, 1).alias("churn_rate_pct")
).orderBy("churn_rate_pct", ascending=False).show(truncate=False)

print("CHURN RATE BY COMPANY SIZE")
profiles.join(churn, "customer_id").groupBy("company_size").agg(
    F.count("*").alias("total"),
    F.sum(F.when(F.col("churned"), 1).otherwise(0)).alias("churned"),
    F.round(F.sum(F.when(F.col("churned"), 1).otherwise(0)) / F.count("*") * 100, 1).alias("churn_rate_pct")
).orderBy("churn_rate_pct", ascending=False).show(truncate=False)

# COMMAND ----------

# DBTITLE 1,Usage Metrics by Churn Status
usage = spark.table(f"{CS}.product_usage_events")
churn = spark.table(f"{CS}.churn_labels").select("customer_id", "churned")

print("USAGE METRICS BY CHURN STATUS")
usage_agg = usage.groupBy("customer_id").agg(
    F.avg("session_count").alias("avg_sessions"),
    F.avg("api_calls").alias("avg_api_calls"),
    F.count("*").alias("usage_event_count"),
    F.max("session_count").alias("max_sessions"),
)
usage_agg.join(churn, "customer_id").groupBy("churned").agg(
    F.round(F.avg("avg_sessions"), 1).alias("avg_sessions"),
    F.round(F.avg("avg_api_calls"), 1).alias("avg_api_calls"),
    F.round(F.avg("usage_event_count"), 1).alias("avg_event_count"),
    F.round(F.avg("max_sessions"), 1).alias("avg_max_sessions")
).orderBy("churned").show(truncate=False)

# COMMAND ----------

# DBTITLE 1,Billing Metrics by Churn Status
billing = spark.table(f"{CS}.billing_history")
churn = spark.table(f"{CS}.churn_labels").select("customer_id", "churned")

print("BILLING METRICS BY CHURN STATUS")
billing_agg = billing.groupBy("customer_id").agg(
    F.sum("amount").alias("total_revenue"),
    F.avg("amount").alias("avg_invoice"),
    F.count("*").alias("invoice_count"),
    F.sum(F.when(F.col("payment_status") == "overdue", 1).otherwise(0)).alias("overdue_count"),
    F.sum(F.when(F.col("payment_status") == "pending", 1).otherwise(0)).alias("pending_count"),
)
billing_agg.join(churn, "customer_id").groupBy("churned").agg(
    F.round(F.avg("total_revenue"), 1).alias("avg_total_revenue"),
    F.round(F.avg("avg_invoice"), 1).alias("avg_invoice_amt"),
    F.round(F.avg("invoice_count"), 1).alias("avg_invoices"),
    F.round(F.avg("overdue_count"), 1).alias("avg_overdue"),
    F.round(F.avg("pending_count"), 1).alias("avg_pending"),
).orderBy("churned").show(truncate=False)

print("\nOVERDUE RATE BY CHURN STATUS")
billing_agg_rate = billing_agg.withColumn("overdue_rate", F.col("overdue_count") / F.col("invoice_count"))
billing_agg_rate.join(churn, "customer_id").groupBy("churned").agg(
    F.round(F.avg("overdue_rate") * 100, 1).alias("avg_overdue_rate_pct")
).orderBy("churned").show(truncate=False)

# COMMAND ----------

# DBTITLE 1,Support Metrics by Churn Status
support = spark.table(f"{CS}.support_interactions")
churn = spark.table(f"{CS}.churn_labels").select("customer_id", "churned")

print("SUPPORT METRICS BY CHURN STATUS")
support_agg = support.groupBy("customer_id").agg(
    F.count("*").alias("ticket_count"),
    F.sum(F.when(F.col("resolution") == "escalated", 1).otherwise(0)).alias("escalated_count"),
    F.sum(F.when(F.col("resolution") == "pending", 1).otherwise(0)).alias("pending_tickets"),
    F.sum(F.when(F.col("resolution") == "resolved", 1).otherwise(0)).alias("resolved_count"),
)
support_agg.join(churn, "customer_id").groupBy("churned").agg(
    F.round(F.avg("ticket_count"), 1).alias("avg_tickets"),
    F.round(F.avg("escalated_count"), 1).alias("avg_escalated"),
    F.round(F.avg("pending_tickets"), 1).alias("avg_pending"),
    F.round(F.avg("resolved_count"), 1).alias("avg_resolved"),
).orderBy("churned").show(truncate=False)

print("\nESCALATION RATE BY CHURN STATUS")
support_agg_rate = support_agg.withColumn(
    "escalation_rate", F.col("escalated_count") / F.col("ticket_count")
)
support_agg_rate.join(churn, "customer_id").groupBy("churned").agg(
    F.round(F.avg("escalation_rate") * 100, 1).alias("avg_escalation_rate_pct")
).orderBy("churned").show(truncate=False)

# COMMAND ----------

# DBTITLE 1,Feature Usage Depth & Adoption
usage = spark.table(f"{CS}.product_usage_events")
churn = spark.table(f"{CS}.churn_labels").select("customer_id", "churned")

print("FEATURE USAGE DEPTH BY CHURN STATUS")
feature_depth = usage.withColumn(
    "feature_count", F.size(F.split(F.col("feature_usage"), ","))
)
feature_depth.join(churn, "customer_id").groupBy("churned").agg(
    F.round(F.avg("feature_count"), 2).alias("avg_features_per_event"),
    F.min("feature_count").alias("min_features"),
    F.max("feature_count").alias("max_features"),
).orderBy("churned").show(truncate=False)

print("\nFEATURE ADOPTION (exploded) BY CHURN STATUS")
exploded = usage.withColumn("feature", F.explode(F.split(F.col("feature_usage"), ",")))
exploded_w_churn = exploded.join(churn, "customer_id")
churn_totals = exploded_w_churn.groupBy("churned").agg(F.count("*").alias("total"))
feature_counts = exploded_w_churn.groupBy("churned", "feature").agg(F.count("*").alias("cnt"))
feature_pcts = feature_counts.join(churn_totals, "churned").withColumn(
    "pct", F.round(F.col("cnt") / F.col("total") * 100, 1)
).select("churned", "feature", "cnt", "pct")

print("Active customers:")
feature_pcts.filter(~F.col("churned")).orderBy("pct", ascending=False).show(10, truncate=False)
print("Churned customers:")
feature_pcts.filter(F.col("churned")).orderBy("pct", ascending=False).show(10, truncate=False)

# COMMAND ----------

# DBTITLE 1,Tenure by Churn Status
profiles = spark.table(f"{CS}.customer_profiles")
churn = spark.table(f"{CS}.churn_labels").select("customer_id", "churned")

print("TENURE (days since signup) BY CHURN STATUS")
tenure = profiles.withColumn("tenure_days", F.datediff(F.current_date(), F.col("signup_date")))
tenure.join(churn, "customer_id").groupBy("churned").agg(
    F.round(F.avg("tenure_days"), 0).alias("avg_tenure_days"),
    F.min("tenure_days").alias("min_tenure"),
    F.max("tenure_days").alias("max_tenure"),
    F.percentile_approx("tenure_days", 0.5).alias("median_tenure"),
).orderBy("churned").show(truncate=False)

# COMMAND ----------

# DBTITLE 1,Recommendations for Modeling
# MAGIC %md
# MAGIC ## 6. Recommendations for Modeling
# MAGIC
# MAGIC ### Recommended Feature Views (aligned with `PROJECT_MEMORY.md`)
# MAGIC
# MAGIC The planned Feature Views map directly to the strongest signals found here:
# MAGIC
# MAGIC | Feature View | Source Table | Aggregation | Window | EDA Signal Strength |
# MAGIC |---|---|---|---|---|
# MAGIC | `avg_daily_sessions_30d` | `product_usage_events` | Avg(session_count) | Tumbling 30d | Very strong (3.3x) |
# MAGIC | `support_tickets_7d` | `support_interactions` | Count(ticket_id) | Sliding 7d/1d | Strong (2.4x) |
# MAGIC | `total_revenue_90d` | `billing_history` | Sum(amount) | Tumbling 90d | Strong (3.9x revenue gap) |
# MAGIC | `max_api_calls_7d` | `product_usage_events` | Max(api_calls) | Sliding 7d/1d | Very strong (2.6x) |
# MAGIC | `overdue_payment_count` | `billing_history` | Count(\*) where overdue | Tumbling 90d | Very strong (3.8x rate) |
# MAGIC | `escalated_tickets_30d` | `support_interactions` | Count(\*) where escalated | Tumbling 30d | Very strong (9.0x count) |
# MAGIC
# MAGIC ### Additional Static Features (from `customer_profiles`)
# MAGIC
# MAGIC * `plan_type` — strong ordinal signal (free → enterprise maps to 37% → 2.5% churn)
# MAGIC * `company_size` — moderate signal (1000+ has only 3.7% churn)
# MAGIC * `tenure_days` — weak but usable as a control variable
# MAGIC * `region` — drop or use only as a stratification variable (no predictive power)
# MAGIC
# MAGIC ### Modeling Notes
# MAGIC
# MAGIC 1. **Class imbalance handling:** 18.8% positive rate is manageable. Use `class_weight='balanced'` or stratified splits rather than SMOTE.
# MAGIC 2. **Feature correlation:** `avg_invoice_amt` is highly correlated with `plan_type` (plan determines price band). Keep one or the other, not both.
# MAGIC 3. **Temporal features are key:** All 6 Feature Views use time windows, which will capture behavioral degradation before churn.
# MAGIC 4. **Feature-usage depth** and **feature adoption mix** add no signal — exclude from the model.
# MAGIC 5. **Data quality is perfect** — no preprocessing/imputation needed beyond encoding categoricals.

# COMMAND ----------

# DBTITLE 1,Entity Relationship Diagram (text)
# MAGIC %md
# MAGIC ## Appendix: Entity Relationship Diagram
# MAGIC
# MAGIC ```
# MAGIC                           ┌─────────────────────┐
# MAGIC                           │  customer_profiles   │
# MAGIC                           │─────────────────────│
# MAGIC                           │ customer_id (PK)     │
# MAGIC                           │ signup_date          │
# MAGIC                           │ plan_type            │
# MAGIC                           │ region               │
# MAGIC                           │ company_size         │
# MAGIC                           └──────────┬──────────┘
# MAGIC                                      │
# MAGIC            ┌───────────┬──────────┼──────────┬──────────┐
# MAGIC            │           │          │          │          │
# MAGIC     ┌──────┴─────┐ ┌───┴──────┐ ┌┴─────────┐ ┌┴─────────┐
# MAGIC     │ product_     │ │ billing_   │ │ support_   │ │ churn_     │
# MAGIC     │ usage_events │ │ history    │ │ interact.. │ │ labels     │
# MAGIC     │─────────────│ │───────────│ │───────────│ │───────────│
# MAGIC     │ customer_id  │ │ customer_id│ │ customer_id│ │ customer_id│
# MAGIC     │ event_date   │ │ billing_   │ │ ticket_id  │ │ observation│
# MAGIC     │ session_count│ │   date     │ │ created_at │ │   _date    │
# MAGIC     │ feature_usage│ │ amount     │ │ category   │ │ churned    │
# MAGIC     │ api_calls    │ │ payment_   │ │ resolution │ └───────────┘
# MAGIC     └─────────────┘ │   status   │ └───────────┘
# MAGIC      1:many         └───────────┘  1:many        1:1
# MAGIC      avg 16.6/cust   1:many
# MAGIC                      avg 19/cust   avg 6.9/cust
# MAGIC ```

# COMMAND ----------

# DBTITLE 1,Statistical Deep Dive
# MAGIC %md
# MAGIC ## 7. Statistical Deep Dive
# MAGIC
# MAGIC Build a unified customer-level feature matrix, then examine:
# MAGIC 1. **Correlation matrix** with heatmap — identify redundant feature pairs
# MAGIC 2. **Variance Inflation Factor (VIF)** — quantify multicollinearity
# MAGIC 3. **Distribution analysis** — histograms + KDE by churn status
# MAGIC 4. **Box plots** — outlier detection per feature, split by churn

# COMMAND ----------

# DBTITLE 1,Build Unified Feature Matrix
import pandas as pd
import numpy as np

# --- Assemble one row per customer with all candidate features ---
profiles = spark.table(f"{CS}.customer_profiles")
usage    = spark.table(f"{CS}.product_usage_events")
billing  = spark.table(f"{CS}.billing_history")
support  = spark.table(f"{CS}.support_interactions")
labels   = spark.table(f"{CS}.churn_labels")

# Profile features
profile_df = profiles.withColumn(
    "tenure_days", F.datediff(F.current_date(), F.col("signup_date"))
).select("customer_id", "plan_type", "region", "company_size", "tenure_days")

# Usage aggregates
usage_agg = usage.groupBy("customer_id").agg(
    F.avg("session_count").alias("avg_sessions"),
    F.avg("api_calls").alias("avg_api_calls"),
    F.max("session_count").alias("max_sessions"),
    F.max("api_calls").alias("max_api_calls"),
    F.count("*").alias("usage_event_count"),
    F.avg(F.size(F.split("feature_usage", ","))).alias("avg_feature_depth"),
)

# Billing aggregates
billing_agg = billing.groupBy("customer_id").agg(
    F.sum("amount").alias("total_revenue"),
    F.avg("amount").alias("avg_invoice"),
    F.count("*").alias("invoice_count"),
    F.sum(F.when(F.col("payment_status") == "overdue", 1).otherwise(0)).alias("overdue_count"),
    F.sum(F.when(F.col("payment_status") == "pending", 1).otherwise(0)).alias("pending_count"),
)
billing_agg = billing_agg.withColumn(
    "overdue_rate", F.col("overdue_count") / F.col("invoice_count")
)

# Support aggregates
support_agg = support.groupBy("customer_id").agg(
    F.count("*").alias("ticket_count"),
    F.sum(F.when(F.col("resolution") == "escalated", 1).otherwise(0)).alias("escalated_count"),
    F.sum(F.when(F.col("resolution") == "pending", 1).otherwise(0)).alias("pending_tickets"),
)
support_agg = support_agg.withColumn(
    "escalation_rate", F.col("escalated_count") / F.col("ticket_count")
)

# Labels
label_df = labels.select(
    "customer_id",
    F.col("churned").cast("int").alias("churned")
)

# Join everything
feature_matrix = (
    profile_df
    .join(usage_agg, "customer_id")
    .join(billing_agg, "customer_id")
    .join(support_agg, "customer_id")
    .join(label_df, "customer_id")
)

# Convert to pandas for statistical analysis
pdf = feature_matrix.toPandas()

# Encode plan_type ordinally (free < starter < pro < enterprise)
plan_order = {"free": 0, "starter": 1, "pro": 2, "enterprise": 3}
pdf["plan_type_ord"] = pdf["plan_type"].map(plan_order)

print(f"Feature matrix: {pdf.shape[0]} rows x {pdf.shape[1]} columns")
print(f"\nNumeric columns for correlation analysis:")
numeric_cols = pdf.select_dtypes(include=[np.number]).columns.tolist()
for c in numeric_cols:
    print(f"  {c}")

# COMMAND ----------

# DBTITLE 1,Correlation Matrix Heatmap
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams.update({"figure.dpi": 120, "font.size": 9})

# Select numeric features (drop customer_id)
numeric_cols = [
    "tenure_days", "plan_type_ord", "avg_sessions", "avg_api_calls",
    "max_sessions", "max_api_calls", "usage_event_count", "avg_feature_depth",
    "total_revenue", "avg_invoice", "invoice_count", "overdue_count",
    "pending_count", "overdue_rate", "ticket_count", "escalated_count",
    "pending_tickets", "escalation_rate", "churned",
]

corr = pdf[numeric_cols].corr()

fig, ax = plt.subplots(figsize=(14, 11))
im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")

# Labels
ax.set_xticks(range(len(numeric_cols)))
ax.set_yticks(range(len(numeric_cols)))
ax.set_xticklabels(numeric_cols, rotation=45, ha="right", fontsize=8)
ax.set_yticklabels(numeric_cols, fontsize=8)

# Annotate cells
for i in range(len(numeric_cols)):
    for j in range(len(numeric_cols)):
        val = corr.iloc[i, j]
        color = "white" if abs(val) > 0.6 else "black"
        ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                fontsize=6, color=color)

fig.colorbar(im, ax=ax, shrink=0.8, label="Pearson r")
ax.set_title("Feature Correlation Matrix", fontsize=13, fontweight="bold")
fig.tight_layout()
display(fig)
plt.close(fig)

# COMMAND ----------

# DBTITLE 1,Top Correlated Pairs & Collinearity Flags
# --- Pairwise correlation ranking (|r| > 0.5, excluding self) ---
pairs = []
for i in range(len(numeric_cols)):
    for j in range(i + 1, len(numeric_cols)):
        r = corr.iloc[i, j]
        pairs.append((numeric_cols[i], numeric_cols[j], round(r, 3)))

pairs_df = pd.DataFrame(pairs, columns=["feature_a", "feature_b", "r"])
pairs_df["abs_r"] = pairs_df["r"].abs()
high_corr = pairs_df[pairs_df["abs_r"] >= 0.5].sort_values("abs_r", ascending=False)

print(f"Feature pairs with |r| >= 0.5  ({len(high_corr)} pairs)")
print("=" * 65)
display(high_corr.reset_index(drop=True))

# COMMAND ----------

# DBTITLE 1,Variance Inflation Factor (VIF)
# Compute VIF manually: VIF_j = 1 / (1 - R²_j) where R²_j is from
# regressing feature j on all other features (uses numpy lstsq)

feature_cols = [
    "tenure_days", "plan_type_ord", "avg_sessions", "avg_api_calls",
    "max_sessions", "max_api_calls", "usage_event_count", "avg_feature_depth",
    "total_revenue", "avg_invoice", "invoice_count", "overdue_count",
    "pending_count", "overdue_rate", "ticket_count", "escalated_count",
    "pending_tickets", "escalation_rate",
]

X = pdf[feature_cols].dropna().values
n = X.shape[1]
vifs = []
for j in range(n):
    y_j = X[:, j]
    X_others = np.delete(X, j, axis=1)
    X_aug = np.column_stack([np.ones(X_others.shape[0]), X_others])
    coeffs, residuals, _, _ = np.linalg.lstsq(X_aug, y_j, rcond=None)
    y_hat = X_aug @ coeffs
    ss_res = np.sum((y_j - y_hat) ** 2)
    ss_tot = np.sum((y_j - y_j.mean()) ** 2)
    r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    vifs.append(1 / (1 - r_sq) if r_sq < 1 else float("inf"))

vif_data = pd.DataFrame({"feature": feature_cols, "VIF": [round(v, 1) for v in vifs]})
vif_data = vif_data.sort_values("VIF", ascending=False)
vif_data["flag"] = vif_data["VIF"].apply(
    lambda v: "HIGH (>10)" if v > 10 else ("MODERATE (5-10)" if v > 5 else "OK")
)

print("Variance Inflation Factors")
print("VIF > 10 = severe multicollinearity, 5-10 = moderate, <5 = acceptable")
print("=" * 55)
display(vif_data.reset_index(drop=True))

# COMMAND ----------

# DBTITLE 1,Distribution Analysis — Histograms by Churn
# Key features to plot distributions for
plot_features = [
    "avg_sessions", "avg_api_calls", "usage_event_count",
    "total_revenue", "avg_invoice", "overdue_rate",
    "ticket_count", "escalated_count", "escalation_rate",
    "tenure_days", "plan_type_ord", "avg_feature_depth",
]

fig, axes = plt.subplots(4, 3, figsize=(15, 14))
axes = axes.flatten()

active = pdf[pdf["churned"] == 0]
churned = pdf[pdf["churned"] == 1]

for idx, feat in enumerate(plot_features):
    ax = axes[idx]
    ax.hist(active[feat], bins=25, alpha=0.6, label="Active", color="#1B3139", density=True)
    ax.hist(churned[feat], bins=25, alpha=0.6, label="Churned", color="#FF3621", density=True)
    ax.set_title(feat, fontsize=9, fontweight="bold")
    ax.set_ylabel("density", fontsize=7)
    ax.tick_params(labelsize=7)
    if idx == 0:
        ax.legend(fontsize=7)

fig.suptitle("Feature Distributions — Active vs Churned", fontsize=13, fontweight="bold", y=1.01)
fig.tight_layout()
display(fig)
plt.close(fig)

# COMMAND ----------

# DBTITLE 1,Box Plots — Outlier Detection by Churn
box_features = [
    "avg_sessions", "avg_api_calls", "overdue_rate",
    "escalation_rate", "ticket_count", "total_revenue",
]

fig, axes = plt.subplots(2, 3, figsize=(14, 8))
axes = axes.flatten()

for idx, feat in enumerate(box_features):
    ax = axes[idx]
    data = [active[feat].dropna(), churned[feat].dropna()]
    bp = ax.boxplot(data, labels=["Active", "Churned"], patch_artist=True,
                    widths=0.5, medianprops={"color": "black", "linewidth": 1.5})
    bp["boxes"][0].set_facecolor("#1B3139")
    bp["boxes"][0].set_alpha(0.6)
    bp["boxes"][1].set_facecolor("#FF3621")
    bp["boxes"][1].set_alpha(0.6)
    ax.set_title(feat, fontsize=10, fontweight="bold")
    ax.tick_params(labelsize=8)

fig.suptitle("Box Plots — Active vs Churned (outlier detection)",
             fontsize=13, fontweight="bold", y=1.01)
fig.tight_layout()
display(fig)
plt.close(fig)

# COMMAND ----------

# DBTITLE 1,Correlation with Target — Ranked
# Point-biserial correlation with churned (same as Pearson for binary target)
target_corr = pdf[numeric_cols].corr()["churned"].drop("churned").abs().sort_values(ascending=False)

fig, ax = plt.subplots(figsize=(10, 6))
colors = ["#FF3621" if v >= 0.3 else "#1B3139" if v >= 0.15 else "#A0B0B8" for v in target_corr.values]
ax.barh(range(len(target_corr)), target_corr.values, color=colors)
ax.set_yticks(range(len(target_corr)))
ax.set_yticklabels(target_corr.index, fontsize=9)
ax.invert_yaxis()
ax.set_xlabel("|Pearson r| with churned", fontsize=10)
ax.set_title("Feature Correlation with Churn Target (absolute)", fontsize=12, fontweight="bold")
ax.axvline(x=0.3, color="#FF3621", linestyle="--", alpha=0.5, label="strong (|r|≥0.3)")
ax.axvline(x=0.15, color="#1B3139", linestyle="--", alpha=0.5, label="moderate (|r|≥0.15)")
ax.legend(fontsize=8)

for i, v in enumerate(target_corr.values):
    ax.text(v + 0.005, i, f"{v:.3f}", va="center", fontsize=7)

fig.tight_layout()
display(fig)
plt.close(fig)

# COMMAND ----------

# DBTITLE 1,Collinearity & Feature Selection Summary
# MAGIC %md
# MAGIC ## 8. Collinearity & Feature Selection Summary
# MAGIC
# MAGIC ### High Collinearity Clusters (action required)
# MAGIC
# MAGIC From the correlation matrix, VIF analysis, and pairwise rankings:
# MAGIC
# MAGIC | Cluster | Features | Action |
# MAGIC |---------|----------|--------|
# MAGIC | **Usage intensity** | `avg_sessions` ↔ `max_sessions` ↔ `usage_event_count` | Keep `avg_sessions` (strongest target correlation). Drop `max_sessions` and `usage_event_count`. |
# MAGIC | **API activity** | `avg_api_calls` ↔ `max_api_calls` | Keep `avg_api_calls`. Drop `max_api_calls`. |
# MAGIC | **Revenue / plan** | `total_revenue` ↔ `avg_invoice` ↔ `plan_type_ord` | Keep `plan_type_ord` (categorical, interpretable) + `total_revenue`. Drop `avg_invoice`. |
# MAGIC | **Billing health** | `overdue_count` ↔ `overdue_rate` ↔ `pending_count` | Keep `overdue_rate` (normalized). Drop raw counts. |
# MAGIC | **Support distress** | `ticket_count` ↔ `escalated_count` ↔ `pending_tickets` ↔ `escalation_rate` | Keep `escalation_rate` + `ticket_count`. Drop `escalated_count` and `pending_tickets`. |
# MAGIC
# MAGIC ### Recommended Final Feature Set
# MAGIC
# MAGIC **Strong (keep):**
# MAGIC * `avg_sessions` — usage engagement proxy
# MAGIC * `avg_api_calls` — technical engagement
# MAGIC * `overdue_rate` — billing health signal
# MAGIC * `escalation_rate` — support distress signal
# MAGIC * `ticket_count` — support volume
# MAGIC * `total_revenue` — customer value
# MAGIC * `plan_type_ord` — plan tier (ordinal)
# MAGIC
# MAGIC **Weak but include as controls:**
# MAGIC * `tenure_days` — account age
# MAGIC * `company_size` — (encode ordinally for model)
# MAGIC
# MAGIC **Drop:**
# MAGIC * `region` — no predictive power
# MAGIC * `avg_feature_depth` — no signal
# MAGIC * `max_sessions`, `max_api_calls` — redundant with averages
# MAGIC * `avg_invoice` — redundant with plan/revenue
# MAGIC * `overdue_count`, `pending_count` — redundant with rate
# MAGIC * `escalated_count`, `pending_tickets` — redundant with rate + count
# MAGIC * `invoice_count` — no meaningful variance
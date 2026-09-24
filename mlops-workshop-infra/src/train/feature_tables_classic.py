# Databricks notebook source
# DBTITLE 1,Classic Feature Tables — Customer Churn Model
# MAGIC %md
# MAGIC # Classic Feature Tables — Customer Churn Model
# MAGIC
# MAGIC Classic Feature Store pattern: manually compute features via PySpark, store in **feature tables** (Delta + primary keys), assemble training sets with `FeatureLookup`. Compare with the declarative Feature Views approach in `feature_definitions.py`.
# MAGIC
# MAGIC **9 features:** 6 time-windowed aggregations + 3 static profile features
# MAGIC
# MAGIC | Feature | Computation | Window |
# MAGIC |---|---|---|
# MAGIC | `avg_daily_sessions_30d` | AVG(session_count) | 30d |
# MAGIC | `max_api_calls_7d` | MAX(api_calls) | 7d |
# MAGIC | `total_revenue_90d` | SUM(amount) | 90d |
# MAGIC | `overdue_payment_count_90d` | COUNT WHERE overdue | 90d |
# MAGIC | `support_tickets_7d` | COUNT(ticket_id) | 7d |
# MAGIC | `escalated_tickets_30d` | COUNT WHERE escalated | 30d |
# MAGIC | `plan_type_encoded` | Ordinal (free=0..enterprise=3) | static |
# MAGIC | `company_size_encoded` | Ordinal (1-10=0..1000+=4) | static |
# MAGIC | `tenure_days` | datediff(today, signup_date) | static |

# COMMAND ----------

# DBTITLE 1,Install dependencies
# MAGIC %pip install --upgrade databricks-sdk mlflow databricks-feature-engineering>=0.16.0
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Parameters & client
dbutils.widgets.text("catalog", "hls_fde_dev")
dbutils.widgets.text("schema", "dev_matthew_giglia_mlops_workshop")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
CS = f"{catalog}.{schema}"

from databricks.feature_engineering import FeatureEngineeringClient

fe = FeatureEngineeringClient()
print(f"Target: {CS}")

# COMMAND ----------

# DBTITLE 1,Compute time-windowed features
from pyspark.sql import functions as F

labels = spark.table(f"{CS}.churn_labels").select("customer_id", "observation_date")
usage = spark.table(f"{CS}.product_usage_events")
billing = spark.table(f"{CS}.billing_history")
support = spark.table(f"{CS}.support_interactions")

# ═══ Usage features (30d and 7d windows) ══════════════════════════════
# Conditional aggregation: F.when returns NULL outside the window;
# AVG/MAX/COUNT ignore NULLs, giving per-window results.

usage_features = (
    labels.join(usage, on="customer_id")
    .groupBy("customer_id", "observation_date")
    .agg(
        F.avg(F.when(
            F.col("event_date").between(
                F.date_sub("observation_date", 30), F.col("observation_date")
            ), F.col("session_count"),
        )).alias("avg_daily_sessions_30d"),
        F.max(F.when(
            F.col("event_date").between(
                F.date_sub("observation_date", 7), F.col("observation_date")
            ), F.col("api_calls"),
        )).alias("max_api_calls_7d"),
    )
)

# ═══ Billing features (90d window) ═════════════════════════════════

billing_features = (
    labels.join(billing, on="customer_id")
    .groupBy("customer_id", "observation_date")
    .agg(
        F.sum(F.when(
            F.col("billing_date").between(
                F.date_sub("observation_date", 90), F.col("observation_date")
            ), F.col("amount"),
        )).alias("total_revenue_90d"),
        F.count(F.when(
            (F.col("billing_date").between(
                F.date_sub("observation_date", 90), F.col("observation_date")
            )) & (F.col("payment_status") == "overdue"),
            True,
        )).alias("overdue_payment_count_90d"),
    )
)

# ═══ Support features (7d and 30d windows) ══════════════════════════

support_features = (
    labels.join(support, on="customer_id")
    .groupBy("customer_id", "observation_date")
    .agg(
        F.count(F.when(
            F.col("created_at").cast("date").between(
                F.date_sub("observation_date", 7), F.col("observation_date")
            ), F.col("ticket_id"),
        )).alias("support_tickets_7d"),
        F.count(F.when(
            (F.col("created_at").cast("date").between(
                F.date_sub("observation_date", 30), F.col("observation_date")
            )) & (F.col("resolution") == "escalated"),
            F.col("ticket_id"),
        )).alias("escalated_tickets_30d"),
    )
)

print("✓ Time-windowed features computed (6 features across 3 domains)")

# COMMAND ----------

# DBTITLE 1,Compute static profile features
profiles = spark.table(f"{CS}.customer_profiles")

profile_features = (
    profiles
    .withColumn(
        "plan_type_encoded",
        F.when(F.col("plan_type") == "free", 0)
         .when(F.col("plan_type") == "starter", 1)
         .when(F.col("plan_type") == "pro", 2)
         .when(F.col("plan_type") == "enterprise", 3),
    )
    .withColumn(
        "company_size_encoded",
        F.when(F.col("company_size") == "1-10", 0)
         .when(F.col("company_size") == "11-50", 1)
         .when(F.col("company_size") == "51-200", 2)
         .when(F.col("company_size") == "201-1000", 3)
         .when(F.col("company_size") == "1000+", 4),
    )
    .withColumn("tenure_days", F.datediff(F.current_date(), F.col("signup_date")))
    .select("customer_id", "plan_type_encoded", "company_size_encoded", "tenure_days")
)

print(f"✓ Profile features: {profile_features.count():,} rows")
display(profile_features.limit(5))

# COMMAND ----------

# DBTITLE 1,Assemble & create feature tables
# ── Join windowed features into one DataFrame ─────────────────────
windowed_features = (
    usage_features
    .join(billing_features, on=["customer_id", "observation_date"], how="left")
    .join(support_features, on=["customer_id", "observation_date"], how="left")
    .fillna(0)
    .withColumn("observation_date", F.col("observation_date").cast("timestamp"))
)

print(f"✓ Windowed features assembled: {windowed_features.count():,} rows")

# ── Time series feature table (6 windowed features) ─────────────
WINDOWED_TABLE = f"{CS}.churn_windowed_features"

try:
    fe.create_table(
        name=WINDOWED_TABLE,
        primary_keys=["customer_id", "observation_date"],
        timeseries_column="observation_date",
        df=windowed_features,
        schema=windowed_features.schema,
        description="Time-windowed churn features: usage, billing, support aggregations",
    )
    print(f"  ✓ {WINDOWED_TABLE} (created)")
except Exception as e:
    if "already exists" in str(e).lower():
        fe.write_table(name=WINDOWED_TABLE, df=windowed_features, mode="overwrite")
        print(f"  ✓ {WINDOWED_TABLE} (overwritten)")
    else:
        raise

# ── Static feature table (3 profile features) ───────────────────
PROFILE_TABLE = f"{CS}.churn_profile_features"

try:
    fe.create_table(
        name=PROFILE_TABLE,
        primary_keys=["customer_id"],
        df=profile_features,
        schema=profile_features.schema,
        description="Static customer profile features: plan type, company size, tenure",
    )
    print(f"  ✓ {PROFILE_TABLE} (created)")
except Exception as e:
    if "already exists" in str(e).lower():
        fe.write_table(name=PROFILE_TABLE, df=profile_features, mode="overwrite")
        print(f"  ✓ {PROFILE_TABLE} (overwritten)")
    else:
        raise

# COMMAND ----------

# DBTITLE 1,Verify feature tables
print("=" * 65)
print("VERIFICATION — Feature tables in Unity Catalog")
print("=" * 65)

# Compute schema once outside the loop (Spark Connect best practice)
table_names = [WINDOWED_TABLE, PROFILE_TABLE]
table_info = [(name, spark.table(name)) for name in table_names]

for name, df in table_info:
    print(f"\n  {name}")
    print(f"    Rows: {df.count():,}  |  Columns: {df.columns}")

print("\n" + "=" * 65)
print("✓ Both feature tables verified")
print("=" * 65)

# COMMAND ----------

# DBTITLE 1,FeatureLookup training set assembly
from databricks.feature_engineering import FeatureLookup

# ── Define lookups ─────────────────────────────────────────────────
feature_lookups = [
    # Time-windowed features (point-in-time via timestamp_lookup_key)
    FeatureLookup(
        table_name=WINDOWED_TABLE,
        lookup_key="customer_id",
        timestamp_lookup_key="observation_date",
        feature_names=[
            "avg_daily_sessions_30d", "max_api_calls_7d",
            "total_revenue_90d", "overdue_payment_count_90d",
            "support_tickets_7d", "escalated_tickets_30d",
        ],
    ),
    # Static profile features (no timestamp — latest value)
    FeatureLookup(
        table_name=PROFILE_TABLE,
        lookup_key="customer_id",
        feature_names=[
            "plan_type_encoded", "company_size_encoded", "tenure_days",
        ],
    ),
]

# ── Build training set ─────────────────────────────────────────────
labels_df = (
    spark.table(f"{CS}.churn_labels")
    .withColumn("observation_date", F.col("observation_date").cast("timestamp"))
)

training_set = fe.create_training_set(
    df=labels_df,
    feature_lookups=feature_lookups,
    label="churned",
)

training_df = training_set.load_df()
print(f"✓ Training set: {training_df.count():,} rows × {len(training_df.columns)} columns")
print(f"  Columns: {training_df.columns}")
display(training_df.limit(5))
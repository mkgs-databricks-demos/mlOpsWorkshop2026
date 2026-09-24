# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# dependencies = [
#   "databricks-sdk==0.141.0",
#   "mlflow==3.16.1",
#   "databricks-feature-engineering==0.18.0",
# ]
# ///
# DBTITLE 1,Feature Definitions — Customer Churn Model
# MAGIC %md
# MAGIC # Feature Definitions — Customer Churn Model
# MAGIC
# MAGIC Declarative Feature Views using `databricks-feature-engineering >= 0.16.0`. Defines **6 time-windowed aggregation features** from silver materialized views and registers them as governed Unity Catalog objects. Static features (`plan_type`, `company_size`, `tenure_days`) are joined and encoded in the training notebook via `fe.create_training_set()`.
# MAGIC
# MAGIC | Feature | Source | Aggregation | Window |
# MAGIC |---|---|---|---|
# MAGIC | `avg_daily_sessions_30d` | product_usage_events | Avg(session_count) | Tumbling 30d |
# MAGIC | `max_api_calls_7d` | product_usage_events | Max(api_calls) | Sliding 7d/1d |
# MAGIC | `total_revenue_90d` | billing_history | Sum(amount) | Tumbling 90d |
# MAGIC | `overdue_payment_count_90d` | billing_history (overdue) | Count(billing_date) | Tumbling 90d |
# MAGIC | `support_tickets_7d` | support_interactions | Count(ticket_id) | Sliding 7d/1d |
# MAGIC | `escalated_tickets_30d` | support_interactions (escalated) | Count(ticket_id) | Tumbling 30d |

# COMMAND ----------

# DBTITLE 1,Parameters & client
dbutils.widgets.text("catalog", "hls_fde_dev")
dbutils.widgets.text("schema", "dev_matthew_giglia_mlops_workshop")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

from databricks.feature_engineering import FeatureEngineeringClient

fe = FeatureEngineeringClient()
print(f"Target: {catalog}.{schema}")

# COMMAND ----------

# DBTITLE 1,Define DeltaTableSources
from databricks.feature_engineering.entities import DeltaTableSource

# ── Create helper views that cast DATE → TIMESTAMP ───────────────
# Feature Views internally calls unix_micros() which requires TIMESTAMP.
# These lightweight views don't store data — just query transformations.

spark.sql(f"""
    CREATE OR REPLACE VIEW {catalog}.{schema}.product_usage_events_fv AS
    SELECT customer_id, CAST(event_date AS TIMESTAMP) AS event_date,
           session_count, feature_usage, api_calls
    FROM {catalog}.{schema}.product_usage_events
""")

spark.sql(f"""
    CREATE OR REPLACE VIEW {catalog}.{schema}.billing_history_fv AS
    SELECT customer_id, CAST(billing_date AS TIMESTAMP) AS billing_date,
           amount, payment_status
    FROM {catalog}.{schema}.billing_history
""")

spark.sql(f"""
    CREATE OR REPLACE VIEW {catalog}.{schema}.billing_history_overdue_fv AS
    SELECT customer_id, CAST(billing_date AS TIMESTAMP) AS billing_date,
           amount, payment_status
    FROM {catalog}.{schema}.billing_history
    WHERE payment_status = 'overdue'
""")

print("✓ 3 helper views created (DATE → TIMESTAMP cast)")

# ── Product usage events ─────────────────────────────────────────
usage_source = DeltaTableSource(
    catalog_name=catalog, schema_name=schema,
    table_name="product_usage_events_fv",
)

# ── Billing history — all records ─────────────────────────────────
billing_source = DeltaTableSource(
    catalog_name=catalog, schema_name=schema,
    table_name="billing_history_fv",
)

# ── Billing history — overdue payments only ───────────────────────
billing_overdue_source = DeltaTableSource(
    catalog_name=catalog, schema_name=schema,
    table_name="billing_history_overdue_fv",
)

# ── Support interactions — all tickets ────────────────────────────
# created_at is already TIMESTAMP — no cast needed
support_source = DeltaTableSource(
    catalog_name=catalog, schema_name=schema,
    table_name="support_interactions",
)

# ── Support interactions — escalated only ─────────────────────────
support_escalated_source = DeltaTableSource(
    catalog_name=catalog, schema_name=schema,
    table_name="support_interactions",
    filter_condition="resolution = 'escalated'",
)

print("✓ 5 DeltaTableSource objects defined")

# COMMAND ----------

# DBTITLE 1,Define 6 Feature objects
from databricks.feature_engineering.entities import (
    Feature, AggregationFunction,
    Avg, Max, Sum, Count,
    TumblingWindow, SlidingWindow,
)
from datetime import timedelta

# ═══ Usage features (source: product_usage_events) ═════════════════

avg_daily_sessions_30d = Feature(
    source=usage_source,
    function=AggregationFunction(
        Avg(input="session_count"),
        TumblingWindow(window_duration=timedelta(days=30)),
    ),
    entity=["customer_id"],
    timeseries_column="event_date",
    name="avg_daily_sessions_30d",
)

max_api_calls_7d = Feature(
    source=usage_source,
    function=AggregationFunction(
        Max(input="api_calls"),
        SlidingWindow(
            window_duration=timedelta(days=7),
            slide_duration=timedelta(days=1),
        ),
    ),
    entity=["customer_id"],
    timeseries_column="event_date",
    name="max_api_calls_7d",
)

# ═══ Billing features (source: billing_history) ═══════════════════

total_revenue_90d = Feature(
    source=billing_source,
    function=AggregationFunction(
        Sum(input="amount"),
        TumblingWindow(window_duration=timedelta(days=90)),
    ),
    entity=["customer_id"],
    timeseries_column="billing_date",
    name="total_revenue_90d",
)

overdue_payment_count_90d = Feature(
    source=billing_overdue_source,
    function=AggregationFunction(
        Count(input="amount"),  # not billing_date — it's the timeseries col (renamed internally)
        TumblingWindow(window_duration=timedelta(days=90)),
    ),
    entity=["customer_id"],
    timeseries_column="billing_date",
    name="overdue_payment_count_90d",
)

# ═══ Support features (source: support_interactions) ═══════════════

support_tickets_7d = Feature(
    source=support_source,
    function=AggregationFunction(
        Count(input="ticket_id"),
        SlidingWindow(
            window_duration=timedelta(days=7),
            slide_duration=timedelta(days=1),
        ),
    ),
    entity=["customer_id"],
    timeseries_column="created_at",
    name="support_tickets_7d",
)

escalated_tickets_30d = Feature(
    source=support_escalated_source,
    function=AggregationFunction(
        Count(input="ticket_id"),
        TumblingWindow(window_duration=timedelta(days=30)),
    ),
    entity=["customer_id"],
    timeseries_column="created_at",
    name="escalated_tickets_30d",
)

# ── Collect all features ───────────────────────────────────────────
ALL_FEATURES = [
    avg_daily_sessions_30d,
    max_api_calls_7d,
    total_revenue_90d,
    overdue_payment_count_90d,
    support_tickets_7d,
    escalated_tickets_30d,
]

print(f"✓ {len(ALL_FEATURES)} Feature objects defined:")
for f in ALL_FEATURES:
    print(f"  • {f.name}")

# COMMAND ----------

# DBTITLE 1,Compute & validate features
from pyspark.sql import functions as F

print("=" * 65)
print("FEATURE VALIDATION — computing against source data")
print("=" * 65)

for feature in ALL_FEATURES:
    df = fe.compute_features(features=[feature])
    row_count = df.count()
    print(f"\n  {feature.name}")
    print(f"    Rows: {row_count:,}  |  Columns: {df.columns}")

print("\n" + "=" * 65)
print("✓ All 6 Feature definitions validated")
print("=" * 65)

# COMMAND ----------

# DBTITLE 1,Register features to Unity Catalog
print("=" * 65)
print("REGISTERING FEATURES TO UNITY CATALOG")
print("=" * 65)

for feature in ALL_FEATURES:
    full_name = f"{catalog}.{schema}.{feature.name}"

    try:
        fe.register_feature(
            feature=feature, catalog_name=catalog, schema_name=schema,
        )
        print(f"  ✓ {full_name} (registered)")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"  ✓ {full_name} (already registered)")
        else:
            raise

print(f"\n✓ {len(ALL_FEATURES)} features registered to {catalog}.{schema}")

# COMMAND ----------

# DBTITLE 1,Verify UC registration
print("=" * 65)
print("VERIFICATION — confirming UC registration")
print("=" * 65)

for feature in ALL_FEATURES:
    full_name = f"{catalog}.{schema}.{feature.name}"
    registered = fe.get_feature(full_name=full_name)
    print(f"  ✓ {registered.name}")

print(f"\n{'=' * 65}")
print("Feature definitions complete.")
print()
print("Static features (plan_type, company_size, tenure_days) will be")
print("joined and encoded in the training notebook via")
print("fe.create_training_set().")
print(f"{'=' * 65}")
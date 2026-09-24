"""Silver layer — typed, record-specific materialized views.

Each view reads from bronze_unified, filters by record_type,
and extracts typed fields from the JSON payload.
"""

from pyspark import pipelines as dp


@dp.materialized_view(
    name="customer_profiles",
    comment="Customer profile data extracted from bronze",
)
def customer_profiles():
    return spark.sql("""
        SELECT
            parse_json(payload):customer_id::STRING   AS customer_id,
            parse_json(payload):signup_date::DATE     AS signup_date,
            parse_json(payload):plan_type::STRING     AS plan_type,
            parse_json(payload):region::STRING        AS region,
            parse_json(payload):company_size::STRING  AS company_size,
            source,
            ingested_at
        FROM bronze_unified
        WHERE record_type = 'customer_profile'
    """)


@dp.materialized_view(
    name="product_usage_events",
    comment="Product usage events extracted from bronze",
)
def product_usage_events():
    return spark.sql("""
        SELECT
            parse_json(payload):customer_id::STRING      AS customer_id,
            parse_json(payload):event_date::DATE         AS event_date,
            parse_json(payload):session_count::INT       AS session_count,
            parse_json(payload):feature_usage::STRING    AS feature_usage,
            parse_json(payload):api_calls::INT           AS api_calls,
            source,
            ingested_at
        FROM bronze_unified
        WHERE record_type = 'usage_event'
    """)


@dp.materialized_view(
    name="billing_history",
    comment="Billing records extracted from bronze",
)
def billing_history():
    return spark.sql("""
        SELECT
            parse_json(payload):customer_id::STRING        AS customer_id,
            parse_json(payload):billing_date::DATE        AS billing_date,
            parse_json(payload):amount::DOUBLE            AS amount,
            parse_json(payload):payment_status::STRING    AS payment_status,
            source,
            ingested_at
        FROM bronze_unified
        WHERE record_type = 'billing'
    """)


@dp.materialized_view(
    name="support_interactions",
    comment="Support ticket interactions extracted from bronze",
)
def support_interactions():
    return spark.sql("""
        SELECT
            parse_json(payload):customer_id::STRING    AS customer_id,
            parse_json(payload):ticket_id::STRING      AS ticket_id,
            parse_json(payload):created_at::TIMESTAMP  AS created_at,
            parse_json(payload):category::STRING       AS category,
            parse_json(payload):resolution::STRING     AS resolution,
            source,
            ingested_at
        FROM bronze_unified
        WHERE record_type = 'support_interaction'
    """)


@dp.materialized_view(
    name="churn_labels",
    comment="Churn label observations extracted from bronze",
)
def churn_labels():
    return spark.sql("""
        SELECT
            parse_json(payload):customer_id::STRING         AS customer_id,
            parse_json(payload):observation_date::DATE     AS observation_date,
            parse_json(payload):churned::BOOLEAN           AS churned,
            source,
            ingested_at
        FROM bronze_unified
        WHERE record_type = 'churn_label'
    """)

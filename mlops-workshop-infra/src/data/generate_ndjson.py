# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Parameters
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume_path = dbutils.widgets.get("volume_path")

print(f"Catalog:     {catalog}")
print(f"Schema:      {schema}")
print(f"Volume path: {volume_path}")

# COMMAND ----------

# DBTITLE 1,Configuration
import json
import random
import uuid
from datetime import datetime, timedelta

random.seed(42)  # Reproducible for workshop

NUM_CUSTOMERS = 500
TODAY = datetime.now().date()
THREE_YEARS_AGO = TODAY - timedelta(days=3 * 365)

PLAN_TYPES = ["free", "starter", "pro", "enterprise"]
PLAN_WEIGHTS = [0.20, 0.35, 0.30, 0.15]

REGIONS = ["us-east", "us-west", "eu", "apac"]
REGION_WEIGHTS = [0.35, 0.25, 0.25, 0.15]

COMPANY_SIZES = ["1-10", "11-50", "51-200", "201-1000", "1000+"]
SIZE_WEIGHTS = [0.25, 0.30, 0.25, 0.15, 0.05]

BILLING_AMOUNTS = {
    "free": (0, 0),
    "starter": (29, 49),
    "pro": (99, 199),
    "enterprise": (499, 999),
}

SUPPORT_CATEGORIES = ["billing", "technical", "feature_request", "account", "bug"]
RESOLUTIONS = ["resolved", "escalated", "pending", "closed"]

FEATURES_LIST = ["dashboard", "reports", "api", "export", "integrations", "alerts"]

# COMMAND ----------

# DBTITLE 1,Generate synthetic records
def random_date(start, end):
    """Random date between start and end (inclusive)."""
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(0, delta)))


def generate_customers():
    """Generate customer profiles with plan-dependent churn probability."""
    churn_rates = {"free": 0.35, "starter": 0.25, "pro": 0.12, "enterprise": 0.05}
    customers = []
    for i in range(1, NUM_CUSTOMERS + 1):
        plan = random.choices(PLAN_TYPES, weights=PLAN_WEIGHTS, k=1)[0]
        signup = random_date(THREE_YEARS_AGO, TODAY - timedelta(days=90))
        churned = random.random() < churn_rates[plan]
        customers.append({
            "customer_id": f"C{i:05d}",
            "signup_date": signup.isoformat(),
            "plan_type": plan,
            "region": random.choices(REGIONS, weights=REGION_WEIGHTS, k=1)[0],
            "company_size": random.choices(COMPANY_SIZES, weights=SIZE_WEIGHTS, k=1)[0],
            "_churned": churned,
            "_signup_date": signup,
        })
    return customers


def generate_usage_events(customers):
    """Usage events — churned customers show declining sessions and fewer API calls."""
    base_sessions = {"free": 3, "starter": 8, "pro": 15, "enterprise": 25}
    records = []
    for c in customers:
        n = random.randint(3, 12) if c["_churned"] else random.randint(8, 30)
        for _ in range(n):
            sessions = max(1, int(random.gauss(base_sessions[c["plan_type"]], 5)))
            if c["_churned"]:
                sessions = max(1, sessions // 2)
            records.append({
                "record_type": "usage_event",
                "customer_id": c["customer_id"],
                "event_date": random_date(c["_signup_date"], TODAY).isoformat(),
                "session_count": sessions,
                "feature_usage": ",".join(random.sample(FEATURES_LIST, k=random.randint(1, 4))),
                "api_calls": max(0, int(random.gauss(30 if c["_churned"] else 100, 50))),
            })
    return records


def generate_billing(customers):
    """Monthly billing — churned customers have higher overdue rates."""
    records = []
    for c in customers:
        lo, hi = BILLING_AMOUNTS[c["plan_type"]]
        cursor = (c["_signup_date"].replace(day=1) + timedelta(days=32)).replace(day=1)
        overdue_w = [0.50, 0.35, 0.15] if c["_churned"] else [0.85, 0.08, 0.07]
        while cursor <= TODAY:
            records.append({
                "record_type": "billing",
                "customer_id": c["customer_id"],
                "billing_date": cursor.isoformat(),
                "amount": round(random.uniform(lo, hi), 2) if hi > 0 else 0.0,
                "payment_status": random.choices(
                    ["paid", "overdue", "pending"], weights=overdue_w, k=1
                )[0],
            })
            cursor = (cursor + timedelta(days=32)).replace(day=1)
    return records


def generate_support(customers):
    """Support tickets — churned customers have more, especially escalated."""
    records = []
    for c in customers:
        n = random.randint(5, 20) if c["_churned"] else random.randint(1, 10)
        res_w = [0.25, 0.35, 0.15, 0.25] if c["_churned"] else [0.50, 0.10, 0.15, 0.25]
        for _ in range(n):
            ts_date = random_date(c["_signup_date"], TODAY)
            ts = f"{ts_date.isoformat()}T{random.randint(8,18):02d}:{random.randint(0,59):02d}:00"
            records.append({
                "record_type": "support_interaction",
                "customer_id": c["customer_id"],
                "ticket_id": str(uuid.uuid4()),
                "created_at": ts,
                "category": random.choice(SUPPORT_CATEGORIES),
                "resolution": random.choices(RESOLUTIONS, weights=res_w, k=1)[0],
            })
    return records


def generate_churn_labels(customers):
    """One observation per customer — recent observation date."""
    return [
        {
            "record_type": "churn_label",
            "customer_id": c["customer_id"],
            "observation_date": random_date(TODAY - timedelta(days=30), TODAY).isoformat(),
            "churned": c["_churned"],
        }
        for c in customers
    ]


# ── Generate all records ──
customers = generate_customers()
churned_count = sum(1 for c in customers if c["_churned"])
print(f"Customers: {len(customers)} ({churned_count} churned, {len(customers) - churned_count} active)")

profiles = [
    {
        "record_type": "customer_profile",
        "customer_id": c["customer_id"],
        "signup_date": c["signup_date"],
        "plan_type": c["plan_type"],
        "region": c["region"],
        "company_size": c["company_size"],
    }
    for c in customers
]

usage = generate_usage_events(customers)
billing = generate_billing(customers)
support = generate_support(customers)
labels = generate_churn_labels(customers)

all_records = {
    "customer_profile": profiles,
    "usage_event": usage,
    "billing": billing,
    "support_interaction": support,
    "churn_label": labels,
}

for rt, recs in all_records.items():
    print(f"  {rt:.<30s} {len(recs):>6,} records")
print(f"  {'TOTAL':.<30s} {sum(len(v) for v in all_records.values()):>6,} records")

# COMMAND ----------

# DBTITLE 1,Write NDJSON to landing volume
import os
import shutil

# Write directly to the landing volume — each job task runs on separate
# serverless compute so /tmp/ is NOT shared between tasks.
# UC volumes are accessible at /Volumes/... via the local filesystem.

# Clean existing subdirectories for idempotency
# (can't rmtree the volume root — it's a managed mount point)
if os.path.exists(volume_path):
    for item in os.listdir(volume_path):
        item_path = os.path.join(volume_path, item)
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)

for record_type, records in all_records.items():
    dest_dir = os.path.join(volume_path, record_type)
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, f"{record_type}.ndjson")
    with open(path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    size_kb = os.path.getsize(path) / 1024
    print(f"  {record_type}/{record_type}.ndjson  ({len(records):>6,} records, {size_kb:,.1f} KB)")

print(f"\nAll NDJSON files written to {volume_path}")

# COMMAND ----------

# DBTITLE 1,Set task values for downstream
total = sum(len(v) for v in all_records.values())

dbutils.jobs.taskValues.set(key="ndjson_path", value=volume_path)
dbutils.jobs.taskValues.set(key="record_count", value=total)

print(f"Task values set:")
print(f"  ndjson_path  = {volume_path}")
print(f"  record_count = {total:,}")
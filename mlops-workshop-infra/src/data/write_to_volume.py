# Databricks notebook source
# DBTITLE 1,Parameters
volume_path = dbutils.widgets.get("volume_path")
print(f"Volume path: {volume_path}")

# COMMAND ----------

# DBTITLE 1,Read upstream task value
ndjson_path = dbutils.jobs.taskValues.get(
    taskKey="generate_ndjson",
    key="ndjson_path",
    default="/tmp/mlops-workshop/ndjson",
    debugValue="/tmp/mlops-workshop/ndjson",
)
print(f"Source NDJSON path: {ndjson_path}")

# COMMAND ----------

# DBTITLE 1,Copy NDJSON to volume partitioned by record_type
import os
import shutil

# List NDJSON files from local temp path (Python native I/O for serverless compatibility)
ndjson_files = [f for f in os.listdir(ndjson_path) if f.endswith(".ndjson")]
print(f"Found {len(ndjson_files)} NDJSON files in {ndjson_path}\n")

# Clean landing zone for idempotency
# UC volumes are directly accessible at /Volumes/... on the local filesystem
if os.path.exists(volume_path):
    shutil.rmtree(volume_path)
os.makedirs(volume_path, exist_ok=True)

for fname in ndjson_files:
    record_type = fname.replace(".ndjson", "")
    dest_dir = os.path.join(volume_path, record_type)
    os.makedirs(dest_dir, exist_ok=True)
    src = os.path.join(ndjson_path, fname)
    dest = os.path.join(dest_dir, fname)
    shutil.copy2(src, dest)
    print(f"  {fname} \u2192 {dest}")

print(f"\nAll NDJSON files staged to {volume_path}")

# COMMAND ----------

# DBTITLE 1,Verify landing volume contents
print("Landing volume contents:\n")
total_bytes = 0
for d in sorted(os.listdir(volume_path)):
    d_path = os.path.join(volume_path, d)
    if os.path.isdir(d_path):
        for fname in sorted(os.listdir(d_path)):
            fpath = os.path.join(d_path, fname)
            size = os.path.getsize(fpath)
            total_bytes += size
            print(f"  {d}/{fname:<35s} {size:>10,} bytes")

print(f"\nTotal: {total_bytes / 1024:,.1f} KB")
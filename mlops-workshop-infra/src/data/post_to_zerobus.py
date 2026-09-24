# Databricks notebook source
# DBTITLE 1,Parameters
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Catalog: {catalog}")
print(f"Schema:  {schema}")

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

# DBTITLE 1,Post to ZeroBus (not yet implemented)
# TODO: Implement when ZeroBus SDK is available
#
# Expected flow:
#   1. Read NDJSON files from ndjson_path
#   2. Initialize ZeroBus client with credentials from secret scope
#   3. POST records to ZeroBus API endpoint
#   4. ZeroBus writes to bronze_zerobus streaming table in the SDP pipeline
#
# Credentials:
#   token = dbutils.secrets.get(scope="mlops-workshop", key="zerobus_token")
#
# Example (pending SDK):
#   from zerobus import ZeroBusClient
#   client = ZeroBusClient(token=token)
#   for record_type_file in dbutils.fs.ls(f"file:{ndjson_path}"):
#       with open(record_type_file.path.replace("file:", "")) as f:
#           for line in f:
#               client.publish(topic="mlops-workshop", payload=line.strip())

print("ZeroBus path is not yet implemented.")
print("Use the Auto Loader path (use_zerobus=false) for now.")
print("\nTo enable: set use_zerobus=true once ZeroBus SDK + secret scope are configured.")
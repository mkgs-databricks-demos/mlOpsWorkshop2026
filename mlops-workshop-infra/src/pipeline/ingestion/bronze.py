"""Bronze layer — Auto Loader ingestion and unified view.

Defines streaming tables for raw record ingestion and a temporary view
that merges all bronze sources for downstream silver consumption.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

# Volume path is passed via pipeline configuration block
volume_path = spark.conf.get("volume_path")


@dp.table(
    name="bronze_autoload",
    comment="Raw records ingested via Auto Loader from landing volume",
)
@dp.expect_or_drop("valid_payload", "payload IS NOT NULL")
def bronze_autoload():
    """Stream NDJSON files from the landing volume.

    Uses text format to read each JSON line as-is, avoiding cross-record-type
    schema inference. Extracts record_type from the JSON string and stores
    the raw line as payload for downstream silver extraction.
    """
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "text")
        .option("recursiveFileLookup", "true")
        .load(volume_path)
        .select(
            F.get_json_object(F.col("value"), "$.record_type").alias("record_type"),
            F.col("value").alias("payload"),
            F.current_timestamp().alias("ingested_at"),
        )
    )


@dp.table(
    name="bronze_zerobus",
    comment="Raw records ingested via ZeroBus API (placeholder)",
)
def bronze_zerobus():
    """Placeholder streaming table for the ZeroBus ingestion path.

    Returns an empty DataFrame with the expected bronze schema.
    Replace with a real ZeroBus source when the SDK is available.
    """
    return spark.createDataFrame(
        [], "record_type STRING, payload STRING, ingested_at TIMESTAMP"
    )


@dp.temporary_view()
def bronze_unified():
    """Merge all bronze sources into a single view with a source column."""
    autoload = spark.read.table("bronze_autoload").withColumn(
        "source", F.lit("autoload")
    )
    zerobus = spark.read.table("bronze_zerobus").withColumn(
        "source", F.lit("zerobus")
    )
    return autoload.unionByName(zerobus)

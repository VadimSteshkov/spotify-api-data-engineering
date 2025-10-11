#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generic Spark Structured Streaming job (modular ops version).

- Reads JSON events from Kafka (topics provided via env: SPARK_KAFKA_TOPICS or KAFKA_TOPICS).
- Picks operator by SPARK_MODE via spark.ops.registry (top_artists | top_tracks | feature_avg).
- Optionally overrides SPARK_MODE, topn, feature, group based on TEAM_CONFIG_SPARK and APP_PREFIX.
- Writes results to MongoDB collection: <APP_PREFIX>_spark_<mode>.
- Also prints aggregates to console for live demo.
- Resilient to mixed schemas sent by teammates (fields can be null/string/JSON-array).
"""

# tabs are used in this file
import os
import yaml
from typing import List

from dotenv import load_dotenv
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
	StructType, StructField, StringType, LongType, ArrayType, DoubleType
)

# ---------------------------
# Load environment variables
# ---------------------------
load_dotenv()

APP_PREFIX = os.getenv("APP_PREFIX", "demo").strip()

# Kafka topic selection
SPARK_KAFKA_TOPICS = os.getenv("SPARK_KAFKA_TOPICS", "").strip()
KAFKA_TOPICS = SPARK_KAFKA_TOPICS or os.getenv("KAFKA_TOPICS", "events").strip()

# Base Spark mode configuration
SPARK_MODE = os.getenv("SPARK_MODE", "top_artists").strip()  # top_artists | top_tracks | feature_avg
SPARK_TOPN = int(os.getenv("SPARK_TOPN", "10").strip() or "10")
SPARK_FEATURE = os.getenv("SPARK_FEATURE", "track_duration_ms").strip()
SPARK_GROUP = os.getenv("SPARK_GROUP", "market_used").strip()  # comma-separated grouping cols

# Kafka & Mongo configuration
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092").strip()
MONGO_URL = os.getenv("MONGO_URL", "mongodb://root:example@localhost:27017/?authSource=admin").strip()
MONGO_DB = os.getenv("MONGO_DB", "spotify_db").strip()
OUT_COLL = f"{APP_PREFIX}_spark_{SPARK_MODE}"

SPARK_PACKAGES = os.getenv(
	"SPARK_PACKAGES",
	"org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.kafka:kafka-clients:3.5.2",
)

print(f"[Spark] bootstrap: {KAFKA_BOOTSTRAP}")
print(f"[Spark] topics: {KAFKA_TOPICS.split(',')}")
print(f"[Spark] mode (initial): {SPARK_MODE}")

# ---------------------------
# Load team config (per APP_PREFIX)
# ---------------------------
def load_spark_team_config() -> dict:
	"""
	Load Spark team config with robust path resolution:
	- prefer TEAM_CONFIG_SPARK env
	- then try 'spark/team_config.yaml' (when /app == src/)
	- then try 'src/spark/team_config.yaml' (when /app == repo root)
	"""
	candidates = []
	cfg_env = os.getenv("TEAM_CONFIG_SPARK", "").strip()
	if cfg_env:
		candidates.append(cfg_env)

	candidates += [
		"spark/team_config.yaml",
		"src/spark/team_config.yaml",
	]

	for p in candidates:
		if os.path.exists(p):
			try:
				with open(p, "r", encoding="utf-8") as f:
					return yaml.safe_load(f) or {}
			except Exception as e:
				print(f"[Spark] WARN: failed to parse Spark team config '{p}': {e}")
				return {}

	print(f"[Spark] WARN: TEAM_CONFIG_SPARK not found in any of: {candidates}")
	return {}

SPARK_TEAM_CFG = load_spark_team_config()

# Override SPARK_MODE / params based on team config for this APP_PREFIX
if SPARK_TEAM_CFG and "teams" in SPARK_TEAM_CFG:
	team_cfg = SPARK_TEAM_CFG["teams"].get(APP_PREFIX, {})
	if team_cfg:
		SPARK_MODE = team_cfg.get("mode", SPARK_MODE)
		SPARK_TOPN = int(team_cfg.get("topn", SPARK_TOPN))
		SPARK_FEATURE = team_cfg.get("feature", SPARK_FEATURE)
		SPARK_GROUP = team_cfg.get("group", SPARK_GROUP)
		print(f"[Spark] using team config for prefix '{APP_PREFIX}': {team_cfg}")

OUT_COLL = f"{APP_PREFIX}_spark_{SPARK_MODE}"

# ---------------------------
# Spark session
# ---------------------------
spark = (
	SparkSession.builder
		.appName(f"{APP_PREFIX}_kafka_to_mongo_{SPARK_MODE}")
		.config("spark.sql.shuffle.partitions", "2")
		.config("spark.jars.packages", SPARK_PACKAGES)
		.getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")

# ---------------------------
# Kafka source
# ---------------------------
df_raw = (
	spark.readStream
		.format("kafka")
		.option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
		.option("subscribe", KAFKA_TOPICS)  # comma-separated list supported
		.option("startingOffsets", "latest")
		.load()
)

df_json_str = df_raw.select(
	F.col("timestamp").alias("kafka_ts"),
	F.col("value").cast("string").alias("raw_json")
)

# ---------------------------
# Base schema (keep fields generic & safe)
# ---------------------------
event_schema = StructType([
	StructField("user_id", StringType(), True),
	StructField("track_id", StringType(), True),
	StructField("track_name", StringType(), True),
	StructField("artist_ids", StringType(), True),
	StructField("artist_names", StringType(), True),
	StructField("album_name", StringType(), True),
	StructField("market_used", StringType(), True),
	StructField("played_at", StringType(), True),
	StructField("track_duration_ms", LongType(), True),

	# Optional feature-style fields colleagues might send (keep them as strings; we cast later)
	StructField("danceability", StringType(), True),
	StructField("energy", StringType(), True),
	StructField("valence", StringType(), True),
])

df_parsed = df_json_str.select(
	F.from_json(F.col("raw_json"), event_schema, {"mode": "PERMISSIVE"}).alias("d"),
	"kafka_ts"
).select("kafka_ts", "d.*")

# ---------------------------
# Registry (ops)
# ---------------------------
from spark.ops.registry import OPS

def _normalize_array_like(col: F.Column) -> F.Column:
	json_arr = F.from_json(col, ArrayType(StringType()))
	return (
		F.when(col.isNull(), F.array().cast("array<string>"))
		 .when(col.startswith("["), json_arr)
		 .when(F.instr(col, ",") > 0, F.split(col, r"\s*,\s*"))
		 .otherwise(F.array(col.cast("string")))
	)

df_norm = (
	df_parsed
		.withColumn("artist_names", F.col("artist_names").cast(StringType()))
		.withColumn("artist_ids", F.col("artist_ids").cast(StringType()))
)

# Operator config
op_cfg = {
	"feature": SPARK_FEATURE,
	"group": SPARK_GROUP,
	"topn": SPARK_TOPN,
}

if SPARK_MODE not in OPS:
	raise RuntimeError(f"Unknown SPARK_MODE '{SPARK_MODE}'. Available: {list(OPS.keys())}")

op_fn = OPS[SPARK_MODE]
df_out = op_fn(df_norm, op_cfg)

# ---------------------------
# Mongo sink via foreachBatch
# ---------------------------
def write_batch_to_mongo(batch_df: DataFrame, batch_id: int) -> None:
	"""
	For each micro-batch, insert result rows into MongoDB as documents.
	Extra fields are added for traceability.
	"""
	import pymongo
	from pymongo import MongoClient

	rows = [r.asDict(recursive=True) for r in batch_df.collect()]
	if not rows:
		return

	client = MongoClient(MONGO_URL)
	try:
		coll = client[MONGO_DB][OUT_COLL]
		for r in rows:
			r["batch_id"] = batch_id
			r["prefix"] = APP_PREFIX
			r["mode"] = SPARK_MODE
			if SPARK_MODE == "feature_avg":
				r["feature"] = SPARK_FEATURE
				r["group"] = SPARK_GROUP
		coll.insert_many(rows, ordered=False)
	finally:
		client.close()

# ---------------------------
# Dual sink: console + Mongo
# ---------------------------
query_console = (
	df_out.writeStream
		.outputMode("complete")
		.format("console")
		.option("truncate", "false")
		.option("numRows", "50")
		.start()
)

query_mongo = (
	df_out.writeStream
		.outputMode("complete")
		.foreachBatch(write_batch_to_mongo)
		.option("checkpointLocation", f"/tmp/{APP_PREFIX}_spark_{SPARK_MODE}_ck")
		.start()
)

query_console.awaitTermination()
query_mongo.awaitTermination()


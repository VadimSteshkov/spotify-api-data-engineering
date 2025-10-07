#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generic Spark Structured Streaming job.

- Reads JSON events from Kafka (topics provided via env: SPARK_KAFKA_TOPICS or KAFKA_TOPICS).
- Supports multiple aggregation "modes" (env SPARK_MODE):
	* top_artists  -> Top-N by artist_names
	* top_tracks   -> Top-N by track_name
	* feature_avg  -> Average of a numeric field (SPARK_FEATURE), grouped by SPARK_GROUP
- Writes results to MongoDB collection: <APP_PREFIX>_spark_<mode>
- Prints aggregates to console for live demo.

Design goals:
- Portable (no Mongo Spark connector; uses foreachBatch + PyMongo).
- Robust to mixed schemas sent by teammates (fields can be null/string/JSON-array).
- No hardcoded topics/fields in code; everything configurable from .env.
"""

import os
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

# Topic selection priority: SPARK_KAFKA_TOPICS (if set) else KAFKA_TOPICS
SPARK_KAFKA_TOPICS = os.getenv("SPARK_KAFKA_TOPICS", "").strip()
KAFKA_TOPICS = SPARK_KAFKA_TOPICS or os.getenv("KAFKA_TOPICS", "events").strip()

# Kafka & mode configuration
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092").strip()
SPARK_MODE = os.getenv("SPARK_MODE", "top_artists").strip()  # top_artists | top_tracks | feature_avg

# Feature mode only
SPARK_FEATURE = os.getenv("SPARK_FEATURE", "track_duration_ms").strip()
SPARK_GROUP = os.getenv("SPARK_GROUP", "market_used").strip()  # comma-separated grouping cols

# Mongo config
MONGO_URL = os.getenv("MONGO_URL", "mongodb://root:example@localhost:27017/?authSource=admin").strip()
MONGO_DB = os.getenv("MONGO_DB", "spotify_db").strip()
OUT_COLL = f"{APP_PREFIX}_spark_{SPARK_MODE}"

# Packages (Kafka source). Can be overridden from env.
SPARK_PACKAGES = os.getenv(
	"SPARK_PACKAGES",
	"org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.kafka:kafka-clients:3.5.2",
)

print(f"[Spark] bootstrap: {KAFKA_BOOTSTRAP}")
print(f"[Spark] topics: {KAFKA_TOPICS.split(',')}")
print(f"[Spark] mode: {SPARK_MODE}")
if SPARK_MODE == "feature_avg":
	print(f"[Spark] feature: {SPARK_FEATURE} | group: {SPARK_GROUP}")

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
# - artist_* as StringType since producers may send string OR JSON-array.
# - We normalize after parsing (see normalizers below).
# ---------------------------
event_schema = StructType([
	StructField("user_id", StringType(), True),
	StructField("track_id", StringType(), True),
	StructField("track_name", StringType(), True),
	StructField("artist_ids", StringType(), True),		# may be '["a","b"]' or "a"
	StructField("artist_names", StringType(), True),	# may be '["A","B"]' or "A"
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
# Helpers: robust normalizers
# ---------------------------
def normalize_array_like(col: F.Column) -> F.Column:
	"""
	Normalize a column that can be:
	- null
	- plain string "A"
	- comma-separated "A,B"
	- JSON array '["A","B"]'
	Returns array<string>.
	"""
	# If it's a JSON array string, parse it as array<string>
	json_arr = F.from_json(col, ArrayType(StringType()))
	return (
		F.when(col.isNull(), F.array().cast("array<string>"))
		 .when(col.startswith("["), json_arr)
		 .when(F.instr(col, ",") > 0, F.split(col, r"\s*,\s*"))
		 .otherwise(F.array(col.cast("string")))
	)

def ensure_columns(df: DataFrame, names: List[str]) -> DataFrame:
	"""
	Make sure all column names exist in df.
	If missing, add them as NULL columns so downstream groupBy/select won't crash.
	"""
	for n in names:
		if n and n not in df.columns:
			df = df.withColumn(n, F.lit(None).cast(StringType()))
	return df

# Normalize the artist fields we actually aggregate on for top_artists
df_norm = (
	df_parsed
		.withColumn("artist_names_norm", normalize_array_like(F.col("artist_names")))
		.withColumn("artist_ids_norm", normalize_array_like(F.col("artist_ids")))
)

# ---------------------------
# Aggregation builders (modes)
# ---------------------------
def build_top_artists(df: DataFrame) -> DataFrame:
	"""
	Explode artist_names and compute Top 10 by play count.
	"""
	df_exploded = df.select(F.explode("artist_names_norm").alias("artist_name"))
	return (
		df_exploded
			.groupBy("artist_name")
			.agg(F.count(F.lit(1)).alias("plays"))
			.orderBy(F.col("plays").desc())
			.limit(10)
			.withColumn("batch_ts", F.current_timestamp())
			.select("batch_ts", "artist_name", "plays")
	)

def build_top_tracks(df: DataFrame) -> DataFrame:
	"""
	Compute Top 10 tracks by play count.
	"""
	df_src = ensure_columns(df, ["track_id", "track_name"])
	return (
		df_src.groupBy("track_id", "track_name")
			.agg(F.count(F.lit(1)).alias("plays"))
			.orderBy(F.col("plays").desc())
			.limit(10)
			.withColumn("batch_ts", F.current_timestamp())
			.select("batch_ts", "track_id", "track_name", "plays")
	)

def build_feature_avg(df: DataFrame, feat: str, group_expr: str) -> DataFrame:
	"""
	Average any numeric feature by chosen grouping columns.
	- feat: column name inside df (string). It will be cast to DOUBLE.
	- group_expr: comma-separated list of columns to group by. Missing cols are added as NULL.
	"""
	cols = [c.strip() for c in group_expr.split(",") if c.strip()]
	df_src = ensure_columns(df, cols + [feat])

	# Cast feature to double; filter out rows where cast fails (NULL)
	df_feat = df_src.withColumn(feat, F.col(feat).cast(DoubleType())).where(F.col(feat).isNotNull())

	if cols:
		out = (
			df_feat.groupBy(*[F.col(c) for c in cols])
				.agg(F.avg(F.col(feat)).alias("avg_value"), F.count(F.lit(1)).alias("rows"))
				.orderBy(F.col("avg_value").desc())
				.withColumn("batch_ts", F.current_timestamp())
		)
		return out.select(*cols, "avg_value", "rows", "batch_ts")
	else:
		out = (
			df_feat.agg(F.avg(F.col(feat)).alias("avg_value"), F.count(F.lit(1)).alias("rows"))
				.withColumn("batch_ts", F.current_timestamp())
		)
		return out.select("avg_value", "rows", "batch_ts")

# Choose mode
if SPARK_MODE == "top_tracks":
	df_out = build_top_tracks(df_norm)
elif SPARK_MODE == "feature_avg":
	df_out = build_feature_avg(df_norm, SPARK_FEATURE, SPARK_GROUP)
else:
	df_out = build_top_artists(df_norm)  # default

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


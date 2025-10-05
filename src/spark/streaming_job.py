#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Spark Structured Streaming job:
	- Consumes JSON events from Kafka topics (from .env KAFKA_TOPICS / KAFKA_BOOTSTRAP)
	- Parses flexible schema (handles artist_names as str|array|null, best-effort)
	- Computes Top Artists by play count per micro-batch
	- Writes aggregate to MongoDB (collection: <APP_PREFIX>_spark_leaderboard)
	- Also prints aggregates to console for live demo

Notes:
	- No Mongo Spark connector needed; we use foreachBatch + PyMongo (simpler & portable)
	- Safe on mixed/historic schemas; unknown fields are ignored
"""

import os
from typing import List

from dotenv import load_dotenv

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
	StructType, StructField, StringType, LongType, ArrayType
)

# ---------------------------
# Load environment variables
# ---------------------------
load_dotenv()  # loads .env if present

APP_PREFIX = os.getenv("APP_PREFIX", "avd").strip()
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPICS = os.getenv("KAFKA_TOPICS", "avd_recent_events")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://root:example@localhost:27017/?authSource=admin")
MONGO_DB = os.getenv("MONGO_DB", "spotify_db")
OUT_COLL = f"{APP_PREFIX}_spark_leaderboard"  # e.g., avd_spark_leaderboard

# You can override this from the Makefile via PYSPARK_SUBMIT_ARGS,
# but also inject it here so the job works when launched directly.
SPARK_PACKAGES = os.getenv(
	"SPARK_PACKAGES",
	"org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.kafka:kafka-clients:3.5.2",
)

print(f"[Spark] bootstrap: {KAFKA_BOOTSTRAP}")
print(f"[Spark] topics: {KAFKA_TOPICS.split(',')}")

# ---------------------------
# Spark session
# ---------------------------
spark = (
	SparkSession.builder
		.appName(f"{APP_PREFIX}_kafka_to_mongo_leaderboard")
		.config("spark.sql.shuffle.partitions", "2")
		.config("spark.jars.packages", SPARK_PACKAGES)  # <-- important
		.getOrCreate()
)
# Lower Spark console noise; switch to "INFO" for debugging
spark.sparkContext.setLogLevel("WARN")

# ---------------------------
# Kafka source
# ---------------------------
df_raw = (
	spark.readStream
		.format("kafka")
		.option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
		.option("subscribe", KAFKA_TOPICS)  # comma-separated topics supported
		.option("startingOffsets", "latest")
		.load()
)

# Kafka value is binary; cast to string
df_json_str = df_raw.select(
	F.col("timestamp").alias("kafka_ts"),
	F.col("value").cast("string").alias("raw_json")
)

# ---------------------------
# Flexible schema for events
# ---------------------------
event_schema = StructType([
	StructField("user_id", StringType(), True),
	StructField("track_id", StringType(), True),
	StructField("track_name", StringType(), True),
	StructField("artist_ids", ArrayType(StringType()), True),   # may be list in newer docs
	StructField("artist_names", ArrayType(StringType()), True), # may be list OR string in older docs
	StructField("album_name", StringType(), True),
	StructField("market_used", StringType(), True),
	StructField("played_at", StringType(), True),
	StructField("track_duration_ms", LongType(), True),
])

# Parse JSON with PERMISSIVE mode (malformed -> null)
df_parsed = df_json_str.select(
	F.from_json(F.col("raw_json"), event_schema, {"mode": "PERMISSIVE"}).alias("d"),
	"kafka_ts",
	"raw_json"
).select("kafka_ts", "raw_json", "d.*")

# ---------------------------
# Robust normalization of artist_names:
#	- if array<string> -> keep
#	- if null but raw_json has a string at $.artist_names -> wrap as array
#	- else -> empty array
# ---------------------------
# Best-effort fallback: pull raw field as string (when producers sent a scalar)
raw_artist_names_str = F.get_json_object(F.col("raw_json"), "$.artist_names")

df_norm = (
	df_parsed
		.withColumn(
			"artist_names_norm",
			F.when(F.col("artist_names").isNotNull(), F.col("artist_names"))
			 .when(raw_artist_names_str.isNotNull(), F.array(raw_artist_names_str.cast("string")))
			 .otherwise(F.array().cast("array<string>"))
		)
)

# ---------------------------
# Aggregation (Top Artists by plays) per micro-batch
# ---------------------------
df_exploded = df_norm.select(F.explode("artist_names_norm").alias("artist_name"))

df_top = (
	df_exploded
		.groupBy("artist_name")
		.agg(F.count(F.lit(1)).alias("plays"))
		.orderBy(F.col("plays").desc())
		.limit(10)
		.withColumn("batch_ts", F.current_timestamp())
		.select("batch_ts", "artist_name", "plays")
)

# ---------------------------
# Mongo sink via foreachBatch (PyMongo)
# ---------------------------
def write_batch_to_mongo(batch_df: DataFrame, batch_id: int) -> None:
	"""
	Called for every micro-batch.
	Writes the Top-10 rows to MongoDB as documents:
	{ batch_ts, artist_name, plays, batch_id, prefix }
	"""
	import pymongo
	from pymongo import MongoClient

	rows: List[dict] = [row.asDict(recursive=True) for row in batch_df.collect()]
	if not rows:
		return

	client = MongoClient(MONGO_URL)
	try:
		coll = client[MONGO_DB][OUT_COLL]
		for r in rows:
			r["batch_id"] = batch_id
			r["prefix"] = APP_PREFIX
		coll.insert_many(rows, ordered=False)
	finally:
		client.close()

# ---------------------------
# Dual sink: console + Mongo
# ---------------------------
query_console = (
	df_top.writeStream
		.outputMode("complete")  # print whole Top-10 each time
		.format("console")
		.option("truncate", "false")
		.option("numRows", "20")
		.start()
)

query_mongo = (
	df_top.writeStream
		.outputMode("complete")
		.foreachBatch(write_batch_to_mongo)
		.option("checkpointLocation", f"/tmp/{APP_PREFIX}_spark_leaderboard_ck")
		.start()
)

# Wait for both streams
query_console.awaitTermination()
query_mongo.awaitTermination()


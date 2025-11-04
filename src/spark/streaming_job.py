# tabs
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Modular Spark Structured Streaming job.

Pipeline:
Kafka -> parse JSON -> normalize arrays -> parse played_at
-> watermark + dropDuplicates (user_id, track_id, played_at_ts)
-> operator from spark.ops.registry (windowed) -> console + Mongo (append)

Teammates can plug operators via spark/ops/registry.py and configure defaults
per APP_PREFIX via spark/team_config.yaml. Environment variables override YAML.
"""

import os
from dotenv import load_dotenv
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, LongType, ArrayType

# ---------- env (base) ----------
load_dotenv()
APP_PREFIX = "avd"

# Operator & params (ENV has priority; YAML fills only missing ones)
SPARK_MODE	= os.getenv("SPARK_MODE", "top_artists").strip()		# top_artists | top_tracks | top_tracks_grouped | feature_avg | ...
SPARK_TOPN	= int(os.getenv("SPARK_TOPN", "10"))
SPARK_FEATURE = os.getenv("SPARK_FEATURE", "energy").strip()
SPARK_GROUP	= os.getenv("SPARK_GROUP", "market_used").strip()

# Kafka
SPARK_KAFKA_TOPICS = os.getenv("SPARK_KAFKA_TOPICS", "").strip()
KAFKA_TOPICS = SPARK_KAFKA_TOPICS or os.getenv("KAFKA_TOPICS", f"{APP_PREFIX}_recent_events").strip()
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:19092").strip()

# Mongo
MONGO_URL = os.getenv("MONGO_URL", "mongodb://root:example@mongo:27017/?authSource=admin").strip()
MONGO_DB = os.getenv("MONGO_DB", "spotify_db").strip()

# Windowing
WINDOW_SIZE = os.getenv("SPARK_WINDOW_SIZE", "2 hours")
WINDOW_SLIDE = os.getenv("SPARK_WINDOW_SLIDE", "15 minutes")		# fixed typo
WATERMARK = os.getenv("SPARK_WATERMARK", "2 hours")

# Packages
SPARK_PACKAGES = os.getenv(
	"SPARK_PACKAGES",
	"org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.kafka:kafka-clients:3.5.2",
)

# ---------- optional team config (per APP_PREFIX) ----------
# YAML can provide defaults per teammate prefix; ENV still wins when set.
import yaml

TEAM_CONFIG_PATH = os.getenv("TEAM_CONFIG_SPARK", "spark/team_config.yaml").strip()

def _load_team_cfg(path: str) -> dict:
	"""Read YAML (teams -> <prefix> -> {mode, topn, feature, group}). Missing file is OK."""
	try:
		if os.path.exists(path):
			with open(path, "r", encoding="utf-8") as f:
				return yaml.safe_load(f) or {}
	except Exception as e:
		print(f"[Spark] WARN: failed to read team config '{path}': {e}")
	return {}

_team_cfg = _load_team_cfg(TEAM_CONFIG_PATH)
if _team_cfg and "teams" in _team_cfg:
	_self = (_team_cfg["teams"].get(APP_PREFIX) or {})
	if _self:
		# Only use YAML if corresponding ENV is empty/unset
		if not os.getenv("SPARK_MODE"):		SPARK_MODE = (_self.get("mode") or SPARK_MODE).strip()
		if not os.getenv("SPARK_TOPN"):		SPARK_TOPN = int(_self.get("topn", SPARK_TOPN))
		if not os.getenv("SPARK_FEATURE"):	SPARK_FEATURE = (_self.get("feature") or SPARK_FEATURE).strip()
		if not os.getenv("SPARK_GROUP"):	SPARK_GROUP = (_self.get("group") or SPARK_GROUP).strip()

# Effective collection name
OUT_COLL = f"{APP_PREFIX}_spark_{SPARK_MODE}"
print(f"[Spark] topics={KAFKA_TOPICS} bootstrap={KAFKA_BOOTSTRAP}")
print(f"[Spark] mode={SPARK_MODE}, topN={SPARK_TOPN}, feature={SPARK_FEATURE}, group={SPARK_GROUP}")
print(f"[Spark] window size={WINDOW_SIZE}, slide={WINDOW_SLIDE}, watermark={WATERMARK}")

# ---------- spark ----------
spark = (
	SparkSession.builder
		.appName(f"{APP_PREFIX}_kafka_to_mongo_{SPARK_MODE}")
		.config("spark.sql.shuffle.partitions", "2")
		.config("spark.jars.packages", SPARK_PACKAGES)
		.getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")

# ---------- source (Kafka) ----------
df_raw = (
	spark.readStream
		.format("kafka")
		.option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
		.option("subscribe", KAFKA_TOPICS)
		.option("startingOffsets", "latest")
		.load()
)

df_json = df_raw.select(
	F.col("timestamp").alias("kafka_ts"),
	F.col("value").cast("string").alias("raw_json")
)

# ---------- schema ----------
event_schema = StructType([
	StructField("user_id", StringType(), True),
	StructField("played_at", StringType(), True),			# ISO8601 from producer
	StructField("track_id", StringType(), True),
	StructField("track_name", StringType(), True),
	StructField("artist_ids", StringType(), True),			# may be "A,B" or JSON array
	StructField("artist_names", StringType(), True),		# may be "A,B" or JSON array
	StructField("album_id", StringType(), True),
	StructField("album_name", StringType(), True),
	StructField("country", StringType(), True),
	StructField("market_used", StringType(), True),
	StructField("track_duration_ms", LongType(), True),

	# optional metrics (strings; cast later in ops)
	StructField("danceability", StringType(), True),
	StructField("energy", StringType(), True),
	StructField("valence", StringType(), True),
])

df_parsed = df_json.select(
	F.from_json(F.col("raw_json"), event_schema, {"mode": "PERMISSIVE"}).alias("d"),
	"kafka_ts"
).select("kafka_ts", "d.*")

# ---------- normalizers ----------
def normalize_str_array(col: F.Column) -> F.Column:
	"""Turn null / 'A' / 'A,B' / '["A","B"]' into array<string>."""
	json_arr = F.from_json(col, ArrayType(StringType()))
	return (
		F.when(col.isNull(), F.array().cast("array<string>"))
		 .when(col.startswith("["), json_arr)
		 .when(F.instr(col, ",") > 0, F.split(col, r"\s*,\s*"))
		 .otherwise(F.array(col.cast("string")))
	)

df_norm = (
	df_parsed
		.withColumn("artist_names_arr", normalize_str_array(F.col("artist_names")))
		.withColumn("artist_ids_arr", normalize_str_array(F.col("artist_ids")))
		.withColumn("played_at_ts", F.to_timestamp("played_at"))
)

# ---------- dedup + watermark ----------
df_clean = (
	df_norm
		.withWatermark("played_at_ts", WATERMARK)
		.dropDuplicates(["user_id", "track_id", "played_at_ts"])
)

# ---------- operator selection ----------
from spark.ops.registry import OPS

if SPARK_MODE not in OPS:
	raise RuntimeError(f"Unknown SPARK_MODE '{SPARK_MODE}'. Available: {list(OPS.keys())}")

cfg = {
	"topn": SPARK_TOPN,
	"feature": SPARK_FEATURE,
	"group": SPARK_GROUP,		# grouping column name (e.g., 'market_used')
}
win = {
	"size": WINDOW_SIZE,
	"slide": WINDOW_SLIDE,
}

op_fn = OPS[SPARK_MODE]
# Operator returns a time-windowed DataFrame with a 'batch_ts' column
df_out = op_fn(df_clean, cfg, win)

# ---------- sinks ----------
def write_batch_to_mongo(batch_df: DataFrame, batch_id: int) -> None:
	"""
	Run Top-N ranking on the static micro-batch (allowed in foreachBatch),
	then insert documents into MongoDB.

	Notes:
	- Do NOT overwrite 'group' (it contains the actual value like 'RO').
	  Store the grouping column name as metadata 'group_by'.
	- For 'top_tracks_grouped' and 'feature_avg' we keep ALL rows
	  (no Top-N trimming here).
	"""
	from pyspark.sql import functions as F
	from pyspark.sql.window import Window
	from pymongo import MongoClient

	# quick empty-batch guard (cheap enough here)
	if batch_df.count() == 0:
		return

	topn = int(cfg.get("topn", 10))
	part_col = "batch_ts"

	# Choose ordering by mode
	if SPARK_MODE == "top_artists":
		order_cols = [F.col("plays").desc(), F.col("artist_name").asc()]
	elif SPARK_MODE in ("top_tracks", "top_tracks_grouped"):
		order_cols = [F.col("plays").desc(), F.col("track_name").asc()]
	elif SPARK_MODE == "feature_avg":
		order_cols = [F.col("avg_value").desc()]
	else:
		order_cols = [F.lit(1)]  # no-op fallback

	w = Window.partitionBy(part_col).orderBy(*order_cols)

	# For grouped/feature_avg keep all rows; otherwise apply Top-N per batch_ts
	keep_all = SPARK_MODE in ("feature_avg", "top_tracks_grouped")

	ranked = (
		batch_df.withColumn("rn", F.row_number().over(w))
			.where((F.col("rn") <= topn) | F.lit(keep_all))
			.drop("rn")
	)

	docs = [r.asDict(recursive=True) for r in ranked.collect()]
	if not docs:
		return

	client = MongoClient(MONGO_URL)
	try:
		coll = client[MONGO_DB][OUT_COLL]
		for d in docs:
			# trace/meta
			d["batch_id"] = batch_id
			d["prefix"] = APP_PREFIX
			d["mode"] = SPARK_MODE

			# add feature meta only for feature_avg
			if SPARK_MODE == "feature_avg":
				d["feature"] = cfg.get("feature")

			# IMPORTANT: do not overwrite the actual group value
			# store grouping COLUMN NAME as metadata
			group_field = cfg.get("group")
			if group_field:
				d["group_by"] = group_field

		coll.insert_many(docs, ordered=False)
	finally:
		client.close()

# Console stream (for demo)
query_console = (
	df_out.writeStream
		.outputMode("append")			# with watermark + windowing -> append is correct
		.format("console")
		.option("truncate", "false")
		.option("numRows", "50")
		.start()
)

# Mongo sink via foreachBatch
query_mongo = (
	df_out.writeStream
		.outputMode("append")
		.foreachBatch(write_batch_to_mongo)
		.option("checkpointLocation", f"/tmp/{APP_PREFIX}_spark_{SPARK_MODE}_ck")
		.start()
)

print("[Spark] console id:", query_console.id)
print("[Spark] mongo   id:", query_mongo.id)

# Wait robustly for any stream to end
spark.streams.awaitAnyTermination()


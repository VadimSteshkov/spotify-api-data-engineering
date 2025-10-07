# -*- coding: utf-8 -*-
"""
Schema registry for per-topic parsing in Spark.
- Each teammate can register a StructType for their topic.
- Topics not in SCHEMAS will be ingested as RAW JSON (fallback).
"""

from pyspark.sql.types import (
	StructType, StructField, StringType, ArrayType, LongType
)

# === Example: Dorin/AVD events (baseline you already use) ===
AVD_EVENT_SCHEMA = StructType([
	StructField("user_id", StringType()),
	StructField("played_at", StringType()),
	StructField("track_id", StringType()),
	StructField("track_name", StringType()),
	StructField("artist_ids", ArrayType(StringType())),
	StructField("artist_names", ArrayType(StringType())),
	StructField("album_id", StringType()),
	StructField("album_name", StringType()),
	StructField("country", StringType()),
	StructField("market_used", StringType()),
	StructField("track_duration_ms", LongType()),
])

# === Teammates add their schemas here (topic -> StructType) ===
SCHEMAS = {
	"avd_recent_events": AVD_EVENT_SCHEMA,	# example
	# "alex_events": ALEX_EVENT_SCHEMA,
	# "vadim_clicks": VADIM_EVENT_SCHEMA,
}


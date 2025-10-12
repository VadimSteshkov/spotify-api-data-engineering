# tabs
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Windowed Top Tracks grouped by a column (e.g., market_used).

This operator:
- groups by time window + group column + track fields
- counts plays per group & track
- selects a 'batch_ts' that is the window start (consistent with other ops)
Ranking (Top-N) is handled later in foreachBatch.
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def build_top_tracks_grouped(df: DataFrame, cfg: dict, win: dict) -> DataFrame:
	"""
	Args:
		df: cleaned stream with 'played_at_ts' and deduplicated rows
		cfg: expects 'group' (e.g., 'market_used')
		win: {'size': '10 minutes', 'slide': '1 minute'}
	"""
	# Resolve config
	group_col = (cfg.get("group") or "market_used").strip()
	size = win["size"]
	slide = win["slide"]

	# --- Safety: ensure the group column exists and is a clean, non-null string ---
	# If the column is missing in the input schema, create it as NULL to avoid runtime errors.
	if group_col not in df.columns:
		df = df.withColumn(group_col, F.lit(None))

	# Normalize the grouping key: trim and replace NULL with 'unknown'
	group_key = F.trim(F.coalesce(F.col(group_col).cast("string"), F.lit("unknown"))).alias("group")

	# --- Windowed aggregation ---
	out = (
		df.groupBy(
			F.window("played_at_ts", size, slide).alias("w"),
			group_key,
			F.col("track_id"),
			F.col("track_name"),
		)
		.agg(F.count(F.lit(1)).alias("plays"))
		.select(
			F.col("w.start").alias("batch_ts"),
			F.col("group"),
			F.col("track_id"),
			F.col("track_name"),
			F.col("plays"),
		)
	)

	return out


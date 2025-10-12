# tabs
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

def build_top_tracks(df: DataFrame, cfg: dict, win: dict) -> DataFrame:
	"""
	Time-windowed play counts per track (no ranking here).
	Ranking is done inside foreachBatch.
	Assumes df has: track_id, track_name, played_at_ts
	"""
	size = win["size"]
	slide = win["slide"]

	out = (
		df.groupBy(
			F.window("played_at_ts", size, slide).alias("w"),
			F.col("track_id"),
			F.col("track_name"),
		)
		.agg(F.count(F.lit(1)).alias("plays"))
		.select(
			F.col("w.start").alias("batch_ts"),
			F.col("track_id"),
			F.col("track_name"),
			F.col("plays"),
		)
	)
	return out


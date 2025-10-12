# tabs
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

def build_top_artists(df: DataFrame, cfg: dict, win: dict) -> DataFrame:
	"""
	Time-windowed play counts per artist (no ranking here).
	Ranking is done later inside foreachBatch (static context).
	Assumes df has:
	- artist_names_arr: array<string>
	- played_at_ts: timestamp
	"""
	size = win["size"]
	slide = win["slide"]

	# explode to one row per artist
	df_a = df.withColumn("artist_name", F.explode_outer("artist_names_arr"))

	out = (
		df_a.groupBy(
			F.window("played_at_ts", size, slide).alias("w"),
			F.col("artist_name")
		)
		.agg(F.count(F.lit(1)).alias("plays"))
		.select(
			F.col("w.start").alias("batch_ts"),
			F.col("artist_name"),
			F.col("plays"),
		)
	)
	return out


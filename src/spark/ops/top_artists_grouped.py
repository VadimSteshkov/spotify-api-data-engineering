# tabs
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Windowed Top Artists grouped by a column (e.g., market_used).

This operator:
- groups by time window + group column + artist fields
- counts plays per group & artist
- selects a 'batch_ts' that is the window start (consistent with other ops)
Ranking (Top-N) is handled later in foreachBatch.
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

def build_top_artists_grouped(df: DataFrame, cfg: dict, win: dict) -> DataFrame:
	"""
	Args:
		df: cleaned stream with 'played_at_ts' and deduplicated rows
		cfg: expects 'group' (e.g., 'market_used')
		win: {'size': '10 minutes', 'slide': '1 minute'}
	"""
	group_col = (cfg.get("group") or "market_used").strip()
	size = win["size"]
	slide = win["slide"]

	out = (
		df.withColumn("artist_name", F.explode("artist_names_arr"))
		  .withColumn("artist_id", F.explode("artist_ids_arr"))
		  .groupBy(
				F.window("played_at_ts", size, slide).alias("w"),
				F.col(group_col).alias("group"),
				F.col("artist_id"),
				F.col("artist_name"),
		  )
		  .agg(F.count(F.lit(1)).alias("plays"))
		  .select(
				F.col("w.start").alias("batch_ts"),
				F.col("group"),
				F.col("artist_id"),
				F.col("artist_name"),
				F.col("plays"),
		  )
	)
	return out


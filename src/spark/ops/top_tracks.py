#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Top tracks aggregation by play count.
"""

from pyspark.sql import DataFrame, functions as F


def _ensure_columns(df: DataFrame, cols: list[str]) -> DataFrame:
	for c in cols:
		if c not in df.columns:
			df = df.withColumn(c, F.lit(None).cast("string"))
	return df


def build_top_tracks(df: DataFrame, cfg: dict | None = None) -> DataFrame:
	"""Aggregate top tracks by play count."""
	df = _ensure_columns(df, ["track_id", "track_name"])
	out = (
		df.groupBy("track_id", "track_name")
			.agg(F.count(F.lit(1)).alias("plays"))
			.orderBy(F.col("plays").desc())
			.limit(10)
			.withColumn("batch_ts", F.current_timestamp())
			.select("batch_ts", "track_id", "track_name", "plays")
	)
	return out


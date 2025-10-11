#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Top artists aggregation.
If column 'artist_names_norm' does not exist, it normalizes 'artist_names'
from string or JSON into an array<string>.
"""

from pyspark.sql import DataFrame, functions as F
from pyspark.sql.types import ArrayType, StringType


def _normalize_array_like(col):
	"""Turn null / 'A' / 'A,B' / '["A","B"]' into array<string>."""
	json_arr = F.from_json(col, ArrayType(StringType()))
	return (
		F.when(col.isNull(), F.array().cast("array<string>"))
			.when(col.startswith("["), json_arr)
			.when(F.instr(col, ",") > 0, F.split(col, r"\s*,\s*"))
			.otherwise(F.array(col.cast("string")))
	)


def build_top_artists(df: DataFrame, cfg: dict | None = None) -> DataFrame:
	"""Aggregate top artists by count of plays."""
	if "artist_names_norm" not in df.columns:
		df = df.withColumn("artist_names_norm", _normalize_array_like(F.col("artist_names")))

	exploded = df.select(F.explode("artist_names_norm").alias("artist_name"))
	out = (
		exploded.groupBy("artist_name")
			.agg(F.count(F.lit(1)).alias("plays"))
			.orderBy(F.col("plays").desc())
			.limit(10)
			.withColumn("batch_ts", F.current_timestamp())
			.select("batch_ts", "artist_name", "plays")
	)
	return out


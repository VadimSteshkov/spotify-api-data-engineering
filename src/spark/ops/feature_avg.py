#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Feature average aggregation operator.

This operator computes the average of a numeric feature (cast to double)
grouped by a single column (e.g., market or artist).
"""

from typing import List
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType


def _ensure_columns(df: DataFrame, cols: List[str]) -> DataFrame:
	"""Ensure that all required columns exist in the DataFrame."""
	for c in cols:
		if c not in df.columns:
			df = df.withColumn(c, F.lit(None).cast(StringType()))
	return df


def build_feature_avg(df: DataFrame, cfg: dict | None = None) -> DataFrame:
	"""
	Aggregate average of a numeric feature grouped by one column.
	Defaults: feature='energy', group='market_used', topn=10
	"""
	cfg = cfg or {}
	feature = (cfg.get("feature") or "energy").strip()
	group_col = (cfg.get("group") or cfg.get("groups") or "market_used").strip()
	topn = int(cfg.get("topn", 10))

	df = _ensure_columns(df, [group_col, feature])

	# Cast feature to double and filter out invalid values
	df_num = df.withColumn(feature, F.col(feature).cast(DoubleType())).where(F.col(feature).isNotNull())

	out = (
		df_num.groupBy(F.col(group_col))
			.agg(
				F.avg(F.col(feature)).alias("avg_value"),
				F.count(F.lit(1)).alias("rows")
			)
			.orderBy(F.col("avg_value").desc())
			.limit(topn)
			.withColumn("batch_ts", F.current_timestamp())
			.select(group_col, "avg_value", "rows", "batch_ts")
	)

	return out


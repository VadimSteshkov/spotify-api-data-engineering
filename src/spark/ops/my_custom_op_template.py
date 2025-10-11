#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Custom Spark Structured Streaming operator (function-based) — TEMPLATE.

How to use:
1) Copy this file as: src/spark/ops/my_custom_op_template.py
   (Optionally rename it to match your use-case, e.g. avg_valence_by_market.py)
2) Register it in src/spark/ops/registry.py:
		from .my_custom_op_template import build_my_custom_op
		OPS["my_custom_mode"] = build_my_custom_op
3) In src/spark/team_config.yaml, configure your prefix:
	teams:
	  alex:
	    mode: my_custom_mode
	    feature: energy          # numeric field to average (string or numeric)
	    group: market_used       # one or more grouping columns
	    topn: 10                 # keep Top-N rows after sorting by avg_value desc

Notes:
- Input 'df' is the parsed & normalized stream with stringly-typed robustness.
- Keep the output small (Top-N aggregates) for readable console output and efficient Mongo writes.
"""

from typing import List, Union
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType


def _ensure_columns(df: DataFrame, cols: List[str]) -> DataFrame:
	"""
	Ensure all requested columns exist in df.
	If a column is missing, add it as NULL (cast to string for robustness).
	"""
	for c in cols:
		if c and c not in df.columns:
			df = df.withColumn(c, F.lit(None).cast(StringType()))
	return df


def _parse_groups(group_cfg: Union[str, List[str], None]) -> List[str]:
	"""
	Accept 'group' as:
	- None
	- comma-separated string: "market_used,artist_name"
	- list of strings
	Return normalized list of non-empty column names.
	"""
	if group_cfg is None:
		return []
	if isinstance(group_cfg, str):
		return [c.strip() for c in group_cfg.split(",") if c.strip()]
	return [str(c).strip() for c in group_cfg if str(c).strip()]


def build_my_custom_op(df: DataFrame, cfg: dict | None = None) -> DataFrame:
	"""
	Compute average of a numeric feature grouped by one or more columns,
	then keep Top-N by average (desc). Mirrors 'feature_avg', but kept
	as a simple template you can modify freely.

	Config (from team_config.yaml under your prefix):
	- feature: str              # numeric field to average (cast to DOUBLE)
	- group: str | list[str]    # group-by columns (comma-separated or list)
	- topn: int                 # how many rows to keep (Top-N)

	Fallback defaults if keys are missing:
	- feature: "energy"
	- group: ["market_used"]
	- topn: 10
	"""
	cfg = cfg or {}

	# Resolve params (with safe defaults)
	feature = (cfg.get("feature") or "energy").strip()
	group_cols = _parse_groups(cfg.get("group") or cfg.get("groups") or ["market_used"])
	try:
		topn = int(cfg.get("topn", 10))
	except Exception:
		topn = 10

	# Ensure required columns exist
	df = _ensure_columns(df, group_cols + [feature])

	# Cast selected feature to DOUBLE and drop rows where cast fails (NULL)
	df_num = df.withColumn(feature, F.col(feature).cast(DoubleType())).where(F.col(feature).isNotNull())

	# If we have group columns -> group & average; else -> global average
	if group_cols:
		out = (
			df_num.groupBy(*[F.col(c) for c in group_cols])
				.agg(
					F.avg(F.col(feature)).alias("avg_value"),
					F.count(F.lit(1)).alias("rows")
				)
				.orderBy(F.col("avg_value").desc())
		)
		# Keep Top-N if requested
		if topn and topn > 0:
			out = out.limit(topn)

		# Add batch timestamp for context
		out = out.withColumn("batch_ts", F.current_timestamp())

		# Deterministic column order
		return out.select(*group_cols, "avg_value", "rows", "batch_ts")

	# No groups -> single global average
	out = (
		df_num.agg(F.avg(F.col(feature)).alias("avg_value"), F.count(F.lit(1)).alias("rows"))
			.withColumn("batch_ts", F.current_timestamp())
	)
	return out.select("avg_value", "rows", "batch_ts")


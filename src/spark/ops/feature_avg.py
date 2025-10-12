# tabs
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType

def build_feature_avg(df: DataFrame, cfg: dict, win: dict) -> DataFrame:
	"""
	Time-windowed average of a numeric feature grouped by a column.
	No ranking in streaming; any topN is applied in foreachBatch.
	"""
	feature = (cfg.get("feature") or "energy").strip()
	group_col = (cfg.get("group") or "market_used").strip()
	size = win["size"]
	slide = win["slide"]

	df_num = df.withColumn(feature, F.col(feature).cast(DoubleType())).where(F.col(feature).isNotNull())

	out = (
		df_num.groupBy(
			F.window("played_at_ts", size, slide).alias("w"),
			F.col(group_col)
		)
		.agg(
			F.avg(F.col(feature)).alias("avg_value"),
			F.count(F.lit(1)).alias("rows"),
		)
		.select(
			F.col("w.start").alias("batch_ts"),
			F.col(group_col).alias("group"),
			F.col("avg_value"),
			F.col("rows"),
		)
	)
	return out


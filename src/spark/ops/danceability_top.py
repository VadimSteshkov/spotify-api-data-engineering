# tabs
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

def build_danceability_top(df: DataFrame, cfg: dict, win: dict) -> DataFrame:
	# df already has played_at_ts + dedup + watermark
	size = win["size"]; slide = win["slide"]
	topn = int(cfg.get("topn", 10))
	df_num = df.withColumn("danceability", F.col("danceability").cast("double")).where(F.col("danceability").isNotNull())
	grp = df_num.groupBy(F.window("played_at_ts", size, slide).alias("w"), F.col("track_name")).agg(F.avg("danceability").alias("avg_dance"))
	return (grp.orderBy(F.col("avg_dance").desc()).limit(topn)
		.select(F.col("w.start").alias("batch_ts"), F.col("track_name"), F.col("avg_dance")))


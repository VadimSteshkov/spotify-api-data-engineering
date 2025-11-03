import pandas as pd
import streamlit as st
from datetime import datetime, timezone, date, time
from typing import Tuple
from pymongo.errors import PyMongoError
import plotly.express as px
import numpy as np

def render(db, cfg, prefix: str):
	"""Render a tab for prefix 'alex' with filters and analytics."""
	st.session_state._orchestrator_mongo_db = db
	df = build_data()
	if df.empty:
		st.write("No data found")
		return
	numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
	st.subheader("Overview")
	st.dataframe(df.groupby("playlist_name")[numeric_cols].mean())

	st.subheader("Top 10")
	column = st.selectbox(
		"Select Column:",  # Label above the dropdown
		numeric_cols  # Options list
	)
	agg = (
		df.dropna(subset=["playlist_name", column])
		.groupby("playlist_name", as_index=False)[column].mean()
	)

	top10 = agg.nlargest(10, column).sort_values(column, ascending=True)

	fig = px.bar(
		top10,
		x=column,
		y="playlist_name",
		text_auto=True
	)
	st.plotly_chart(fig, use_container_width=True)


	option = st.selectbox(
		"Select Playlist:",  # Label above the dropdown
		["(all)"] + df["playlist_name"].dropna().unique().tolist()  # Options list
	)

	if option != "(all)":
		df_filtered = df[df["playlist_name"] == option]
	else:
		df_filtered = df



	st.subheader("Top Tracks")
	col = st.selectbox(
		"By:",  # Label above the dropdown
		numeric_cols  # Options list
	)

	df_filtered[col] = pd.to_numeric(df_filtered[col], errors="coerce")
	ranked = (
		df_filtered.groupby(["track_name", "href"], as_index=False)[col]
		.mean()
		.assign(rank=lambda d: d[col].rank(method="dense", ascending=False).astype(int))
		.sort_values(["rank", col])
	)
	ranked.set_index("rank", inplace=True)

	st.dataframe(
		ranked.head(5),
		use_container_width=True
	)

	st.subheader("Statistics")
	st.dataframe(df_filtered.describe())

	st.subheader("Heatmap")

	selected = st.multiselect("Select columns to correlate:", numeric_cols, default=numeric_cols)


	fig = px.imshow(
		df_filtered[selected].corr(numeric_only=True),
		text_auto=True,
		color_continuous_scale="RdBu_r",
		zmin=-1,
		zmax=1,
		title=option + " (Number Tracks: " + str(len(df_filtered)) + ")",
	)
	fig.update_layout(coloraxis_showscale=False)
	size = st.slider("Heatmap size (pixels)", 500, 1000, 700, step=100)
	fig.update_layout(width=size, height=size)
	st.plotly_chart(fig)


# Pull data from the collection.
# Uses st.cache_data to only rerun when the query changes or after 10 min.
@st.cache_data(ttl=600)
def get_data(coll_name: str) -> pd.DataFrame:
		try:
			db = st.session_state._orchestrator_mongo_db
			data = db[coll_name].find()
			df = pd.DataFrame(list(data))
			return df
		except PyMongoError as e:
			st.error(f"Mongo error while loading events from {coll_name}: {e}")
			return pd.DataFrame()

def build_data() -> pd.DataFrame:
	tracksPlaylistsDf = get_data("alex_playlist_analysis")
	df = pd.DataFrame()
	if tracksPlaylistsDf.empty:
		return df
	for index, row in tracksPlaylistsDf.iterrows():
		df.at[index, "playlist_name"] = row.get("playlist_name")
		df.at[index, "track_name"] = row.get("track_name")
		reckoAnalysis = row.get("analysis")
		if reckoAnalysis == "Failed":
			continue
		danceability = reckoAnalysis["danceability"]
		valence = reckoAnalysis["valence"]
		liveness = reckoAnalysis["liveness"]
		tempo = reckoAnalysis["tempo"]
		href = reckoAnalysis["href"]
		instrumentalness = reckoAnalysis["instrumentalness"]
		try:
			popularity = row.get("popularity")
		except:
			popularity = 0
		df.at[index, "popularity"] = popularity
		df.at[index, "danceability"] = danceability
		df.at[index, "instrumentalness"] = instrumentalness
		df.at[index, "valence"] = valence
		df.at[index, "liveness"] = liveness
		df.at[index, "tempo"] = tempo
		df.at[index, "href"] = href
	return df


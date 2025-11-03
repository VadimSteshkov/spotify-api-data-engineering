import pandas as pd
import plotly.express as px
import streamlit as st


def render(db, cfg, prefix: str):
	coll_danceability = f"{prefix}_genre_danceability"

	st.markdown("""
    **User Story**: *As a DJ, I want to know which genre has the highest average danceability in order to improve my music selection.*
    """)

	try:
		latest_dance_doc = db[coll_danceability].find_one({}, sort=[("generated_at", -1)])

		if latest_dance_doc and latest_dance_doc.get("genres"):
			genres_data = latest_dance_doc["genres"]
			generated_at = latest_dance_doc.get("generated_at", "N/A")

			st.info(f"📅 Analysis: {generated_at} | Data source: RapidAPI")

			df_genres = pd.DataFrame(genres_data)
			df_genres = df_genres[df_genres["avg_danceability"].notna()].copy()
			df_genres = df_genres.sort_values("avg_danceability", ascending=False)

			col1, col2 = st.columns(2)

			with col1:
				st.subheader("Top Genres by Danceability")

				fig_dance = px.bar(
					df_genres.head(10),
					y="genre",
					x="avg_danceability",
					orientation="h",
					title="Average Danceability by Genre",
					labels={"avg_danceability": "Danceability", "genre": "Genre"},
					color="avg_danceability",
					color_continuous_scale="Viridis",
					text="avg_danceability"
				)
				fig_dance.update_traces(texttemplate='%{text:.3f}', textposition='outside')
				fig_dance.update_layout(yaxis={'categoryorder': 'total ascending'}, showlegend=False, height=400)
				st.plotly_chart(fig_dance, use_container_width=True)

			with col2:
				st.subheader("Energy vs Danceability")

				fig_scatter = px.scatter(
					df_genres,
					x="avg_danceability",
					y="avg_energy",
					size="track_count",
					hover_data=["genre", "avg_tempo"],
					title="Energy vs Danceability",
					color="avg_tempo",
					color_continuous_scale="Turbo"
				)
				fig_scatter.update_layout(height=400)
				st.plotly_chart(fig_scatter, use_container_width=True)

			st.subheader("Complete Analysis")

			display_df = df_genres[["genre", "avg_danceability", "avg_energy", "avg_tempo", "track_count"]].copy()
			display_df.columns = ["Genre", "Danceability", "Energy", "Tempo (BPM)", "Tracks"]
			display_df["Danceability"] = display_df["Danceability"].round(3)
			display_df["Energy"] = display_df["Energy"].round(3)
			display_df["Tempo (BPM)"] = display_df["Tempo (BPM)"].round(0).astype(int)

			st.dataframe(display_df, use_container_width=True, hide_index=True, height=210)

			st.subheader("Key Insights")

			col1, col2, col3 = st.columns(3)
			top_genre = df_genres.iloc[0]

			with col1:
				st.metric("Most Danceable", top_genre["genre"].title(), f"{top_genre['avg_danceability']:.3f}")
			with col2:
				st.metric("Average", "All Genres", f"{df_genres['avg_danceability'].mean():.3f}")
			with col3:
				st.metric("Fastest", df_genres.loc[df_genres["avg_tempo"].idxmax(), "genre"].title(),
				          f"{df_genres['avg_tempo'].max():.0f} BPM")

		else:
			st.warning("No genre analysis data. Producer will analyze every hour.")

	except Exception as e:
		st.error(f"Error: {e}")

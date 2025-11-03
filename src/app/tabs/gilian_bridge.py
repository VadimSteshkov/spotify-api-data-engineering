import math
from typing import List, Dict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def camelot_to_color(camelot: str) -> str:
	if not camelot or len(camelot) < 2:
		return "gray"

	is_major = camelot[-1].upper() == "B"

	colors_minor = ["#3498db", "#2980b9", "#1f618d", "#154360"]  # Blues
	colors_major = ["#e74c3c", "#c0392b", "#922b21", "#641e16"]  # Reds

	try:
		num = int(camelot[:-1])
		idx = (num - 1) % 4
		return colors_major[idx] if is_major else colors_minor[idx]
	except:
		return "gray"


def create_camelot_wheel_chart(bridge_tracks: List[Dict]) -> go.Figure:
	fig = go.Figure()

	theta = [i * (2 * math.pi / 12) for i in range(13)]
	r = [1.0] * 13

	fig.add_trace(go.Scatterpolar(
		r=r,
		theta=[t * 180 / math.pi for t in theta],
		mode='lines',
		line=dict(color='lightgray', width=1),
		showlegend=False,
		hoverinfo='skip'
	))

	for i in range(1, 13):
		angle = (i - 1) * (2 * math.pi / 12)

		fig.add_trace(go.Scatterpolar(
			r=[1.15],
			theta=[angle * 180 / math.pi],
			mode='text',
			text=[f"{i}B"],
			textfont=dict(size=10, color='red'),
			showlegend=False,
			hoverinfo='skip'
		))

		fig.add_trace(go.Scatterpolar(
			r=[0.7],
			theta=[angle * 180 / math.pi],
			mode='text',
			text=[f"{i}A"],
			textfont=dict(size=10, color='blue'),
			showlegend=False,
			hoverinfo='skip'
		))

	for track in bridge_tracks:
		camelot = track.get("camelot")
		if not camelot or len(camelot) < 2:
			continue

		try:
			num = int(camelot[:-1])
			is_major = camelot[-1].upper() == "B"

			angle = (num - 1) * (2 * math.pi / 12)
			radius = 1.0 if is_major else 0.65

			fig.add_trace(go.Scatterpolar(
				r=[radius],
				theta=[angle * 180 / math.pi],
				mode='markers+text',
				marker=dict(
					size=20,
					color=camelot_to_color(camelot),
					symbol='circle',
					line=dict(color='white', width=2)
				),
				text=[str(track["position"])],
				textfont=dict(color='white', size=12, family='Arial Black'),
				name=f"{track['position']}. {track['track_name'][:30]}",
				hovertext=f"{track['track_name']}<br>Key: {camelot}<br>Position: {track['position']}",
				hoverinfo='text'
			))
		except:
			pass

	fig.update_layout(
		polar=dict(
			radialaxis=dict(visible=False, range=[0, 1.3]),
			angularaxis=dict(visible=False)
		),
		showlegend=True,
		title="Camelot Wheel - Bridge Track Keys",
		height=500
	)

	return fig


def render(db, cfg, prefix: str):
	st.title(f"DJ Bridge Dashboard")

	coll_bridges = f"{prefix}_genre_bridges"
	st.markdown("""
    **User Story**: *As a DJ, I want to build bridges between subgenres*
    """)

	try:
		latest_bridge_doc = db[coll_bridges].find_one({}, sort=[("generated_at", -1)])

		if latest_bridge_doc and latest_bridge_doc.get("tracks"):
			source = latest_bridge_doc.get("source_genre", "Unknown")
			target = latest_bridge_doc.get("target_genre", "Unknown")
			generated_at = latest_bridge_doc.get("generated_at", "N/A")
			rapid_enabled = latest_bridge_doc.get("rapid_api_enabled", False)
			tracks = latest_bridge_doc["tracks"]

			st.info(
				f"Generated: {generated_at} | Camelot keys: {'✓ Available' if rapid_enabled else '✗ Not available (set RAPID_API_KEY)'}")
			st.success(f"Bridge: **{source.title()}** → **{target.title()}**")

			df_bridge = pd.DataFrame(tracks)

			if rapid_enabled and any(t.get("camelot") for t in tracks):
				st.subheader("Camelot Wheel (Harmonic Mixing)")
				st.markdown("*Tracks plotted on the Camelot wheel. Adjacent keys mix smoothly!*")

				fig_wheel = create_camelot_wheel_chart(tracks)
				st.plotly_chart(fig_wheel, use_container_width=True)

				st.info("""
                **Camelot Mixing Rules**:
                - Same key = Perfect match (e.g., 8A → 8A)
                - Adjacent numbers = Energy boost/drop (e.g., 8A → 9A or 7A)
                - Same number, different letter = Mood change (e.g., 8A → 8B)
                - Diagonal = Smooth transition (e.g., 8A → 11B)
                """)

			st.subheader("Transition Playlist")

			for _, track in df_bridge.iterrows():
				camelot = track.get('camelot') or 'N/A'
				with st.expander(f"**{track['position']}. {track['track_name']}** - {', '.join(track['artists'])}"):
					col1, col2 = st.columns([2, 1])

					with col1:
						st.markdown(f"""
                        **Genre**: {track['genre_seed'].title()}
                        **Camelot Key**: {camelot}
                        **Danceability**: {track['danceability']:.3f}
                        **Energy**: {track['energy']:.3f}
                        **Tempo**: {track['tempo']:.0f} BPM
                        """)

						if track.get("spotify_url"):
							st.markdown(f"[Open in Spotify]({track['spotify_url']})")

			st.subheader("Bridge Analysis")

			col1, col2 = st.columns(2)

			with col1:

				fig_tempo = go.Figure()
				fig_tempo.add_trace(go.Scatter(
					x=df_bridge["position"],
					y=df_bridge["tempo"],
					mode='lines+markers',
					name='Tempo',
					line=dict(color='royalblue', width=3),
					marker=dict(size=10)
				))
				fig_tempo.update_layout(
					title="Tempo Progression (BPM)",
					xaxis_title="Position",
					yaxis_title="BPM",
					height=300
				)
				st.plotly_chart(fig_tempo, use_container_width=True)

			with col2:

				fig_features = go.Figure()
				fig_features.add_trace(go.Scatter(
					x=df_bridge["position"],
					y=df_bridge["danceability"],
					mode='lines+markers',
					name='Danceability',
					line=dict(color='green', width=2)
				))
				fig_features.add_trace(go.Scatter(
					x=df_bridge["position"],
					y=df_bridge["energy"],
					mode='lines+markers',
					name='Energy',
					line=dict(color='red', width=2)
				))
				fig_features.update_layout(
					title="Feature Progression",
					xaxis_title="Position",
					yaxis_title="Value",
					height=300
				)
				st.plotly_chart(fig_features, use_container_width=True)

			fig_scatter = go.Figure()
			fig_scatter.add_trace(go.Scatter(
				x=df_bridge["danceability"],
				y=df_bridge["energy"],
				mode='markers+text',
				text=df_bridge["position"],
				textposition="top center",
				marker=dict(
					size=15,
					color=df_bridge["position"],
					colorscale='Viridis',
					showscale=True
				),
				hovertext=[f"{row['track_name']}<br>Pos: {row['position']}" for _, row in df_bridge.iterrows()]
			))
			fig_scatter.update_layout(
				title="Energy vs Danceability Progression",
				xaxis_title="Danceability",
				yaxis_title="Energy",
				height=400
			)
			st.plotly_chart(fig_scatter, use_container_width=True)

			st.subheader("DJ Mixing Tips")

			tempo_range = df_bridge["tempo"].max() - df_bridge["tempo"].min()

			st.success(f"""
            **Bridge Analysis**:
            - Tempo range: {tempo_range:.1f} BPM (Use pitch control for smooth transitions)
            - Keys: {', '.join(t.get('camelot', '?') for t in tracks)}
            - Start with track 1, gradually mix through, end with track {len(tracks)}

            **Pro Tips**:
            - Use EQ to blend matching frequencies
            - Follow the Camelot wheel for harmonic mixing
            - Watch energy levels - avoid big drops
            - Practice each transition!
            """)

		else:
			st.warning("""
            No bridge data yet. Producer generates bridges every hour.

            Configure genres in `.env.gilian`:
            ```
            BRIDGE_SOURCE=techno
            BRIDGE_TARGET=house
            ```
            """)


	except Exception as e:
		st.error(f"Error: {e}")

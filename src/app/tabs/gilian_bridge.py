import math
import traceback
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
		line=dict(color='lightgray', width=2),
		showlegend=False,
		hoverinfo='skip'
	))

	fig.add_trace(go.Scatterpolar(
		r=[0.65] * 13,
		theta=[t * 180 / math.pi for t in theta],
		mode='lines',
		line=dict(color='lightgray', width=2),
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
			r=[0.5],
			theta=[angle * 180 / math.pi],
			mode='text',
			text=[f"{i}A"],
			textfont=dict(size=10, color='blue'),
			showlegend=False,
			hoverinfo='skip'
		))

	valid_tracks = []
	for track in sorted(bridge_tracks, key=lambda t: t.get("position", 999)):
		camelot = track.get("camelot")
		if not camelot or len(camelot) < 2:
			continue

		try:
			num = int(camelot[:-1])
			is_major = camelot[-1].upper() == "B"
			angle = (num - 1) * (2 * math.pi / 12)
			radius = 1.0 if is_major else 0.65

			valid_tracks.append({
				"track": track,
				"angle": angle * 180 / math.pi,
				"radius": radius,
				"camelot": camelot
			})
		except:
			pass

	if len(valid_tracks) > 1:
		line_angles = [t["angle"] for t in valid_tracks]
		line_radii = [t["radius"] for t in valid_tracks]

		fig.add_trace(go.Scatterpolar(
			r=line_radii,
			theta=line_angles,
			mode='lines',
			line=dict(color='rgba(255, 215, 0, 0.6)', width=3, dash='solid'),
			name='Bridge Path',
			showlegend=True,
			hoverinfo='skip'
		))

	for track_data in valid_tracks:
		track = track_data["track"]
		angle = track_data["angle"]
		radius = track_data["radius"]
		camelot = track_data["camelot"]

		danceability = track.get("danceability") or 0
		energy = track.get("energy") or 0
		tempo = track.get("tempo") or 0

		hover_text = (
			f"<b>{track['position']}. {track['track_name']}</b><br>"
			f"Artists: {', '.join(track.get('artists', []))}<br>"
			f"Genre: {track.get('genre_seed', 'N/A').title()}<br>"
			f"<br>"
			f"<b>Key:</b> {camelot}<br>"
			f"<b>Danceability:</b> {danceability:.2f}<br>"
			f"<b>Energy:</b> {energy:.2f}<br>"
			f"<b>Tempo:</b> {tempo:.0f} BPM"
		)

		fig.add_trace(go.Scatterpolar(
			r=[radius],
			theta=[angle],
			mode='markers+text',
			marker=dict(
				size=30,
				color=camelot_to_color(camelot),
				symbol='circle',
				line=dict(color='white', width=3)
			),
			text=[str(track["position"])],
			textfont=dict(color='white', size=14, family='Arial Black'),
			name=f"{track['position']}. {track['track_name'][:25]}...",
			hovertext=hover_text,
			hoverinfo='text',
			hoverlabel=dict(
				bgcolor='white',
				font_size=12,
				font_family='Arial'
			)
		))

		offset_angle = angle + 15
		annotation_radius = radius + 0.15 if radius > 0.8 else radius - 0.15

		fig.add_annotation(
			x=annotation_radius * math.cos(offset_angle * math.pi / 180),
			y=annotation_radius * math.sin(offset_angle * math.pi / 180),
			text=f"{tempo:.0f}",
			showarrow=False,
			font=dict(size=9, color='white'),
			xref="x",
			yref="y"
		)

	fig.update_layout(
		polar=dict(
			radialaxis=dict(visible=False, range=[0, 1.4]),
			angularaxis=dict(visible=False)
		),
		showlegend=True,
		legend=dict(
			orientation="v",
			yanchor="top",
			y=0.99,
			xanchor="left",
			x=1.05,
			font=dict(size=10)
		),
		title={
			'text': "Camelot Wheel Bridge Progression",
			'x': 0.5,
			'xanchor': 'center',
			'font': {'size': 18, 'family': 'Arial Black'}
		},
		height=600,
		margin=dict(l=50, r=150, t=80, b=50)
	)

	return fig


def render(db, cfg, prefix: str):
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
				st.subheader("Camelot Wheel - Harmonic Mixing Path")
				st.markdown(
					"*Tracks plotted on the Camelot wheel. Gold line shows the progression. Hover for details!*")

				fig_wheel = create_camelot_wheel_chart(tracks)
				st.plotly_chart(fig_wheel, use_container_width=True)

				st.info("""
                **Camelot Mixing Rules**:
                - **Same key** = Perfect match (e.g., 8A → 8A)
                - **Adjacent numbers** = Energy boost/drop (e.g., 8A → 9A or 7A)
                - **Same number, different letter** = Mood change (e.g., 8A → 8B)
                - **Diagonal** = Smooth transition (e.g., 8A → 11B)

                *Numbers on the wheel show BPM. Track position numbers are inside the circles.*
                """)

			st.subheader("🎼 Transition Playlist")

			for _, track in df_bridge.iterrows():
				camelot = track.get('camelot') or 'N/A'
				with st.expander(f"**{track['position']}. {track['track_name']}** - {', '.join(track['artists'])}"):
					col1, col2 = st.columns([2, 1])

					with col1:
						st.markdown(f"""
                        **Genre**: {track['genre_seed'].title()}
                        **Camelot Key**: {camelot}
                        **Danceability**: {track.get('danceability', 0):.3f}
                        **Energy**: {track.get('energy', 0):.3f}
                        **Tempo**: {track.get('tempo', 0):.0f} BPM
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

			st.subheader("Mixing Tips")

			tempo_range = df_bridge["tempo"].max() - df_bridge["tempo"].min()

			st.success(f"""
            **Bridge Analysis**:
            - **Tempo range**: {tempo_range:.1f} BPM
            - **Keys**: {', '.join(t.get('camelot', '?') for t in tracks)}
            - **Path**: {' → '.join([f"{t.get('camelot', '?')}" for t in tracks])}
            """)

		else:
			st.warning("""
            No bridge data yet. Producer generates bridges every hour.

            Configure genres in `.env.gilian`:
            ```
            BRIDGE_SOURCE=techno
            BRIDGE_TARGET=classical
            ```
            """)


	except Exception as e:
		st.error(f"Error: {e}")
		st.code(traceback.format_exc())

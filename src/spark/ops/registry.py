# tabs
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from .top_artists import build_top_artists
from .top_tracks import build_top_tracks
from .feature_avg import build_feature_avg

OPS = {
	"top_artists": build_top_artists,
	"top_tracks": build_top_tracks,
	"feature_avg": build_feature_avg,
}


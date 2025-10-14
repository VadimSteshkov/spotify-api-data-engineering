# tabs
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from .top_artists import build_top_artists
from .top_tracks import build_top_tracks
from .feature_avg import build_feature_avg
<<<<<<< HEAD
from .top_tracks_grouped import build_top_tracks_grouped
from spark.ops.top_artists_grouped import build_top_artists_grouped
=======
>>>>>>> a716db97c21512d34f2c7416acf7107c63a6354c

OPS = {
	"top_artists": build_top_artists,
	"top_tracks": build_top_tracks,
	"feature_avg": build_feature_avg,
<<<<<<< HEAD
	"top_tracks_grouped": build_top_tracks_grouped,
	"top_artists_grouped": build_top_artists_grouped,
=======
>>>>>>> a716db97c21512d34f2c7416acf7107c63a6354c
}


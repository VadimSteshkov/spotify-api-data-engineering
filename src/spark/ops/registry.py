#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Registry of available streaming operators (function-based).
Each operator has the signature:
	(df: pyspark.sql.DataFrame, cfg: dict | None) -> pyspark.sql.DataFrame
"""

# Built-in operators
from .top_artist import build_top_artists
from .top_tracks import build_top_tracks
from .feature_avg import build_feature_avg

# Optional custom operator (template). Import only if the file exists.
# You can copy/rename 'my_custom_op_template.py' and keep the import path in sync.
try:
	from .my_custom_op_template import build_my_custom_op
	_HAS_CUSTOM = True
except Exception:
	_HAS_CUSTOM = False

# Map mode name -> operator function
OPS = {
	"top_artists": build_top_artists,
	"top_tracks": build_top_tracks,
	"feature_avg": build_feature_avg,
}

# Register custom mode only if import succeeded
if _HAS_CUSTOM:
	OPS["my_custom_mode"] = build_my_custom_op


def get_op(name: str):
	"""Return operator function by name or None."""
	return OPS.get(name)


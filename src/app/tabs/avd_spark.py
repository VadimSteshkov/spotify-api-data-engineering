# -*- coding: utf-8 -*-
"""
Thin wrapper that reuses the generic Spark tab but locks it to the owner's base prefix.
"""

from tabs import spark_generic as generic

def render(db, cfg, prefix: str) -> None:
	# Here, `prefix` is 'avd_spark' (the tab name), but we want to show collections for owner 'avd'.
	owner_prefix = "avd"	# <-- teammates will copy this file and set their own owner prefix
	generic.render(db=db, cfg=cfg, prefix=owner_prefix)


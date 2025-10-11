#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Base class for custom Spark Structured Streaming operators.
This is optional but useful when you want to build operators using OOP.
Currently, most operators are function-based, but this base can be extended later.
"""

from typing import Optional
from pyspark.sql import DataFrame


class BaseOp:
	"""
	Base operator providing a standard interface.
	Subclasses must implement the `run(self, df)` method.
	"""

	name: str = "base"

	def __init__(self, cfg: Optional[dict] = None):
		self.cfg = cfg or {}

	def run(self, df: DataFrame) -> DataFrame:
		"""
		Override this method in subclasses to define the operator logic.
		"""
		raise NotImplementedError("Subclasses must implement 'run' method")


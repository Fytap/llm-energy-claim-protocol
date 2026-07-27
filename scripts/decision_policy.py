"""Formal numerical decision rule used by Protocol 1.1.0 simulations.

The rule is illustrative until a service owner freezes its SESOI, direction
fraction, tolerance, estimand, inference method, and multiplicity family.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil


class NumericState(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class NumericDecisionRule:
    sesoi_percent: float
    direction_fraction: float
    tolerance: float = 1e-12

    def required_favorable_blocks(self, n_blocks: int) -> int:
        if n_blocks <= 0:
            raise ValueError("n_blocks must be positive")
        if not 0.0 < self.direction_fraction <= 1.0:
            raise ValueError("direction_fraction must be in (0, 1]")
        return ceil(self.direction_fraction * n_blocks)

    def classify(self, lower_bound: float, upper_bound: float, favorable_blocks: int, n_blocks: int) -> NumericState:
        required = self.required_favorable_blocks(n_blocks)
        # Strict inequalities deliberately leave equality at the SESOI inconclusive.
        if lower_bound > self.sesoi_percent + self.tolerance and favorable_blocks >= required:
            return NumericState.SUPPORTED
        if upper_bound < self.sesoi_percent - self.tolerance:
            return NumericState.CONTRADICTED
        return NumericState.INCONCLUSIVE

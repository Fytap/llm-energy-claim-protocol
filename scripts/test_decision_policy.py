#!/usr/bin/env python3
"""Boundary and rounding tests for the formal numerical decision rule."""

import unittest

from decision_policy import NumericDecisionRule, NumericState


class NumericDecisionRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = NumericDecisionRule(sesoi_percent=2.0, direction_fraction=0.8)

    def test_exact_lower_boundary_is_inconclusive(self):
        self.assertEqual(self.rule.classify(2.0, 4.0, 10, 10), NumericState.INCONCLUSIVE)

    def test_exact_upper_boundary_is_inconclusive(self):
        self.assertEqual(self.rule.classify(-1.0, 2.0, 0, 10), NumericState.INCONCLUSIVE)

    def test_strict_support_requires_both_mean_and_direction_conditions(self):
        self.assertEqual(self.rule.classify(2.001, 4.0, 8, 10), NumericState.SUPPORTED)
        self.assertEqual(self.rule.classify(2.001, 4.0, 7, 10), NumericState.INCONCLUSIVE)

    def test_strict_contradiction_uses_upper_bound(self):
        self.assertEqual(self.rule.classify(-1.0, 1.999, 10, 10), NumericState.CONTRADICTED)

    def test_noninteger_guard_uses_ceiling(self):
        self.assertEqual(self.rule.required_favorable_blocks(11), 9)
        self.assertEqual(self.rule.classify(2.1, 4.0, 8, 11), NumericState.INCONCLUSIVE)
        self.assertEqual(self.rule.classify(2.1, 4.0, 9, 11), NumericState.SUPPORTED)

    def test_invalid_block_count_is_rejected(self):
        with self.assertRaises(ValueError):
            self.rule.required_favorable_blocks(0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

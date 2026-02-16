"""Deterministic position sizing utilities."""

from __future__ import annotations


def clamp_int(value: int, low: int, high: int) -> int:
    """Clamp an integer within inclusive bounds."""
    return max(low, min(high, value))


def momentum_to_target(
    momentum_score: float,
    max_abs_qty: int,
    threshold: float,
) -> int:
    """Map momentum score to a bounded integer target position."""
    if momentum_score >= threshold:
        return max_abs_qty
    if momentum_score <= -threshold:
        return -max_abs_qty
    return 0

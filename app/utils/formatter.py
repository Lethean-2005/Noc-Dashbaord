"""Presentation-layer formatting helpers."""


def badge_color(count):
    """Green for a 0 alarm count, red otherwise — used by the live alarm cards."""
    return "badge-green" if not count else "badge-red"

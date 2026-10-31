"""Measured bilingual groups, in the caller's coordinate system."""
import math


def stacked_pairs(bottom_edge, heights, line_gap, speaker_gap=15):
    """Return (upper_top, lower_top) for each speaker, lowest speaker first.

    A zero height means that layer is absent. Empty groups take no space.
    Native fields use the same edge-to-edge layout with their measured bounds.
    """
    def valid(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0

    if not all(valid(value) for value in (bottom_edge, line_gap, speaker_gap)):
        raise ValueError('Invalid subtitle geometry')
    cursor = bottom_edge
    positions = []
    for upper_height, lower_height in heights:
        if not all(valid(value) for value in (upper_height, lower_height)):
            raise ValueError('Invalid subtitle height')
        upper = lower = None
        if lower_height:
            lower = cursor - lower_height
            cursor = lower
        if upper_height:
            if lower_height:
                cursor -= line_gap
            upper = cursor - upper_height
            cursor = upper
        positions.append((upper, lower))
        if upper_height or lower_height:
            cursor -= speaker_gap
    return positions

"""Small assertions and measurements shared by movement characterization tests."""

from main import UNIT_SEPARATION_RADIUS, UNIT_SOFT_OVERLAP, dist


def pairwise_unit_separation(units):
    """Return `(first, second, distance)` for every unique unit pair."""
    return [
        (first, second, dist((first.x, first.y), (second.x, second.y)))
        for index, first in enumerate(units)
        for second in units[index + 1:]
    ]


def penetration_beyond_soft_overlap(
    first,
    second,
    separation_radius=UNIT_SEPARATION_RADIUS,
    soft_overlap=UNIT_SOFT_OVERLAP,
):
    """Return penetration beyond the explicitly permitted soft overlap."""
    minimum_separation = separation_radius - soft_overlap
    return max(
        0.0,
        minimum_separation - dist((first.x, first.y), (second.x, second.y)),
    )


def made_progress_toward_destination(
    start,
    current,
    destination,
    tolerance=1e-9,
):
    """Return whether `current` is measurably closer to the final destination."""
    return dist(current, destination) < dist(start, destination) - tolerance

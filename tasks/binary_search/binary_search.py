"""Binary search over a sorted list, e.g. a sorted table of extent start addresses."""


def lower_bound(items: list, target) -> int:
    """Return the first index i with items[i] >= target, or len(items) if there is none."""
    lo, hi = 0, len(items) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if items[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo

"""Read and write bit fields inside a hardware register value."""


def get_field(reg: int, lsb: int, width: int) -> int:
    """Return the `width`-bit field of `reg` that starts at bit `lsb`."""
    return (reg >> lsb) & ((1 << width) - 1)


def set_field(reg: int, lsb: int, width: int, value: int) -> int:
    """Return `reg` with bits [lsb, lsb + width) set to `value`; all other bits are unchanged."""
    if value < 0 or value >= (1 << width):
        raise ValueError(f"value {value} does not fit in {width} bits")
    mask = ((1 << width) - 1) << lsb
    return (reg & mask) | (value << lsb)

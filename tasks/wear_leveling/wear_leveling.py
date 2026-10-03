"""Choose which free NAND block to write next so that wear stays even."""


def pick_block(erase_counts: dict[int, int], free_blocks: set[int]) -> int:
    """Return the free block with the lowest erase count.

    Blocks missing from `erase_counts` have never been erased (count 0). Ties go to the
    lowest block id, which keeps the choice deterministic. Raises ValueError when no
    block is free.
    """
    if not free_blocks:
        raise ValueError("no free blocks")
    return min(free_blocks, key=lambda block: (erase_counts.get(block, 0), -block))

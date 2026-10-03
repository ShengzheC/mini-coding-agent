"""CRC-8 checksum used to protect small firmware structures (SMBus PEC variant)."""


def crc8(data: bytes, poly: int = 0x07, init: int = 0x00) -> int:
    """CRC-8 with polynomial x^8 + x^2 + x + 1, MSB first, no reflection, no final XOR.

    The result is always an integer in [0, 255].
    """
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
    return crc

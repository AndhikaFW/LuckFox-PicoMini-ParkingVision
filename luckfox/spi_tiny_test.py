#!/usr/bin/env python3
"""TEMP diagnostic: send one tiny frame matching the current production
firmware config (4000-byte chunks, DMA enabled). Header + 1 payload chunk =
2 total SPI transactions, 4000 bytes each, but with a small real payload --
lets us sweep SPI mode (0-3) quickly without rebuilding/reflashing, in case
mode 0 isn't actually what's landing on the wire (RV1103 SPI0 driver quirk).
"""
import sys
import struct
import spidev

CHUNK_BYTES = 4000
MAGIC = 0x52415046

mode = int(sys.argv[1]) if len(sys.argv) > 1 else 0

payload = bytes(range(16))  # 16 bytes, well under one chunk

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1_000_000
spi.mode = mode
print(f"using mode={mode}", file=sys.stderr)

header = struct.pack("<I", MAGIC) + struct.pack("<BHI", 0, 0, len(payload))
header_padded = header + bytes(CHUNK_BYTES - len(header))
spi.writebytes2(header_padded)

payload_padded = payload + bytes(CHUNK_BYTES - len(payload))
spi.writebytes2(payload_padded)

spi.close()
print("sent tiny test frame (2 transactions, 4000 bytes each)")

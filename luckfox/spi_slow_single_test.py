#!/usr/bin/env python3
"""TEMP diagnostic: single 4000-byte transfer (matching production
kLuckfoxSpiChunkBytes) at a configurable (very low) speed, to rule out
timing-margin explanations entirely.
"""
import sys
import spidev

speed = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
CHUNK_BYTES = 4000

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = speed
spi.mode = 0

payload = bytes((i % 256) for i in range(CHUNK_BYTES))
result = spi.xfer2(list(payload))
spi.close()

print(f"sent single {CHUNK_BYTES}-byte transfer at {speed}Hz, received (first 16 bytes):",
      bytes(result[:16]).hex())

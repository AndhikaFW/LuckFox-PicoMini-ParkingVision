#!/usr/bin/env python3
"""Standalone SPI0 sanity check for the LuckFox side only -- no ESP32
involved. Requires a physical jumper wire bridging MOSI to MISO on
LuckFox's own J1 header (SPI0 M0: physical positions 8 and 9, per
luckfox-config's pin diagram) so whatever this sends comes straight back
on the same transfer (spidev's full-duplex xfer2).

Written to isolate whether LuckFox's SPI0 pins are actually live/correctly
mapped to the physical header positions we've been wiring to the ESP32,
independent of anything on the ESP32 side (a plain send always reports
success on the master regardless of whether anything is listening, so it
proves nothing about wiring by itself).

Usage: python3 spi_loopback_test.py
"""
import spidev

TEST_BYTES = bytes([0xDE, 0xAD, 0xBE, 0xEF, 0x01, 0x02, 0x03, 0x04] * 4)

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1_000_000  # slow, to rule out signal-integrity-at-speed issues
spi.mode = 0

result = spi.xfer2(list(TEST_BYTES))
spi.close()

result_bytes = bytes(result)
print("sent:    ", TEST_BYTES.hex())
print("received:", result_bytes.hex())
if result_bytes == TEST_BYTES:
    print("LOOPBACK OK: SPI0 MOSI/MISO pins are live and correctly wired")
else:
    print("LOOPBACK FAILED: received data does not match sent data")

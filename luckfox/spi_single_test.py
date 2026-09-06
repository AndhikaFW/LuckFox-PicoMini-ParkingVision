#!/usr/bin/env python3
"""TEMP diagnostic: ONE single isolated SPI transfer, nothing else -- open,
one xfer2() call of exactly 16 bytes (matching firmware's temporarily
reduced kLuckfoxSpiChunkBytes=16), close. Isolates whether even a single,
completely isolated transaction can make the ESP32 SPI slave's
spi_slave_transmit() return at all, independent of any multi-call protocol
behavior.
"""
import spidev

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1_000_000
spi.mode = 0

result = spi.xfer2(list(range(16)))
spi.close()

print("sent single 16-byte transfer, received:", bytes(result).hex())

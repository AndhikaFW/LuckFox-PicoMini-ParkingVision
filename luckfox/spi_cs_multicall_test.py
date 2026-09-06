#!/usr/bin/env python3
"""TEMP diagnostic: does CS actually deassert/reassert between two SEPARATE
writebytes2()-style ioctl calls on the SAME open spidev fd? Our real
protocol (spi_sender.py) opens the fd once per frame, then does one
writebytes2() for the header and one per payload chunk -- if CS stays
continuously low across all of these instead of toggling once per call,
the ESP32 slave (which arms exactly one chunk's worth of bits per
spi_slave_transmit() call) would see the whole burst as one giant
transaction and its length-limited receive would never signal "done".

Requires the same CS(pin6)->MISO(pin9) jumper as the earlier CS-bridge
test. Uses xfer2() (full-duplex) instead of writebytes2() so we can see
what's actually coming back on MISO during EACH of two separate calls.
"""
import spidev

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1_000_000
spi.mode = 0

call1 = spi.xfer2(list(bytes([0xAA] * 16)))
call2 = spi.xfer2(list(bytes([0xBB] * 16)))

spi.close()

print("call1 received:", bytes(call1).hex())
print("call2 received:", bytes(call2).hex())

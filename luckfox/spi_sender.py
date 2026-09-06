#!/usr/bin/env python3
"""Runs on LuckFox: read raw NV12 frames (no header, back-to-back -- see
../backend/ and the pi4-camera-stream-noencode tool that produces them),
split each frame into kVideoStreamsPerNode vertical strips (one per parking
lane covered by this node's camera), downsample each strip to the chain's
per-stream size, encode, and push all of them to this node's paired
ESP32-S3 over SPI (Linux spidev, master) as the local leg of
file -> LuckFox -> SPI -> ESP32 -> RPi4.

Splitting: the source frame is SRC_W wide; stream N gets the vertical slice
[N*STRIP_W, (N+1)*STRIP_W) at full SRC_H, independently downsampled to
DST_W x DST_H. All 3 streams come from the same captured frame (same
moment in time, same seq number per frame) -- this used to be a round-robin
placeholder that gave every stream the *same*, full, undivided frame once
every 3rd capture (1/3 the real frame rate each); that never actually
split anything spatially, just multiplexed identical whole frames across
3 stream_ids.

Counterpart: src/ESP32-S3-RAP/main/luckfox_spi.{h,cpp} (SPI *slave* there --
Linux spidev is master-only, and the ESP32 side already uses spi_master.h
for the Gateway's ENC28J60, so this stays master / ESP32 stays slave to
avoid two masters on one bus).

Encoding note: the ESP32 side's placeholder producer originally assumed
~15-23KB JPEG frames, but this LuckFox image's Pillow build has no JPEG
encoder (only zlib/PNG -- see features.check("jpg") == False). Sends PNG
for now; swap encode_frame() for real JPEG/H.264 once that's available
on-device (also bump kVideoMaxFrameBytes back down in config.h once frames
shrink -- it's currently sized for these larger PNGs).

Requires SPI0 M0 enabled first (not persistent across reboots by default):
    source /usr/bin/luckfox-config noop
    luckfox_config_init
    luckfox_spi_app 1 0 0 1 1 20000000
"""
import argparse
import gc
import struct
import sys
import time

import spidev
from PIL import Image

SRC_W, SRC_H = 1920, 1080
Y_SIZE = SRC_W * SRC_H
FRAME_SIZE = Y_SIZE + Y_SIZE // 2

DST_W, DST_H = 600, 400  # kVideoStreamsPerNode streams, this size each (config.h)
STREAMS_PER_NODE = 3
STRIP_W = SRC_W // STREAMS_PER_NODE  # 640px-wide vertical slice per stream

# Must match config.h's kLuckfoxSpiChunkBytes exactly -- both ends assume
# every SPI transaction is this many bytes.
CHUNK_BYTES = 4000

MAGIC = 0x52415046  # "RAPF", must match luckfox_spi.cpp's kMagic
# WireHeader: uint32 magic, uint8 stream_id, uint16 seq, uint32 data_len
# (little-endian, packed -- matches the __attribute__((packed)) struct on
# the ESP32 side; both are little-endian cores so this lines up as-is).
HEADER_FMT = "<BHI"  # after the 4-byte magic, which we pack separately below


def downsample_plane(plane, full_w, full_h, crop_x, crop_w, dst_w, dst_h, stride=1, elem_offset=0):
    """Nearest-neighbor downsample of the [crop_x, crop_x+crop_w) x [0, full_h)
    region of `plane` (a full_w-wide row buffer) into dst_w x dst_h. Indexes
    directly into `plane` with an optional element stride/offset (stride=2
    lets this read straight out of an interleaved U/V buffer without a
    separate [0::2]/[1::2] copy first -- each of those copies ~0.5MB, real
    money against this device's ~12MB genuinely-free budget, see project
    notes). `full_w` (the real row stride) and `crop_w` (the region being
    downsampled) are separate on purpose -- a crop narrower than the full
    row still needs the full row's stride to find the next row's start."""
    out = bytearray(dst_w * dst_h)
    for dy in range(dst_h):
        sy = dy * full_h // dst_h
        row_off = sy * full_w
        for dx in range(dst_w):
            sx = crop_x + dx * crop_w // dst_w
            out[dy * dst_w + dx] = plane[(row_off + sx) * stride + elem_offset]
    return bytes(out)


def nv12_strip_to_png_bytes(y_plane, uv_plane, stream_id, dst_w=DST_W, dst_h=DST_H):
    """Memory-frugal NV12(1920x1080) strip -> PNG(dst_w x dst_h) for one of
    STREAMS_PER_NODE vertical slices of the frame (see module docstring).
    `y_plane`/`uv_plane` are the whole frame's planes, read once per frame
    and reused across all streams' calls -- only the downsampled output
    (bytearray, then PIL Image) is duplicated per-stream, not the source
    planes themselves."""
    crop_x = stream_id * STRIP_W
    y_small = downsample_plane(y_plane, SRC_W, SRC_H, crop_x, STRIP_W, dst_w, dst_h)

    half_w, half_h = SRC_W // 2, SRC_H // 2
    half_crop_x, half_strip_w = crop_x // 2, STRIP_W // 2
    dst_half_w, dst_half_h = dst_w // 2, dst_h // 2
    u_small = downsample_plane(uv_plane, half_w, half_h, half_crop_x, half_strip_w,
                                dst_half_w, dst_half_h, stride=2, elem_offset=0)
    v_small = downsample_plane(uv_plane, half_w, half_h, half_crop_x, half_strip_w,
                                dst_half_w, dst_half_h, stride=2, elem_offset=1)

    y_img = Image.frombytes("L", (dst_w, dst_h), y_small)
    del y_small
    u_img = Image.frombytes("L", (dst_half_w, dst_half_h), u_small).resize((dst_w, dst_h), Image.NEAREST)
    del u_small
    v_img = Image.frombytes("L", (dst_half_w, dst_half_h), v_small).resize((dst_w, dst_h), Image.NEAREST)
    del v_small

    rgb = Image.merge("YCbCr", (y_img, u_img, v_img)).convert("RGB")
    del y_img, u_img, v_img
    import io
    buf = io.BytesIO()
    rgb.save(buf, "PNG")
    return buf.getvalue()


class SpiFrameSender:
    """Opens /dev/spidevX.Y lazily, only for the duration of an actual
    send_frame() call, and closes it again right after -- this device has
    ~33MB total RAM and often only a few MB free at idle (see project
    notes), so spidev's own (small but non-zero) footprint sitting open
    for the whole PIL decode/resize/encode step was enough to tip an
    already razor-thin budget into an OOM kill. Reopening per frame costs
    a bit of latency but that's cheap next to a killed process."""

    def __init__(self, bus=0, device=0, speed_hz=20_000_000):
        self.bus = bus
        self.device = device
        self.speed_hz = speed_hz

    def _send_chunk(self, spi, chunk):
        padded = chunk + bytes(CHUNK_BYTES - len(chunk))
        spi.writebytes2(padded)

    def send_frame(self, stream_id, seq, payload):
        gc.collect()  # reclaim the PIL intermediates from encode_frame() first
        spi = spidev.SpiDev()
        spi.open(self.bus, self.device)
        spi.max_speed_hz = self.speed_hz
        spi.mode = 0
        try:
            header = struct.pack("<I", MAGIC) + struct.pack(HEADER_FMT, stream_id, seq, len(payload))
            self._send_chunk(spi, header)

            offset = 0
            while offset < len(payload):
                self._send_chunk(spi, payload[offset:offset + CHUNK_BYTES])
                offset += CHUNK_BYTES
        finally:
            spi.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("nv12_path", help="raw NV12 recording, e.g. from pi4-camera-stream-noencode")
    ap.add_argument("--frames", type=int, default=0, help="stop after N frames (0 = whole file)")
    ap.add_argument("--interval", type=float, default=0.3, help="seconds between frames (matches kVideoLocalFrameIntervalMs by default)")
    ap.add_argument("--bus", type=int, default=0)
    ap.add_argument("--device", type=int, default=0)
    ap.add_argument("--speed-hz", type=int, default=20_000_000)
    args = ap.parse_args()

    import os
    total_frames = os.path.getsize(args.nv12_path) // FRAME_SIZE

    sender = SpiFrameSender(args.bus, args.device, args.speed_hz)
    seq = 0
    sent = 0

    with open(args.nv12_path, "rb") as f:
        while sent < total_frames:
            t0 = time.time()
            y_plane = f.read(Y_SIZE)
            uv_plane = f.read(Y_SIZE // 2)

            for stream in range(STREAMS_PER_NODE):
                png = nv12_strip_to_png_bytes(y_plane, uv_plane, stream)
                gc.collect()  # free the PIL intermediates before spidev opens
                png_len = len(png)
                sender.send_frame(stream, seq, png)
                del png
                print(f"frame {sent}: stream={stream} seq={seq} "
                      f"{png_len} bytes, {time.time()-t0:.2f}s", file=sys.stderr)

            del y_plane, uv_plane
            seq = (seq + 1) & 0xFFFF
            sent += 1
            if args.frames and sent >= args.frames:
                break

            time.sleep(args.interval)

    print(f"done, sent {sent} frames ({sent * STREAMS_PER_NODE} total across {STREAMS_PER_NODE} streams)", file=sys.stderr)


if __name__ == "__main__":
    main()

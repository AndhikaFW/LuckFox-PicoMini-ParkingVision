#!/usr/bin/env python3
"""Minimal RPi4-side demo for the Gateway's video uplink (kVideoBackendPort).

Proves frames arrive traceable to their origin node/camera and can be
organized per node: each frame is written to
frames/<node name>/stream<N>/latest.jpg, and every frame is logged with its
origin, stream, and sequence number. Swap the "write file" step for whatever
the real ParkingVision display does with a frame once that exists.

Wire format per frame (matches VideoFrameHeader in main/gateway_uplink.cpp):
  uint8_t origin_node_id
  uint8_t stream_id
  uint16_t seq   (little-endian)
  uint32_t data_len (little-endian)
  <data_len> bytes of raw frame data
"""

import os
import socket
import struct
import sys
import threading

from node_names import load_names, name_for

PORT = 5300
HEADER = struct.Struct("<BBHI")
FRAMES_DIR = os.path.join(os.path.dirname(__file__), "frames")

# A hard reset on the Gateway (no clean FIN/RST) can leave a connection
# ESTABLISHED on this side with no more data ever coming -- without a
# timeout, recv() blocks forever on it. 30s is generous next to the video
# producer's ~300ms/frame cadence, so it only fires on a genuinely dead peer.
RECV_TIMEOUT_S = 30.0


def recv_all(conn: socket.socket, size: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < size:
        chunk = conn.recv(size - len(buf))
        if not chunk:
            return None
        buf += chunk
    return bytes(buf)


def handle_connection(conn: socket.socket, addr, names: dict[int, str]) -> None:
    conn.settimeout(RECV_TIMEOUT_S)
    print(f"[video] connected: {addr}")
    while True:
        header_bytes = recv_all(conn, HEADER.size)
        if header_bytes is None:
            print(f"[video] disconnected: {addr}")
            return
        origin_node_id, stream_id, seq, data_len = HEADER.unpack(header_bytes)
        data = recv_all(conn, data_len)
        if data is None:
            print(f"[video] disconnected mid-frame: {addr}")
            return

        node_name = name_for(origin_node_id, names)
        print(f"[video] node={origin_node_id} ({node_name}) stream={stream_id} "
              f"seq={seq} bytes={data_len}")

        out_dir = os.path.join(FRAMES_DIR, node_name, f"stream{stream_id}")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "latest.jpg"), "wb") as f:
            f.write(data)


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)  # stdout is block-buffered when redirected to a file
    names = load_names()
    os.makedirs(FRAMES_DIR, exist_ok=True)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(4)
    print(f"[video] listening on :{PORT}, writing frames under {FRAMES_DIR}/<node name>/streamN/")

    while True:
        conn, addr = srv.accept()
        # One thread per connection: a Gateway reboot (no clean FIN/RST)
        # would otherwise leave this thread's recv() blocked on a dead peer
        # and -- if this ran inline in the accept loop -- prevent the next,
        # freshly-reconnected Gateway from ever being accepted.
        threading.Thread(target=serve_connection, args=(conn, addr, names), daemon=True).start()


def serve_connection(conn: socket.socket, addr, names: dict[int, str]) -> None:
    try:
        handle_connection(conn, addr, names)
    except (ConnectionResetError, BrokenPipeError):
        print(f"[video] connection error: {addr}")
    except TimeoutError:
        print(f"[video] no data for {RECV_TIMEOUT_S:.0f}s, dropping stale connection: {addr}")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

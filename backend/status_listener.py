#!/usr/bin/env python3
"""Minimal RPi4-side demo for the Gateway's status/plate uplink (kBackendPort).

Each reading arrives as its own short-lived connection sending one line
"node:occupied:plate\\n" (see main/gateway_uplink.cpp flush()). This just
resolves the node name and logs it -- same node_names.json lookup as
video_listener.py, so a spot's video and its occupancy/plate reading are
both identifiable by the same name.
"""

import socket
import sys

from node_names import load_names, name_for

PORT = 5000


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)  # stdout is block-buffered when redirected to a file
    names = load_names()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(5)
    print(f"[status] listening on :{PORT}")

    while True:
        conn, addr = srv.accept()
        try:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(256)
                if not chunk:
                    break
                data += chunk
            line = data.decode(errors="replace").strip()
            if not line:
                continue
            node_id_str, occupied, plate = line.split(":", 2)
            node_id = int(node_id_str)
            node_name = name_for(node_id, names)
            status = "OCCUPIED" if occupied == "1" else "empty"
            plate_txt = f" plate={plate}" if plate else ""
            print(f"[status] node={node_id} ({node_name}) {status}{plate_txt}")
        except (ConnectionResetError, ValueError) as exc:
            print(f"[status] bad reading from {addr}: {exc}")
        finally:
            conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

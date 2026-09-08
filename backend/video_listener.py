#!/usr/bin/env python3
"""Minimal RPi4-side demo for the Gateway's video uplink (kVideoBackendPort).

Each lane's video is a single continuous H.264 elementary stream now (see
luckfox/rkvenc_subprocess.py: RV1103's own hardware VENC block, not a
per-tick standalone image the way the original PNG placeholder was) --
frames aren't independently viewable the way a PNG/JPEG snapshot is, since
P-frames only decode relative to the frames before them. So this appends
each reassembled chunk-group to frames/<node name>/stream<N>/stream.h264
(one ever-growing file per lane) rather than overwriting a "latest.jpg"
snapshot; feed that file to any H.264-aware player (`ffplay` works) for a
live-ish view, or point ffmpeg's `-f h264 -i` at it. A dropped/incomplete
frame just leaves a gap in the stream -- a real decoder plays through it
with a brief glitch until the next I-frame (gop-interval, see
rkvenc_subprocess.py's H264Encoder), it doesn't corrupt anything after it.

Known gap, unaddressed here (this is still the "minimal demo" this
docstring opens with): stream.h264 has no rotation or size cap and grows
forever for as long as a node keeps running -- fine for a demo/short test,
a real deployment needs this segmented (e.g. roll to a new file every N
minutes/MB, matching how most DVR/NVR software handles continuous
recording) well before RPi4 SD card capacity becomes a concern.

UDP, not TCP -- see kVideoBackendPort's comment in config.h for why (a
dropped video frame is fine to just skip, and losing TCP's delivery-
guarantee machinery buys back real throughput on this link). Each frame is
split by the Gateway into kVideoUdpChunkBytes-sized datagrams (see
VideoChunkHeader in main/gateway_uplink.cpp) and reassembled here; a frame
missing any chunk after kVideoUdpFrameTimeoutMs is just discarded (logged),
not retried -- there's no request-retransmit path over UDP, and the next
frame is only ~300ms away regardless.

Wire format per chunk (matches VideoChunkHeader in main/gateway_uplink.cpp):
  uint8_t origin_node_id
  uint8_t stream_id
  uint16_t seq          (little-endian; which frame)
  uint16_t chunk_index   (little-endian)
  uint16_t chunk_count   (little-endian)
  <up to kVideoUdpChunkBytes bytes of this chunk's slice of the frame>
"""

import os
import socket
import struct
import sys
import time
from dataclasses import dataclass, field

from node_names import load_names, name_for

PORT = 5300
CHUNK_HEADER = struct.Struct("<BBHHH")
FRAMES_DIR = os.path.join(os.path.dirname(__file__), "frames")

# Matches config.h's kVideoUdpFrameTimeoutMs -- how long to wait for a
# frame's remaining chunks before giving up on it. Checked opportunistically
# (see main()'s recv timeout below), not on a separate timer thread -- this
# is a single-threaded UDP receive loop, no per-connection concurrency to
# manage the way the old TCP version needed.
FRAME_TIMEOUT_S = 2.0
# Socket recv timeout, short enough that the timeout sweep below runs often
# even during a quiet stretch with no frames arriving at all.
RECV_TIMEOUT_S = 0.5


@dataclass
class InFlightFrame:
    chunk_count: int
    chunks: dict = field(default_factory=dict)  # chunk_index -> bytes
    first_seen: float = field(default_factory=time.monotonic)

    def complete(self) -> bool:
        return len(self.chunks) == self.chunk_count

    def assemble(self) -> bytes:
        return b"".join(self.chunks[i] for i in range(self.chunk_count))


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)  # stdout is block-buffered when redirected to a file
    names = load_names()
    os.makedirs(FRAMES_DIR, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))
    sock.settimeout(RECV_TIMEOUT_S)
    print(f"[video] listening (UDP) on :{PORT}, appending H.264 under {FRAMES_DIR}/<node name>/streamN/stream.h264")

    # Keyed by (origin_node_id, stream_id) -- only the most recent seq per
    # lane is tracked; a chunk for an older seq than what's in flight means
    # that older frame is a lost cause (its lane moved on), so it's just
    # dropped rather than kept around indefinitely.
    in_flight: dict[tuple[int, int], tuple[int, InFlightFrame]] = {}

    while True:
        try:
            packet, addr = sock.recvfrom(CHUNK_HEADER.size + 65536)
        except TimeoutError:
            _sweep_stale(in_flight)
            continue
        except (ConnectionResetError, OSError):
            # UDP has no connection to reset, but Windows/some platforms
            # surface a peer's "port unreachable" ICMP this way; harmless
            # for a receive loop, just skip this one packet.
            continue

        if len(packet) < CHUNK_HEADER.size:
            continue  # truncated/garbage packet, not a valid chunk
        origin_node_id, stream_id, seq, chunk_index, chunk_count = CHUNK_HEADER.unpack_from(packet)
        payload = packet[CHUNK_HEADER.size:]

        lane = (origin_node_id, stream_id)
        current = in_flight.get(lane)
        if current is None or current[0] != seq:
            # New frame for this lane (or the first one ever seen) --
            # whatever was previously in flight for this lane is now stale
            # (a lane only ever has one frame in flight at a time, since
            # the Gateway sends one frame's chunks before starting the
            # next), so just replace it rather than trying to keep both.
            current = (seq, InFlightFrame(chunk_count=chunk_count))
            in_flight[lane] = current
        current[1].chunks[chunk_index] = payload

        if current[1].complete():
            data = current[1].assemble()
            del in_flight[lane]

            node_name = name_for(origin_node_id, names)
            print(f"[video] node={origin_node_id} ({node_name}) stream={stream_id} "
                  f"seq={seq} bytes={len(data)} chunks={chunk_count}")

            # Appended, not overwritten -- see module docstring: this is a
            # slice of one continuous per-lane H.264 stream, not a
            # standalone image. (spi_sender.py never sends a frame that
            # encoded to zero new bytes in the first place -- see its
            # H264Encoder.encode() call -- so `data` here is never empty.)
            out_dir = os.path.join(FRAMES_DIR, node_name, f"stream{stream_id}")
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "stream.h264"), "ab") as f:
                f.write(data)


def _sweep_stale(in_flight: dict) -> None:
    """Drops any frame that's been waiting on missing chunks longer than
    FRAME_TIMEOUT_S -- otherwise a permanently-lost chunk (not just a late
    one) would leak that lane's InFlightFrame forever and silently stop
    that lane from ever assembling a frame again (a new seq only replaces
    it up above, but that path is never reached if this lane's *next*
    frame's chunks also start arriving and get attributed to a mismatched
    seq check -- simplest to just sweep on a timer instead of reasoning
    through every interleaving)."""
    now = time.monotonic()
    stale = [lane for lane, (_, frame) in in_flight.items() if now - frame.first_seen > FRAME_TIMEOUT_S]
    for lane in stale:
        seq, frame = in_flight.pop(lane)
        print(f"[video] node={lane[0]} stream={lane[1]} seq={seq} incomplete "
              f"({len(frame.chunks)}/{frame.chunk_count} chunks), discarding")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

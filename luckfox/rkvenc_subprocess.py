"""Persistent hardware H.264 encoding via a long-lived rk_mpi_venc_test
subprocess (the LuckFox Pico SDK's own RKMEDIA CLI test tool -- present
on-device at /oem/usr/lib/librockit.so-backed /oem/usr/bin/rk_mpi_venc_test),
fed through named pipes (FIFOs) instead of a static file.

Why a subprocess and named pipes, not a direct ctypes binding to
librockit.so's RK_MPI_VENC_* API (the "obviously more efficient" choice):
a from-scratch ctypes binding was actually built and got far -- correct
struct layouts (verified byte-for-byte against the real SDK headers),
channel creation, a proper MB_POOL for input buffers (required, not
optional: a raw RK_MPI_SYS_MmzAlloc buffer silently never got picked up as
real input), cache flushing, all matched against real reference source
(test_mpi_venc.cpp, the actual source behind this same rk_mpi_venc_test
binary) -- but RK_MPI_VENC_SendFrame's encode never actually completed
(GetStream reported zero packets indefinitely, then GetMB blocked forever
on the next frame), for reasons not resolvable from outside the
closed-source rockit library. This subprocess+FIFO approach reuses that
same binary's own, proven-working internal code path (confirmed: produces
real, ffprobe-valid H.264, decodes correctly) -- it was *never* broken,
only reaching it via raw ctypes was. See luckfox/rkvenc_ctypes.py for the
abandoned binding and the full debugging trail if that's ever worth
revisiting (e.g. if Rockchip ever publishes a newer librockit build).

Both rk_mpi_venc_test's input (-i) and per-channel output file
(<-o dir>/test_<channel_index>.bin) are opened with plain fopen()/fread()/
fwrite() in the tool's own source -- nothing rk_mpi_venc_test-specific
requires them to be regular files. Pre-creating them as FIFOs (mkfifo)
before launching means the *same* proven read-frame/encode/write-stream
loop that the CLI validated on a static file just blocks on each
fopen()/fread() until this module writes/reads through the pipe --
turning one "encode a fixed file, exit" CLI invocation into a persistent
encoder that pays rk_mpi_venc_test's ~2s startup cost (channel/pool
creation) exactly once, not per frame. Round-trip latency once running:
~10-15ms per frame in testing, comfortably inside this project's ~300ms
cadence.

Framing on the output side: rk_mpi_venc_test's own writes are one
fwrite()+fflush() per H.264 pack (a frame's NALs, e.g. SPS+PPS+slice for
an I-frame), not one write per frame -- Linux pipes don't preserve those
write-call boundaries on the read side (multiple small writes can coalesce
into one read(), and one write can split across multiple reads if it
exceeds the pipe's buffer). This module frames by idle timeout instead:
after a frame's input is written, keep reading via select() until a short
quiet period (no more data ready) is observed, assuming that quiet period
means rk_mpi_venc_test has finished flushing that frame's packs. Correct
as long as the encoder can't legitimately pause mid-frame for longer than
the idle timeout, true at this project's frame sizes/bitrates (a whole
frame, even the largest I-frame seen in testing at ~21KB, arrives well
under 15ms).
"""
import fcntl
import os
import select
import subprocess
import time

RKVENC_BIN = "/oem/usr/bin/rk_mpi_venc_test"
FIFO_DIR = "/tmp/rkvenc"

# H264E_NALU codec id for rk_mpi_venc_test's -C flag (see its --help:
# "8:h264, 9:mjpeg, 12:h265, 15:jpeg").
CODEC_H264 = "8"

# The "no more data" quiet period once bytes do start arriving that means
# the frame's done (see module docstring), and the max time to wait for a
# frame's response at all, data or not -- a real P-frame CAN legitimately
# encode to zero new bytes (an unchanged region needs no residual data),
# and 150ms is still generous margin over the ~10-70ms round-trip latency
# actually measured on real hardware for frames that *do* produce data.
# An earlier version of this constant was 2.0s, on the reasoning "generous
# upper bound, we have time" -- true in isolation, but wrong in context:
# _encode_once() uses this same value as the *first* select() wait whenever
# nothing's arrived yet (see below), so a single legitimately-empty frame
# stalled the entire per-frame loop (all 3 lanes) for a full 2 seconds --
# 6x this project's entire ~300ms frame interval, discovered via a
# synthetic all-flat test region rather than by inspection.
_READ_QUIET_S = 0.05
_READ_TOTAL_TIMEOUT_S = 0.15
_OPEN_TIMEOUT_S = 5.0


class RkVencSubprocessError(RuntimeError):
    pass


class H264Encoder:
    """One persistent hardware H.264 encoder for one lane. Not thread-safe
    (matches this project's single-main-loop usage, same as rknn_ctypes.py's
    RknnModel) -- encode() must only ever be called from one task/thread at
    a time."""

    def __init__(self, lane, width, height, bitrate_kbps=1024, gop=60):
        # No frame_rate parameter -- rk_mpi_venc_test's --help only exposes
        # --framerate as an enable/disable flag (0 or 1), not an actual
        # number; whatever num/den the underlying VENC_H264_CBR_S struct's
        # u32SrcFrameRateNum/Den end up with isn't independently
        # CLI-settable in this build, as far as this project has found.
        # An earlier version of this signature accepted (and silently
        # ignored) a frame_rate argument -- removed rather than leave a
        # parameter that looked like it did something but didn't.
        self.lane = lane
        self.width = width
        self.height = height
        self.bitrate_kbps = bitrate_kbps
        self.gop = gop

        os.makedirs(FIFO_DIR, exist_ok=True)
        self.in_fifo = f"{FIFO_DIR}/lane{lane}_in.nv12"
        self.out_dir = f"{FIFO_DIR}/lane{lane}_out"
        self.out_fifo = f"{self.out_dir}/test_0.bin"

        self._proc = None
        self._in_fd = None
        self._out_fd = None
        self._start()

    def _start(self):
        self._cleanup_fds()
        # Restarting (encode()'s retry path) while the old subprocess is
        # merely stuck/misbehaving, not actually dead, would otherwise
        # orphan it here -- a real leak (OS process, and it'd keep the
        # hardware VENC channel it holds occupied, likely breaking the new
        # subprocess's own channel creation right after).
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
        for p in (self.in_fifo, self.out_fifo):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        os.makedirs(self.out_dir, exist_ok=True)
        os.mkfifo(self.in_fifo)
        os.mkfifo(self.out_fifo)

        self._proc = subprocess.Popen(
            [RKVENC_BIN, "-i", self.in_fifo, "-o", self.out_dir,
             "-w", str(self.width), "-h", str(self.height), "-C", CODEC_H264,
             "--rc_mode=1", "-b", str(self.bitrate_kbps), "--gop_size", str(self.gop),
             "-n", "999999999"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        # Output side first: opening a FIFO read end with O_NONBLOCK
        # succeeds immediately regardless of whether a writer exists yet
        # (POSIX) -- rk_mpi_venc_test's own stream-getter thread will open
        # its write end once it gets there, we don't need to wait for it
        # here, only before an actual read (handled by encode()'s select()
        # loop, which just sees "not ready" until then).
        self._out_fd = os.open(self.out_fifo, os.O_RDONLY | os.O_NONBLOCK)

        # Input side: opening for writing blocks until rk_mpi_venc_test's
        # reader thread opens its end -- bounded here so a launch failure
        # (bad binary path, bad args) doesn't hang this process forever.
        deadline = time.monotonic() + _OPEN_TIMEOUT_S
        self._in_fd = None
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                self._cleanup_fds()  # self._out_fd was already opened above, would otherwise leak
                raise RkVencSubprocessError(
                    f"lane {self.lane}: rk_mpi_venc_test exited during startup (code {self._proc.returncode})")
            try:
                self._in_fd = os.open(self.in_fifo, os.O_WRONLY | os.O_NONBLOCK)
                break
            except OSError:
                time.sleep(0.05)
        if self._in_fd is None:
            self._cleanup_fds()
            self._proc.kill()
            raise RkVencSubprocessError(f"lane {self.lane}: rk_mpi_venc_test never opened input FIFO")
        # Drop O_NONBLOCK now that a reader's connected -- see module
        # docstring on why a large (~360KB, bigger than one pipe buffer)
        # frame write needs to block until fully accepted, not
        # partial-write+EAGAIN.
        flags = fcntl.fcntl(self._in_fd, fcntl.F_GETFL)
        fcntl.fcntl(self._in_fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)

    def encode(self, nv12_bytes: bytes) -> bytes:
        """Encodes one tightly-packed NV12(width x height) frame (Y plane
        then interleaved UV at half res -- see spi_sender.py's
        nv12_strip_to_nv12_bytes()), returns the raw H.264 bytes produced
        for it (may be empty if this frame's a cheap P-frame that produced
        no new data by the time the quiet period elapsed -- rare, matches
        real hardware behavior seen in testing, not an error). Restarts
        the subprocess once and retries on any sign it died."""
        try:
            return self._encode_once(nv12_bytes)
        except (BrokenPipeError, OSError, RkVencSubprocessError):
            self._start()
            return self._encode_once(nv12_bytes)

    def _encode_once(self, nv12_bytes: bytes) -> bytes:
        expected = self.width * self.height + (self.width * self.height) // 2
        if len(nv12_bytes) != expected:
            raise RkVencSubprocessError(
                f"expected {expected} bytes (NV12 {self.width}x{self.height}), got {len(nv12_bytes)}")
        if self._proc.poll() is not None:
            raise RkVencSubprocessError(f"lane {self.lane}: rk_mpi_venc_test died (code {self._proc.returncode})")

        os.write(self._in_fd, nv12_bytes)

        chunks = []
        deadline = time.monotonic() + _READ_TOTAL_TIMEOUT_S
        while time.monotonic() < deadline:
            wait = _READ_QUIET_S if chunks else deadline - time.monotonic()
            ready, _, _ = select.select([self._out_fd], [], [], wait)
            if not ready:
                break  # quiet period elapsed with data in hand, or genuinely timed out with none
            chunk = os.read(self._out_fd, 262144)
            if not chunk:
                raise RkVencSubprocessError(f"lane {self.lane}: output FIFO closed (encoder died?)")
            chunks.append(chunk)
        return b"".join(chunks)

    def _cleanup_fds(self):
        for attr in ("_in_fd", "_out_fd"):
            fd = getattr(self, attr, None)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
                setattr(self, attr, None)

    def close(self):
        self._cleanup_fds()
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

"""Per-lane parked-car detection: motion detection gates a parked-car
occupancy check, which in turn gates plate cropping -- each stage only runs
when the cheaper stage before it says it's worth it, so a lane sits at
near-zero cost until something actually happens in frame.

    motion detection (every frame, cheap)
        -> car detection / parked-car check (only after a settle wait)
            -> occupancy (vacant/occupied)
                -> if occupied: crop + hand off for plate reading

Motion detection stays a cheap background-subtraction heuristic (mean
absolute pixel difference on the same 600x400 grayscale snapshot
spi_sender.py already downsamples for the video stream -- no extra decode
cost) -- it's just a coarse "did anything move" gate, not the actual car
detection, so a real model would be wasted effort here.

The occupancy check itself (once a lane settles) is real object detection,
not a heuristic: RV1103 has an NPU (see luckfox/rknn_ctypes.py, a ctypes
binding to the on-device librknnmrt.so -- no rknnlite Python API or
package manager exists on this image to install one) running a
COCO-pretrained YOLOv5n (rknn_model_zoo), checked for its "car" class.
Verified end-to-end on real hardware. check_occupied() in spi_sender.py's
main() still wraps this in a try/except and falls back to this lane's
last known status on any failure (not the heuristic below -- that
fallback is a separate, simpler safety net for testing this module in
isolation, see next paragraph) -- NPU/driver calls are still external
I/O, worth not trusting blindly even once proven working.

LaneDetector doesn't import PIL/rknn directly -- the caller (spi_sender.py)
injects a `check_occupied_fn` callback so this module stays free of those
dependencies and is still testable with a plain heuristic (the
mean_abs_diff fallback below) if no callback is given at all.

Plate OCR cannot run on-device either (no OCR engine, no way to install
one). This only crops the plate-ish region and hands the crop back to the
caller to send onward -- see spi_sender.py, which forwards it to the
ESP32/backend over the video path (a reserved stream_id above the real
video lanes, kPlateStreamBase+lane -- see config.h). Actual text
recognition happens on the backend, which is a real Linux box that can run
tesseract; StatusPacket's plate field stays "" until that lands.
"""
import time

# "sleep 2 minutes" from the project brief -- give a car time to finish
# parking (or leave) before spending a real occupancy check on it, instead
# of reacting to every twitch of motion while it's still moving.
SETTLE_SECONDS = 120

# Mean absolute per-pixel difference (0-255 grayscale) thresholds. Both are
# heuristic and expected to need tuning once run against a real camera feed
# and lot -- there's no calibration step here yet, see module docstring.
MOTION_THRESHOLD = 12
OCCUPANCY_THRESHOLD = 18

# Plate crop region, as a fraction of the lane strip's own W x H -- bottom-
# center heuristic (plates are usually low in frame, roughly centered under
# the car) since there's no real object detector here to actually localize
# one. Tune per-camera once real footage is available.
PLATE_CROP_FRAC = (0.25, 0.75, 0.60, 0.95)  # (x0, x1, y0, y1)


def mean_abs_diff(a: bytes, b: bytes) -> float:
    """Cheap frame-difference metric over two equal-length grayscale byte
    strings. Pure Python (no numpy on this device, see module docstring) --
    O(n), but n is only dst_w*dst_h (600*400 = 240000 bytes) since this
    always runs on the already-downsampled video snapshot, never the raw
    source strip, and only once per lane per captured frame (~every 0.3s),
    which keeps it well within budget."""
    total = 0
    for x, y in zip(a, b):
        total += (x - y) if x > y else (y - x)
    return total / len(a)


class LaneReading:
    """Result of one LaneDetector.process() call -- what changed, if
    anything, so the caller (spi_sender.py) only does extra work (sending a
    status update, cropping+sending a plate image) when there's something
    new to report."""

    __slots__ = ("occupied", "status_changed", "plate_crop_box")

    def __init__(self, occupied: bool, status_changed: bool, plate_crop_box=None):
        self.occupied = occupied
        self.status_changed = status_changed
        # (x0, x1, y0, y1) in the *source* strip's own pixel space, ready to
        # slice directly out of the full-res Y/UV planes -- None unless this
        # call just newly confirmed an occupied spot.
        self.plate_crop_box = plate_crop_box


class LaneDetector:
    """State machine for one parking lane (one of this node's
    kVideoStreamsPerNode strips -- see spi_sender.py). One instance per lane,
    fed that lane's already-downsampled 600x400 grayscale snapshot once per
    captured frame."""

    def __init__(self, lane_index: int, strip_w: int, strip_h: int,
                 settle_seconds: float = SETTLE_SECONDS):
        self.lane_index = lane_index
        self.strip_w = strip_w
        self.strip_h = strip_h
        self.settle_seconds = settle_seconds

        self.state = "idle"  # idle -> settling -> idle
        self.settle_until = 0.0
        self.prev_snapshot = None
        self.empty_reference = None  # learned "no car here" baseline
        self.occupied = False

    def _plate_crop_box(self):
        x0f, x1f, y0f, y1f = PLATE_CROP_FRAC
        return (
            int(self.strip_w * x0f), int(self.strip_w * x1f),
            int(self.strip_h * y0f), int(self.strip_h * y1f),
        )

    def process(self, y_small: bytes, now: float = None, check_occupied_fn=None) -> LaneReading:
        """`check_occupied_fn`, if given, is called with no arguments -- and
        only right when the settle wait elapses, never on every frame -- to
        decide occupancy; it should return a bool. Expected to be a closure
        over this exact call's frame data (see spi_sender.py's real RKNN
        check), so the (comparatively expensive) crop+resize+NPU-inference
        it does only ever happens when this state machine actually needs an
        answer. Falls back to the mean_abs_diff heuristic against
        empty_reference if omitted (e.g. for testing this module alone)."""
        if now is None:
            now = time.time()

        if self.empty_reference is None:
            # First frame ever seen for this lane: no real calibration step
            # exists yet (see module docstring), so assume vacant -- best
            # guess for a baseline to diff future checks against.
            self.empty_reference = y_small
            self.prev_snapshot = y_small
            return LaneReading(occupied=False, status_changed=True)

        if self.state == "idle":
            motion = mean_abs_diff(y_small, self.prev_snapshot)
            self.prev_snapshot = y_small
            if motion > MOTION_THRESHOLD:
                self.state = "settling"
                self.settle_until = now + self.settle_seconds
            # Cheap path: no occupancy re-check, no plate crop, nothing
            # changed to report.
            return LaneReading(occupied=self.occupied, status_changed=False)

        # state == "settling"
        self.prev_snapshot = y_small
        if now < self.settle_until:
            return LaneReading(occupied=self.occupied, status_changed=False)

        # -- Parked-car / occupancy check: only runs once, after the settle
        # wait elapses, not every frame (see module docstring). --
        if check_occupied_fn is not None:
            newly_occupied = check_occupied_fn()
        else:
            diff = mean_abs_diff(y_small, self.empty_reference)
            newly_occupied = diff > OCCUPANCY_THRESHOLD
        was_occupied = self.occupied
        self.occupied = newly_occupied
        self.state = "idle"

        if not newly_occupied:
            self.empty_reference = y_small  # relearn the background, now confirmed empty
            return LaneReading(occupied=False, status_changed=was_occupied)

        if not was_occupied:
            # Newly occupied: crop + hand off for plate reading, one time
            # per parking event (not repeated every settle cycle a car sits
            # there).
            return LaneReading(occupied=True, status_changed=True,
                                plate_crop_box=self._plate_crop_box())
        return LaneReading(occupied=True, status_changed=False)

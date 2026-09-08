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
Once a car's found, a second small YOLOv5n model (keremberke/
yolov5n-license-plate, see spi_sender.py's PLATE_MODEL_PATH) runs on the
car's own region to find the real plate box -- both verified end-to-end
on real hardware, and both stay loaded on the NPU together (see
spi_sender.py's _get_plate_model() for why: this pairing's combined
buffer size fits this board's ~24MB CMA pool fine, confirmed stable over
a 25-iteration real-workload stress test, unlike the reload-per-event
design this replaced). check_occupied() in spi_sender.py's main() still
wraps this in a try/except and falls back to this lane's last known
status on any failure (not the heuristic below --
that fallback is a separate, simpler safety net for testing this module in
isolation, see next paragraph) -- NPU/driver calls are still external
I/O, worth not trusting blindly even once proven working.

LaneDetector doesn't import rknn directly -- the caller (spi_sender.py)
injects a `check_occupied_fn` callback so this module stays free of that
on-device-only dependency and is still testable (off real hardware, no
NPU needed) with a plain heuristic (the mean_abs_diff fallback below) if
no callback is given at all. mean_abs_diff *does* use PIL now (see its own
docstring) -- unlike rknn, PIL is a normal portable dependency any dev
machine running these tests already has, so it doesn't work against that
same testability goal the way an NPU binding would.

Plate OCR cannot run on-device either (no OCR engine, no way to install
one). This only crops the plate-ish region and hands the crop back to the
caller to send onward -- see spi_sender.py, which forwards it to the
ESP32/backend over the video path (a reserved stream_id above the real
video lanes, kPlateStreamBase+lane -- see config.h). Actual text
recognition happens on the backend, which is a real Linux box that can run
tesseract; StatusPacket's plate field stays "" until that lands.
"""
import time

from PIL import Image, ImageChops, ImageStat

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
    strings (only ever the already-downsampled video snapshot, 600x400 =
    240000 bytes, never the raw source strip, and only once per lane per
    captured frame -- see module docstring).

    PIL's ImageChops.difference()+ImageStat, not a hand-rolled Python
    loop -- measured on real hardware: the loop this replaced took ~200ms
    per call (so ~600ms across 3 lanes, every single captured frame,
    every settle-timeout wait notwithstanding -- this ran unconditionally
    in the "idle" state, unlike the NPU calls, which only run once
    settling elapses). An earlier version of this function's docstring
    asserted the loop was "well within budget" -- untested at the time;
    turned out to be the same mistake as spi_sender.py's downsample_plane()
    (see its own docstring for the same story, found and fixed first --
    this one was found by suspecting the same anti-pattern might be
    lurking elsewhere on the same per-lane per-frame hot path, which it
    was). Doesn't care that a/b aren't really 2D -- a pure per-pixel
    absolute-difference-then-mean doesn't need real width/height, just a
    shape PIL will accept, so this reshapes as a single len(a)-wide row."""
    img_a = Image.frombytes("L", (len(a), 1), a)
    img_b = Image.frombytes("L", (len(b), 1), b)
    diff = ImageChops.difference(img_a, img_b)
    return ImageStat.Stat(diff).mean[0]


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
        decide occupancy; it should return (occupied: bool, car_box:
        tuple|None), car_box being crop_plate_png_bytes()'s (x0, x1, y0,
        y1) covering the actually-detected car (see spi_sender.py's
        detect_car()) or None if the caller has no box to offer (occupied
        can still be True with car_box=None). Expected to be a closure over
        this exact call's frame data, so the (comparatively expensive)
        crop+resize+NPU-inference it does only ever happens when this state
        machine actually needs an answer. Falls back to the mean_abs_diff
        heuristic against empty_reference (no box -- see _plate_crop_box())
        if check_occupied_fn is omitted (e.g. for testing this module
        alone)."""
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
        detected_box = None
        if check_occupied_fn is not None:
            newly_occupied, detected_box = check_occupied_fn()
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
            # there). Prefer the real detected box; only fall back to the
            # fixed-fraction guess if the caller didn't have one (e.g. the
            # mean_abs_diff heuristic path, which has no notion of "where").
            box = detected_box if detected_box is not None else self._plate_crop_box()
            return LaneReading(occupied=True, status_changed=True, plate_crop_box=box)
        return LaneReading(occupied=True, status_changed=False)

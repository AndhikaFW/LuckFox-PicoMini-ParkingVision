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

Encoding note: video frames are hardware-encoded H.264 (see
rkvenc_subprocess.py -- RV1103's own VENC block via a persistent
rk_mpi_venc_test subprocess, since this LuckFox image's Pillow build has
no JPEG encoder at all, and PNG -- the original placeholder -- is a poor
fit for a stream of mostly-static frames: real hardware testing measured
~366KB/frame PNG vs ~21KB for an H.264 I-frame and as little as ~20-40
bytes for an unchanged P-frame, since PNG has no notion of "this frame is
almost identical to the last one" the way H.264's inter-frame prediction
does. One encoder per lane, kept resident for the process's lifetime (see
main()) -- same reasoning as detect_car()/detect_plate()'s NPU models
staying loaded rather than reloading per frame. Plate crops (rare, one-off
stills, not a stream) stay PNG -- H.264's inter-frame compression has
nothing to exploit for a single unrelated image, and PNG's lossless
encoding matters more there than for a continuous low-motion video feed.

Also runs each lane's parked-car detection (see parking_detector.py) against
the same downsampled snapshot already computed for its video stream --
motion detection gates a parked-car occupancy check, which gates plate
cropping, so the expensive stages only run when something's actually
changed in frame. Occupancy readings go to the ESP32 as their own SPI
message (kMsgStatus); plate crops (only sent once per new parking event)
ride the same image path as video, on a reserved stream_id per lane.

Requires SPI0 M0 enabled first (not persistent across reboots by default):
    source /usr/bin/luckfox-config noop
    luckfox_config_init
    luckfox_spi_app 1 0 0 1 1 20000000

Also requires models/yolov5n.rknn and models/plate_detector.rknn (this
repo) pushed to RKNN_MODEL_PATH/PLATE_MODEL_PATH below (default
/root/yolov5n.rknn, /root/plate_detector.rknn) for the RKNN car-detection
and plate-detection steps -- see those constants and detect_car()'s/
detect_plate()'s docstrings for what they're for. Both stay loaded on the
NPU together (see _get_plate_model()).
"""
import argparse
import gc
import struct
import sys
import time

import spidev
from PIL import Image

from parking_detector import LaneDetector
from rkvenc_subprocess import H264Encoder

SRC_W, SRC_H = 1920, 1080
Y_SIZE = SRC_W * SRC_H
FRAME_SIZE = Y_SIZE + Y_SIZE // 2

DST_W, DST_H = 600, 400  # kVideoStreamsPerNode streams, this size each (config.h)
STREAMS_PER_NODE = 3
STRIP_W = SRC_W // STREAMS_PER_NODE  # 640px-wide vertical slice per stream
# Plate crops ride the video path on a reserved stream_id per lane, above
# the real video streams -- must match config.h's kPlateStreamBase.
PLATE_STREAM_BASE = STREAMS_PER_NODE

# Must match config.h's kLuckfoxSpiChunkBytes exactly -- both ends assume
# every SPI transaction is this many bytes.
CHUNK_BYTES = 4000

MAGIC = 0x52415046  # "RAPF", must match luckfox_spi.cpp's kMagic
MSG_VIDEO = 0  # video frame or plate crop image -- must match luckfox_spi.cpp's kMsgVideo
MSG_STATUS = 1  # lane occupancy reading -- must match luckfox_spi.cpp's kMsgStatus
# WireHeader: uint32 magic, uint8 msg_type, uint8 stream_id, uint16 seq,
# uint32 data_len (little-endian, packed -- matches the
# __attribute__((packed)) struct on the ESP32 side; both are little-endian
# cores so this lines up as-is).
HEADER_FMT = "<IBBHI"

# Must match config.h's kMaxPlateLen exactly -- the plate field in
# LaneStatusWire (luckfox_spi.cpp) is this many chars + a null terminator.
MAX_PLATE_LEN = 11


def downsample_plane(plane, full_w, full_h, crop_x, crop_w, crop_y, crop_h, dst_w, dst_h,
                      stride=1, elem_offset=0):
    """Nearest-neighbor downsample of the [crop_x, crop_x+crop_w) x
    [crop_y, crop_y+crop_h) region of `plane` (a full_w-wide row buffer)
    into dst_w x dst_h. `full_w` (the real row stride) and `crop_w` (the
    region being downsampled) are separate on purpose -- a crop narrower
    than the full row still needs the full row's stride to find the next
    row's start. `crop_y`/`crop_h` default to a full-height crop (the
    vertical-strip case, see nv12_strip_to_nv12_bytes) but also support a
    sub-rectangle (the plate-crop case, see crop_plate_png_bytes).

    PIL crop()+resize() under the hood, not a hand-rolled pixel loop --
    measured on real hardware: the loop this replaced took ~1.25 *seconds*
    per call (so ~3.75s just to downsample one frame's 3 lanes, against a
    ~300ms target interval -- the actual bottleneck in the whole pipeline,
    dwarfing anything about video encoding). An earlier version of this
    function argued the loop was worth it to avoid PIL's extra buffer
    copies (see stride/elem_offset, which let it read an interleaved U/V
    plane without a separate deinterleave copy) -- true as far as it went,
    but wrong on priorities: a fixed ~2MB PIL Image allocation (freed
    immediately after use) against this device's ~12MB free budget is a
    real but affordable cost, 1.25s of pure-Python interpretation per call
    is not affordable at all, and stride!=1 still needs an interleave
    strip via fast C-level byte slicing first either way -- the loop
    wasn't actually avoiding that copy, just doing the equivalent copy one
    Python-level byte at a time instead."""
    if stride != 1:
        # Fast C-level slice, not a Python loop -- de-interleaves (e.g.
        # NV12's UV plane) into one contiguous half_w x half_h plane
        # before treating it exactly like the stride=1 case below.
        plane = plane[elem_offset::stride]
    img = Image.frombytes("L", (full_w, full_h), plane)
    cropped = img.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))
    del img
    if (dst_w, dst_h) != (crop_w, crop_h):
        resized = cropped.resize((dst_w, dst_h), Image.NEAREST)
        del cropped
        cropped = resized
    out = cropped.tobytes()
    del cropped
    return out


def _ycbcr_region_to_rgb(y_plane, uv_plane, crop_x, crop_w, crop_y, crop_h, dst_w, dst_h):
    """Shared downsample core: NV12 region -> (PIL RGB Image, y_small)."""
    y_small = downsample_plane(y_plane, SRC_W, SRC_H, crop_x, crop_w, crop_y, crop_h, dst_w, dst_h)

    half_w, half_h = SRC_W // 2, SRC_H // 2
    half_crop_x, half_crop_w = crop_x // 2, crop_w // 2
    half_crop_y, half_crop_h = crop_y // 2, crop_h // 2
    dst_half_w, dst_half_h = dst_w // 2, dst_h // 2
    u_small = downsample_plane(uv_plane, half_w, half_h, half_crop_x, half_crop_w, half_crop_y,
                                half_crop_h, dst_half_w, dst_half_h, stride=2, elem_offset=0)
    v_small = downsample_plane(uv_plane, half_w, half_h, half_crop_x, half_crop_w, half_crop_y,
                                half_crop_h, dst_half_w, dst_half_h, stride=2, elem_offset=1)

    y_img = Image.frombytes("L", (dst_w, dst_h), y_small)
    u_img = Image.frombytes("L", (dst_half_w, dst_half_h), u_small).resize((dst_w, dst_h), Image.NEAREST)
    del u_small
    v_img = Image.frombytes("L", (dst_half_w, dst_half_h), v_small).resize((dst_w, dst_h), Image.NEAREST)
    del v_small

    rgb = Image.merge("YCbCr", (y_img, u_img, v_img)).convert("RGB")
    del y_img, u_img, v_img
    return rgb, y_small


def _ycbcr_region_to_png_bytes(y_plane, uv_plane, crop_x, crop_w, crop_y, crop_h, dst_w, dst_h):
    """Shared downsample+encode core: NV12 region -> PNG(dst_w x dst_h)."""
    rgb, y_small = _ycbcr_region_to_rgb(y_plane, uv_plane, crop_x, crop_w, crop_y, crop_h, dst_w, dst_h)
    import io
    buf = io.BytesIO()
    rgb.save(buf, "PNG")
    del rgb
    return buf.getvalue(), y_small


def nv12_strip_to_nv12_bytes(y_plane, uv_plane, stream_id, dst_w=DST_W, dst_h=DST_H):
    """Memory-frugal NV12(1920x1080) strip -> (raw NV12(dst_w x dst_h) bytes,
    y_small) -- the H.264 hardware encoder's native input format (see
    rkvenc_subprocess.py), so this skips the RGB round-trip
    _ycbcr_region_to_rgb() needs entirely: no PIL Image objects, just two
    downsample_plane() calls (Y, then interleaved UV) concatenated.
    Cheaper than the old PNG path on top of feeding a format the encoder
    can use directly."""
    crop_x = stream_id * STRIP_W
    y_small = downsample_plane(y_plane, SRC_W, SRC_H, crop_x, STRIP_W, 0, SRC_H, dst_w, dst_h)

    half_w, half_h = SRC_W // 2, SRC_H // 2
    half_crop_x, half_crop_w = crop_x // 2, STRIP_W // 2
    dst_half_w, dst_half_h = dst_w // 2, dst_h // 2
    u_small = downsample_plane(uv_plane, half_w, half_h, half_crop_x, half_crop_w, 0, half_h,
                                dst_half_w, dst_half_h, stride=2, elem_offset=0)
    v_small = downsample_plane(uv_plane, half_w, half_h, half_crop_x, half_crop_w, 0, half_h,
                                dst_half_w, dst_half_h, stride=2, elem_offset=1)

    uv_small = bytearray(dst_half_w * dst_half_h * 2)
    uv_small[0::2] = u_small
    uv_small[1::2] = v_small
    del u_small, v_small
    return y_small + bytes(uv_small), y_small


def crop_plate_png_bytes(y_plane, uv_plane, stream_id, crop_box):
    """Full-resolution plate crop for one lane -- deliberately NOT
    downsampled to DST_W x DST_H like the video streams (a legible plate
    needs more detail than a 600x400 lane overview does). `crop_box` is
    (x0, x1, y0, y1) in the lane's own strip-local pixel space, as produced
    by parking_detector.LaneDetector (see PLATE_CROP_FRAC there)."""
    x0, x1, y0, y1 = crop_box
    strip_x = stream_id * STRIP_W
    png, _ = _ycbcr_region_to_png_bytes(y_plane, uv_plane, strip_x + x0, x1 - x0, y0, y1 - y0,
                                         x1 - x0, y1 - y0)
    return png


# -- RKNN (NPU) car detection for the occupancy check --
#
# yolov5n.rknn: COCO-pretrained YOLOv5n (rknn_model_zoo/examples/yolov5),
# quantized (i8) for the RV1103 NPU. Input: 640x640 RGB, uint8, NHWC, no
# normalization (quantization is baked into the model, see rknn_model_zoo's
# yolov5.py demo -- the rknn platform branch feeds raw uint8 pixels
# directly). Output: 3 tensors (80x80/40x40/20x20 grids, one per detection
# scale), each 255 channels = 3 anchors x 85 (4 box + 1 objectness + 80
# class scores), already sigmoid-activated inside the model graph.
#
# The occupancy check itself only needs a yes/no "is there a car" signal,
# so it skips the reference demo's full NMS (no need to resolve multiple
# overlapping boxes into one -- max confidence anywhere is enough). It does
# decode the *single* winning cell's box (see _decode_box()) once a car is
# found, to crop the actual detected car instead of a fixed guessed region
# (see PLATE_CROP_FRAC's history in parking_detector.py -- a fixed fraction
# of the whole lane has no idea where the car actually is in frame). Still
# skips decoding box coordinates for every other cell -- those never do
# anything but lose an NMS comparison, see rknn_model_zoo/examples/yolov5/
# python/yolov5.py for the full reference post-processing this only
# partially replicates.
RKNN_MODEL_PATH = "/root/yolov5n.rknn"
RKNN_INPUT_SIZE = 640
CAR_CLASS_INDEX = 2  # 0-indexed into COCO's 80 classes -- see coco_80_labels_list.txt
CHANNELS_PER_ANCHOR = 85  # 4 box + 1 objectness + 80 classes
N_ANCHORS_PER_SCALE = 3
CAR_CONF_THRESH = 0.25  # matches rknn_model_zoo yolov5 demo's OBJ_THRESH

# anchors_yolov5.txt (rknn_model_zoo/examples/yolov5/model/) reshaped
# (3 scales, 3 anchors, 2 (w,h)) -- ANCHORS[scale_idx][anchor_idx] = (w, h),
# in 640x640 model-input pixel units. Needed only for decoding the single
# winning detection's box (see module comment above), not for the
# occupancy yes/no check itself.
ANCHORS = [
    [(10, 13), (16, 30), (33, 23)],
    [(30, 61), (62, 45), (59, 119)],
    [(116, 90), (156, 198), (373, 326)],
]

# Once a car's actual box is known, crop this fraction of its *height*
# (from the bottom) rather than the whole car -- plates sit low on a car,
# so narrowing further within a real detection is still strictly more
# grounded than the old fixed-fraction-of-the-whole-lane guess.
PLATE_WITHIN_CAR_BOTTOM_FRAC = 0.55

# -- Stage 2: plate detection within the already-detected car's region --
#
# plate_detector.rknn: keremberke/yolov5n-license-plate (Hugging Face),
# YOLOv5n architecture -- same conv/C3-only family as yolov5n.rknn above,
# no attention/MatMul, no Pow (see rknn_ctypes.py's module docstring: this
# board's runtime has essentially no CPU-fallback op support, confirmed via
# both LPRNet's Pow and a YOLOv11n plate detector's MatMul failing
# identically even on a newer runtime build -- only plain conv/C3
# architectures like this one are safe here). Single class
# (license_plate), quantized (i8) for RV1103. Its anchors turned out to be
# the stock YOLOv5 defaults (verified against the exported checkpoint's own
# anchor buffer, scaled by stride), identical to ANCHORS above -- no
# separate table needed. Not Indonesia-specific (trained on a global plate
# dataset), but plate *detection* -- finding the rectangle -- doesn't
# depend on character set the way reading does, and it found a real
# Indonesian plate with high confidence in on-hardware testing.
#
# Runs on detect_car()'s whole detected-car box, not the whole lane --
# that's already the likely area, and upsampling a smaller region to
# RKNN_INPUT_SIZE gives more effective resolution than the whole lane
# would. If nothing clears PLATE_CONF_THRESH, callers fall back to
# _car_box_fallback_plate_crop() -- this is a refinement of a real
# detection, not a hard dependency.
PLATE_MODEL_PATH = "/root/plate_detector.rknn"
PLATE_CHANNELS_PER_ANCHOR = 6  # 4 box + 1 objectness + 1 class (license_plate)
PLATE_CLASS_CHANNEL = 5  # single class -- no COCO-style class index needed
PLATE_CONF_THRESH = 0.25

_car_model = None  # lazily loaded, kept resident once loaded -- see _get_car_model()
_plate_model = None  # lazily loaded, kept resident once loaded -- see _get_plate_model()


def _get_car_model():
    """Lazily loads yolov5n.rknn and keeps it resident for the process's
    lifetime -- see _get_plate_model() for why both models stay loaded
    together rather than swapping. Split into its own function (not a
    generic "load this path" helper) because each model now has a fixed,
    dedicated slot rather than sharing one."""
    global _car_model
    if _car_model is None:
        from rknn_ctypes import RknnModel
        _car_model = RknnModel(RKNN_MODEL_PATH)
    return _car_model


def _get_plate_model():
    """Lazily loads plate_detector.rknn and keeps it resident alongside
    the car model for the process's lifetime. An earlier version of this
    closed/reloaded whichever model wasn't currently needed, on the
    (correct, but overly broad) assumption that this board's ~24MB CMA
    pool can't hold two RKNN contexts' zero-copy buffers at once -- true
    for two copies of the *car* model (its 80-class COCO output buffers
    are ~2.15MB each, so two together are ~4.3MB), but this model's
    single-class output buffers are ~8x smaller (~0.26MB), so car+plate
    together only needs ~4.8MB, not ~6.7MB. Confirmed stable keeping both
    resident: a 25-iteration stress test running the real per-cycle
    workload (3-lane video encode + car detection + plate detection) held
    completely flat at ~8MB available RAM the whole way through, no drift
    -- and it removes the reload latency (re-reading the .rknn file,
    rknn_init's graph setup, rknn_create_mem/rknn_set_io_mem for every
    buffer) that swapping paid on every single parking event."""
    global _plate_model
    if _plate_model is None:
        from rknn_ctypes import RknnModel
        _plate_model = RknnModel(PLATE_MODEL_PATH)
    return _plate_model


def _region_to_rknn_input_bytes(y_plane, uv_plane, strip_x0, region_x0, region_w, region_y0, region_h):
    """Letterboxed RKNN_INPUT_SIZE x RKNN_INPUT_SIZE RGB, raw HWC uint8
    bytes for an arbitrary (region_x0, region_w, region_y0, region_h)
    sub-rectangle (in one lane strip's own pixel space, offset by
    strip_x0). Downsamples straight from the source planes to the
    letterboxed inner size in one pass (cheaper than a full-res crop
    followed by a second resize), then pads to a square canvas -- same
    black-pad letterbox both models were converted/calibrated against (see
    rknn_model_zoo's yolov5.py: `pad_color=(0,0,0)`)."""
    scale = min(RKNN_INPUT_SIZE / region_w, RKNN_INPUT_SIZE / region_h)
    inner_w = round(region_w * scale)
    inner_h = round(region_h * scale)

    rgb, _ = _ycbcr_region_to_rgb(y_plane, uv_plane, strip_x0 + region_x0, region_w, region_y0, region_h,
                                   inner_w, inner_h)
    canvas = Image.new("RGB", (RKNN_INPUT_SIZE, RKNN_INPUT_SIZE), (0, 0, 0))
    canvas.paste(rgb, ((RKNN_INPUT_SIZE - inner_w) // 2, (RKNN_INPUT_SIZE - inner_h) // 2))
    del rgb
    return canvas.tobytes()


def strip_to_rknn_input_bytes(y_plane, uv_plane, stream_id):
    """Letterboxed RKNN_INPUT_SIZE x RKNN_INPUT_SIZE RGB for a whole lane
    strip -- yolov5n.rknn's expected input. Just the full-strip case of
    _region_to_rknn_input_bytes()."""
    return _region_to_rknn_input_bytes(y_plane, uv_plane, stream_id * STRIP_W, 0, STRIP_W, 0, SRC_H)


def _find_best_detection(output, grid_h, grid_w, c2, scale, zp, channels_per_anchor, n_anchors, target_channel):
    """Max over all grid cells/anchors of objectness * P(target_channel's
    class) for one output tensor (an array('b', ...) native int8,
    NC1HWC2-tiled layout -- dims [1, c1, grid_h, grid_w, c2], see
    rknn_ctypes.py's module docstring for why it's this and not plain
    NCHW). Shared by detect_car() (channels_per_anchor=85, target_channel=
    5+CAR_CLASS_INDEX) and detect_plate() (channels_per_anchor=6,
    target_channel=PLATE_CLASS_CHANNEL) -- same YOLOv5 head layout either
    way, just a different channel count per anchor and which one is the
    "does this look like the thing we want" channel. Only touches the 2 of
    channels_per_anchor channels that matter (objectness, target class) --
    see module comment above for why box/other-class channels are skipped
    for every *other* cell -- and only dequantizes (raw int8 -> float via
    this tensor's own scale/zp) those same handful of elements instead of
    the whole tensor, on top of not asking the runtime to do it for the
    whole thing in the first place (see RknnModel.run()).

    NC1HWC2 indexing: logical channel c (anchor-major: anchor*
    channels_per_anchor + within-anchor-channel) tiles into (c1_idx,
    c2_idx) = divmod(c, c2). Flattened index for (c1_idx, h, w, c2_idx) in
    a row-major [1, c1, grid_h, grid_w, c2] array is (c1_idx*grid_h*grid_w
    + h*grid_w + w)*c2 + c2_idx -- so all grid_h*grid_w cells for one fixed
    (c1_idx, c2_idx) sit c2 elements apart (everything else in that
    c2-sized inner group is a different logical channel), hence the
    step=c2 slice below instead of a contiguous one.

    Returns (best_conf, anchor_idx, h, w) -- the last three identify which
    single cell to decode a box for if best_conf clears the threshold (see
    _decode_box()); (0.0, None, None, None) if the tensor holds nothing."""
    hw = grid_h * grid_w
    best = 0.0
    best_anchor = best_h = best_w = None
    for anchor in range(n_anchors):
        obj_c1, obj_c2 = divmod(anchor * channels_per_anchor + 4, c2)
        tgt_c1, tgt_c2 = divmod(anchor * channels_per_anchor + target_channel, c2)
        obj_start = obj_c1 * hw * c2 + obj_c2
        tgt_start = tgt_c1 * hw * c2 + tgt_c2
        obj_slice = output[obj_start:obj_start + hw * c2:c2]
        tgt_slice = output[tgt_start:tgt_start + hw * c2:c2]
        for i, (obj_raw, tgt_raw) in enumerate(zip(obj_slice, tgt_slice)):
            obj = (obj_raw - zp) * scale
            tgt = (tgt_raw - zp) * scale
            conf = obj * tgt
            if conf > best:
                best = conf
                best_anchor, best_h, best_w = anchor, i // grid_w, i % grid_w
    return best, best_anchor, best_h, best_w


def _decode_box(output, c2, grid_h, grid_w, anchor_idx, scale_idx, h, w, scale, zp,
                 channels_per_anchor=CHANNELS_PER_ANCHOR, anchors_table=ANCHORS):
    """Decodes the box (center x/y, width/height -> x0,y0,x1,y1) for one
    specific (anchor, grid cell), in RKNN_INPUT_SIZE x RKNN_INPUT_SIZE
    model-input pixel space. Standard YOLOv5 decode (matches
    rknn_model_zoo's yolov5.py box_process(), just for a single cell
    instead of the whole grid at once -- see module comment above for why
    only ever one). channels_per_anchor/anchors_table default to the car
    model's; detect_plate() passes its own channels_per_anchor (its
    anchors_table is the same ANCHORS -- see PLATE_MODEL_PATH's comment,
    its checkpoint's anchors turned out to be the stock YOLOv5 defaults)."""
    stride = RKNN_INPUT_SIZE / grid_w
    anchor_w, anchor_h = anchors_table[scale_idx][anchor_idx]
    hw = grid_h * grid_w

    def read(ch):
        c1_idx, c2_idx = divmod(anchor_idx * channels_per_anchor + ch, c2)
        idx = (c1_idx * hw + h * grid_w + w) * c2 + c2_idx
        return (output[idx] - zp) * scale

    tx, ty, tw, th = read(0), read(1), read(2), read(3)
    cx = (tx * 2 - 0.5 + w) * stride
    cy = (ty * 2 - 0.5 + h) * stride
    bw = (tw * 2) ** 2 * anchor_w
    bh = (th * 2) ** 2 * anchor_h
    return cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2


def _region_box_to_strip_crop(box_640, region_x0, region_w, region_y0, region_h):
    """Maps a box from RKNN_INPUT_SIZE x RKNN_INPUT_SIZE model-input space
    (see _decode_box()) back to the lane strip's own pixel space, undoing
    _region_to_rknn_input_bytes()'s letterbox scale+pad for the
    (region_x0, region_w, region_y0, region_h) sub-rectangle that was fed
    to the model, and offsetting back into strip-local coordinates.
    Clamped to the region's own bounds (a decoded box can't legitimately
    point outside the crop the model actually saw). Returns (x0, x1, y0,
    y1) -- crop_plate_png_bytes()'s expected argument order."""
    scale = min(RKNN_INPUT_SIZE / region_w, RKNN_INPUT_SIZE / region_h)
    inner_w = round(region_w * scale)
    inner_h = round(region_h * scale)
    pad_x = (RKNN_INPUT_SIZE - inner_w) // 2
    pad_y = (RKNN_INPUT_SIZE - inner_h) // 2

    x0, y0, x1, y1 = box_640
    x0 = region_x0 + max(0, min(region_w, (x0 - pad_x) / scale))
    x1 = region_x0 + max(0, min(region_w, (x1 - pad_x) / scale))
    y0 = region_y0 + max(0, min(region_h, (y0 - pad_y) / scale))
    y1 = region_y0 + max(0, min(region_h, (y1 - pad_y) / scale))
    return int(x0), int(x1), int(y0), int(y1)


def _car_box_fallback_plate_crop(car_box):
    """Last-resort plate crop when detect_plate() (the real plate
    detector) finds nothing confident: narrows the car's own box to its
    bottom PLATE_WITHIN_CAR_BOTTOM_FRAC of height (plates sit low on a
    car). This is only ever a fallback now, not the primary path -- it
    used to be applied unconditionally *before* detect_plate() existed,
    which would have actively cut off the true plate location before a
    real detector ever got to look for it if the plate happened to sit
    outside that guessed band (angled parking, unusual plate mounting
    height, an imprecise car box, ...). detect_car() now hands
    detect_plate() its *whole* box to search, and this heuristic only
    kicks in if that search comes back empty."""
    x0, x1, y0, y1 = car_box
    y0 = y1 - (y1 - y0) * PLATE_WITHIN_CAR_BOTTOM_FRAC
    return x0, x1, int(y0), y1


def detect_car(y_plane, uv_plane, stream_id):
    """The real "AI car detection" step -- runs yolov5n.rknn on the NPU for
    one lane's current frame. Returns (present: bool, crop_box: tuple|None)
    -- crop_box is (x0, x1, y0, y1) in the lane strip's own pixel space
    (crop_plate_png_bytes()'s expected order), covering the *whole* actual
    detected car (not pre-narrowed -- see detect_plate(), which searches
    this box for the real plate, and _car_box_fallback_plate_crop(), the
    fallback if that search finds nothing), or None if no car cleared
    CAR_CONF_THRESH anywhere. Meant to be called (lazily, via a closure)
    from parking_detector.LaneDetector.process()'s check_occupied_fn, so
    this NPU inference only ever runs once a lane's settle wait has
    elapsed, not every captured frame.

    Verified end-to-end on real hardware via the zero-copy path (see
    rknn_ctypes.py's module docstring for why zero-copy specifically --
    the "legacy" buffer API rknn_api.h documents as the basic path doesn't
    work on this board's runtime build)."""
    model = _get_car_model()

    input_bytes = strip_to_rknn_input_bytes(y_plane, uv_plane, stream_id)
    outputs = model.run(input_bytes)

    best_conf, best_scale_idx = 0.0, None
    best_anchor = best_h = best_w = None
    for i, output in enumerate(outputs):
        attr = model.native_output_attrs[i]
        grid_h, grid_w, c2 = attr.dims[2], attr.dims[3], attr.dims[4]
        conf, anchor, h, w = _find_best_detection(output, grid_h, grid_w, c2, attr.scale, attr.zp,
                                                   CHANNELS_PER_ANCHOR, N_ANCHORS_PER_SCALE,
                                                   5 + CAR_CLASS_INDEX)
        if conf > best_conf:
            best_conf, best_scale_idx = conf, i
            best_anchor, best_h, best_w = anchor, h, w

    if best_conf < CAR_CONF_THRESH:
        return False, None

    attr = model.native_output_attrs[best_scale_idx]
    grid_h, grid_w, c2 = attr.dims[2], attr.dims[3], attr.dims[4]
    output = outputs[best_scale_idx]
    box_640 = _decode_box(output, c2, grid_h, grid_w, best_anchor, best_scale_idx, best_h, best_w,
                           attr.scale, attr.zp)
    crop_box = _region_box_to_strip_crop(box_640, 0, STRIP_W, 0, SRC_H)
    return True, crop_box


def detect_plate(y_plane, uv_plane, stream_id, search_box):
    """Stage 2, finding the real plate box within detect_car()'s box:
    runs plate_detector.rknn on `search_box` (the *whole* detected car --
    x0, x1, y0, y1 in lane-strip pixel space, straight from detect_car(),
    not pre-narrowed), rather than the whole lane. Returns a (x0, x1, y0,
    y1) box in the same space if a plate cleared PLATE_CONF_THRESH, else
    None -- callers should fall back to _car_box_fallback_plate_crop() in
    that case (this is a refinement of a real detection, not a hard
    dependency; see PLATE_MODEL_PATH's comment).

    Runs alongside the car model, which stays resident too -- see
    _get_plate_model()."""
    model = _get_plate_model()

    x0, x1, y0, y1 = search_box
    region_w, region_h = x1 - x0, y1 - y0
    if region_w <= 0 or region_h <= 0:
        return None
    input_bytes = _region_to_rknn_input_bytes(y_plane, uv_plane, stream_id * STRIP_W, x0, region_w, y0, region_h)
    outputs = model.run(input_bytes)

    best_conf, best_scale_idx = 0.0, None
    best_anchor = best_h = best_w = None
    for i, output in enumerate(outputs):
        attr = model.native_output_attrs[i]
        grid_h, grid_w, c2 = attr.dims[2], attr.dims[3], attr.dims[4]
        conf, anchor, h, w = _find_best_detection(output, grid_h, grid_w, c2, attr.scale, attr.zp,
                                                   PLATE_CHANNELS_PER_ANCHOR, N_ANCHORS_PER_SCALE,
                                                   PLATE_CLASS_CHANNEL)
        if conf > best_conf:
            best_conf, best_scale_idx = conf, i
            best_anchor, best_h, best_w = anchor, h, w

    if best_conf < PLATE_CONF_THRESH:
        return None

    attr = model.native_output_attrs[best_scale_idx]
    grid_h, grid_w, c2 = attr.dims[2], attr.dims[3], attr.dims[4]
    output = outputs[best_scale_idx]
    box_640 = _decode_box(output, c2, grid_h, grid_w, best_anchor, best_scale_idx, best_h, best_w,
                           attr.scale, attr.zp, channels_per_anchor=PLATE_CHANNELS_PER_ANCHOR)
    return _region_box_to_strip_crop(box_640, x0, region_w, y0, region_h)


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

    def _send_message(self, msg_type, stream_id, seq, payload):
        gc.collect()  # reclaim the PIL intermediates from encode_frame() first
        spi = spidev.SpiDev()
        spi.open(self.bus, self.device)
        spi.max_speed_hz = self.speed_hz
        spi.mode = 0
        try:
            header = struct.pack(HEADER_FMT, MAGIC, msg_type, stream_id, seq, len(payload))
            self._send_chunk(spi, header)

            offset = 0
            while offset < len(payload):
                self._send_chunk(spi, payload[offset:offset + CHUNK_BYTES])
                offset += CHUNK_BYTES
        finally:
            spi.close()

    def send_frame(self, stream_id, seq, payload):
        """Video frame or plate crop image -- both are just images, told
        apart by stream_id (see PLATE_STREAM_BASE)."""
        self._send_message(MSG_VIDEO, stream_id, seq, payload)

    def send_status(self, stream_id, seq, occupied, plate=""):
        """One lane's occupancy reading. `plate` is always "" for now (see
        module docstring -- LuckFox can't OCR it, only the backend can, once
        that step exists); wired up already so it's a one-line change there
        once it does."""
        plate_bytes = plate.encode("ascii", errors="replace")[:MAX_PLATE_LEN]
        payload = struct.pack("<B", 1 if occupied else 0) + plate_bytes.ljust(MAX_PLATE_LEN + 1, b"\0")
        self._send_message(MSG_STATUS, stream_id, seq, payload)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("nv12_path", help="raw NV12 recording, e.g. from pi4-camera-stream-noencode")
    ap.add_argument("--frames", type=int, default=0, help="stop after N frames (0 = whole file)")
    ap.add_argument("--interval", type=float, default=0.3, help="seconds between frames (matches kVideoLocalFrameIntervalMs by default)")
    ap.add_argument("--bus", type=int, default=0)
    ap.add_argument("--device", type=int, default=0)
    ap.add_argument("--speed-hz", type=int, default=20_000_000)
    ap.add_argument("--settle-seconds", type=float, default=None,
                     help="override parking_detector.SETTLE_SECONDS (default 120s) -- "
                          "mainly for quick end-to-end testing")
    args = ap.parse_args()

    import os
    total_frames = os.path.getsize(args.nv12_path) // FRAME_SIZE

    sender = SpiFrameSender(args.bus, args.device, args.speed_hz)
    detector_kwargs = {} if args.settle_seconds is None else {"settle_seconds": args.settle_seconds}
    detectors = [LaneDetector(lane, STRIP_W, SRC_H, **detector_kwargs) for lane in range(STREAMS_PER_NODE)]
    # One persistent hardware H.264 encoder per lane, kept resident for the
    # whole run -- see rkvenc_subprocess.py's module docstring for why
    # (each one carries a real ~2s subprocess-startup cost, so paying that
    # per frame instead of once would defeat the point). Built one at a
    # time (not a one-line list comprehension) so a later lane's startup
    # failure closes the earlier lanes' already-launched subprocesses
    # instead of leaking them -- an orphaned rk_mpi_venc_test would keep
    # holding its hardware VENC channel with nothing left able to close it.
    encoders = []
    try:
        for lane in range(STREAMS_PER_NODE):
            encoders.append(H264Encoder(lane, DST_W, DST_H))
    except Exception:
        for enc in encoders:
            enc.close()
        raise
    # atexit, not try/finally around the loop below, so a crash mid-loop
    # still tears down the encoder subprocesses (they'd otherwise outlive
    # this process, each holding its FIFOs open) without having to indent
    # the whole loop body.
    import atexit
    atexit.register(lambda: [enc.close() for enc in encoders])
    seq = 0
    status_seq = [0] * STREAMS_PER_NODE
    plate_seq = [0] * STREAMS_PER_NODE
    sent = 0

    with open(args.nv12_path, "rb") as f:
        while sent < total_frames:
            t0 = time.time()
            y_plane = f.read(Y_SIZE)
            uv_plane = f.read(Y_SIZE // 2)
            now = time.time()

            for stream in range(STREAMS_PER_NODE):
                nv12, y_small = nv12_strip_to_nv12_bytes(y_plane, uv_plane, stream)
                try:
                    h264 = encoders[stream].encode(nv12)
                except Exception as exc:  # noqa: BLE001 -- a subprocess+FIFO encoder is at
                    # least as unpredictable as the NPU calls below, and this lane's video
                    # hiccup shouldn't take down status/occupancy for every lane with it
                    # (matches those calls' own reasoning exactly -- see check_occupied()).
                    print(f"  lane {stream}: H264Encoder.encode failed ({exc}), skipping this frame's video",
                          file=sys.stderr)
                    h264 = b""
                del nv12
                gc.collect()  # free intermediates before spidev opens
                # A cheap P-frame of an unchanged scene can legitimately
                # encode to nothing new by the time encode() gives up
                # waiting (see rkvenc_subprocess.py) -- skip the SPI
                # transaction entirely rather than send an empty payload.
                if h264:
                    sender.send_frame(stream, seq, h264)
                print(f"frame {sent}: stream={stream} seq={seq} "
                      f"{len(h264)} bytes, {time.time()-t0:.2f}s", file=sys.stderr)

                def check_occupied(s=stream):
                    try:
                        present, box = detect_car(y_plane, uv_plane, s)
                    except Exception as exc:  # noqa: BLE001 -- NPU/driver errors are unpredictable
                        # Keep the lane's last known status rather than
                        # crashing the whole pipeline over it -- an NPU
                        # hiccup on one lane's one settle check shouldn't
                        # take down video/other lanes' detection too.
                        print(f"  lane {s}: RKNN detect_car failed ({exc}), "
                              f"keeping previous status", file=sys.stderr)
                        return detectors[s].occupied, None

                    if present and box is not None:
                        # Find the real plate within the whole car box --
                        # best-effort only: a plate-model hiccup, or the
                        # plate detector finding nothing confident,
                        # shouldn't lose the car detection itself, just
                        # fall back to the bottom-of-car heuristic crop
                        # (see detect_plate()'s and
                        # _car_box_fallback_plate_crop()'s docstrings).
                        try:
                            plate_box = detect_plate(y_plane, uv_plane, s, box)
                            box = plate_box if plate_box is not None else _car_box_fallback_plate_crop(box)
                        except Exception as exc:  # noqa: BLE001
                            print(f"  lane {s}: RKNN detect_plate failed ({exc}), "
                                  f"keeping car-box crop", file=sys.stderr)
                            box = _car_box_fallback_plate_crop(box)
                    return present, box

                reading = detectors[stream].process(y_small, now, check_occupied_fn=check_occupied)
                del y_small
                if reading.status_changed:
                    sender.send_status(stream, status_seq[stream], reading.occupied)
                    status_seq[stream] = (status_seq[stream] + 1) & 0xFFFF
                    print(f"  lane {stream}: {'OCCUPIED' if reading.occupied else 'vacant'}",
                          file=sys.stderr)
                if reading.plate_crop_box is not None:
                    plate_png = crop_plate_png_bytes(y_plane, uv_plane, stream, reading.plate_crop_box)
                    gc.collect()
                    sender.send_frame(PLATE_STREAM_BASE + stream, plate_seq[stream], plate_png)
                    plate_seq[stream] = (plate_seq[stream] + 1) & 0xFFFF
                    print(f"  lane {stream}: plate crop sent ({len(plate_png)} bytes)", file=sys.stderr)
                    del plate_png

            del y_plane, uv_plane
            seq = (seq + 1) & 0xFFFF
            sent += 1
            if args.frames and sent >= args.frames:
                break

            time.sleep(args.interval)

    print(f"done, sent {sent} frames ({sent * STREAMS_PER_NODE} total across {STREAMS_PER_NODE} streams)", file=sys.stderr)


if __name__ == "__main__":
    main()

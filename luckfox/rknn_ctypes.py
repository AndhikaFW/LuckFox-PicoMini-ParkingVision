"""Minimal ctypes binding to the RKNN Mini Runtime (librknnmrt.so, present
on-device at /oem/usr/lib/librknnmrt.so on the LuckFox Pico Mini's RV1103).

Why ctypes and not the official Python API: rknn-toolkit2's on-device
counterpart (rknnlite/rknnlite2) is not installed on this LuckFox image, and
there's no package manager here to add it (see parking_detector.py) -- only
the raw C library and its header (rknn_api.h, from the official LuckFox Pico
SDK) exist on-device. This binds just the handful of C API calls needed to
load a model and run inference: rknn_init, rknn_query, rknn_inputs_set,
rknn_run, rknn_outputs_get/release, rknn_destroy.

Struct layouts below are transcribed directly from rknn_api.h and must stay
byte-for-byte in sync with it (field order/types, not marked
__attribute__((packed)) in the header, so this relies on ctypes' default
struct alignment matching the C compiler's -- true for the armv7l target
this actually runs on). rknn_context is uint32_t here specifically because
RV1103 is armv7l (32-bit ARM) -- the header typedefs it uint64_t on every
other architecture (see rknn_api.h's `#ifdef __arm__` guard).
"""
import ctypes as C

_LIB_PATH = "/oem/usr/lib/librknnmrt.so"

RKNN_MAX_DIMS = 16
RKNN_MAX_NAME_LEN = 256

RKNN_QUERY_IN_OUT_NUM = 0
RKNN_QUERY_INPUT_ATTR = 1
RKNN_QUERY_OUTPUT_ATTR = 2

RKNN_TENSOR_UINT8 = 3
RKNN_TENSOR_NHWC = 1

rknn_context = C.c_uint32  # armv7l (__arm__) -- see module docstring


class RknnInputOutputNum(C.Structure):
    _fields_ = [("n_input", C.c_uint32), ("n_output", C.c_uint32)]


class RknnTensorAttr(C.Structure):
    _fields_ = [
        ("index", C.c_uint32),
        ("n_dims", C.c_uint32),
        ("dims", C.c_uint32 * RKNN_MAX_DIMS),
        ("name", C.c_char * RKNN_MAX_NAME_LEN),
        ("n_elems", C.c_uint32),
        ("size", C.c_uint32),
        ("fmt", C.c_int),
        ("type", C.c_int),
        ("qnt_type", C.c_int),
        ("fl", C.c_int8),
        ("zp", C.c_int32),
        ("scale", C.c_float),
        ("w_stride", C.c_uint32),
        ("size_with_stride", C.c_uint32),
        ("pass_through", C.c_uint8),
        ("h_stride", C.c_uint32),
    ]


class RknnInput(C.Structure):
    _fields_ = [
        ("index", C.c_uint32),
        ("buf", C.c_void_p),
        ("size", C.c_uint32),
        ("pass_through", C.c_uint8),
        ("type", C.c_int),
        ("fmt", C.c_int),
    ]


class RknnOutput(C.Structure):
    _fields_ = [
        ("want_float", C.c_uint8),
        ("is_prealloc", C.c_uint8),
        ("index", C.c_uint32),
        ("buf", C.c_void_p),
        ("size", C.c_uint32),
    ]


_lib = C.CDLL(_LIB_PATH)

_lib.rknn_init.argtypes = [C.POINTER(rknn_context), C.c_char_p, C.c_uint32, C.c_uint32, C.c_void_p]
_lib.rknn_init.restype = C.c_int

_lib.rknn_destroy.argtypes = [rknn_context]
_lib.rknn_destroy.restype = C.c_int

_lib.rknn_query.argtypes = [rknn_context, C.c_int, C.c_void_p, C.c_uint32]
_lib.rknn_query.restype = C.c_int

_lib.rknn_inputs_set.argtypes = [rknn_context, C.c_uint32, C.POINTER(RknnInput)]
_lib.rknn_inputs_set.restype = C.c_int

_lib.rknn_run.argtypes = [rknn_context, C.c_void_p]
_lib.rknn_run.restype = C.c_int

_lib.rknn_outputs_get.argtypes = [rknn_context, C.c_uint32, C.POINTER(RknnOutput), C.c_void_p]
_lib.rknn_outputs_get.restype = C.c_int

_lib.rknn_outputs_release.argtypes = [rknn_context, C.c_uint32, C.POINTER(RknnOutput)]
_lib.rknn_outputs_release.restype = C.c_int


class RknnError(RuntimeError):
    pass


def _check(ret, what):
    if ret != 0:
        raise RknnError(f"{what} failed: {ret}")


class RknnModel:
    """One loaded .rknn model, one NPU context. Not thread-safe (matches the
    underlying C API -- each rknn_context is meant to be driven from a
    single thread/task at a time); parking_detector.py only ever calls this
    from spi_sender.py's single main loop, so that's never an issue here."""

    def __init__(self, model_path: str):
        # Loaded into memory and passed as a sized buffer (not the size=0
        # "treat 2nd arg as a filepath" mode rknn_api.h documents) -- matches
        # every reference C example in rknn_model_zoo.
        with open(model_path, "rb") as f:
            model_bytes = f.read()
        self._ctx = rknn_context(0)
        _check(_lib.rknn_init(C.byref(self._ctx), model_bytes, len(model_bytes), 0, None), "rknn_init")

        num = RknnInputOutputNum()
        _check(_lib.rknn_query(self._ctx, RKNN_QUERY_IN_OUT_NUM, C.byref(num), C.sizeof(num)),
               "rknn_query(IN_OUT_NUM)")
        self.n_inputs = num.n_input
        self.n_outputs = num.n_output

        # Every reference example queries input attrs here too, even though
        # this binding doesn't otherwise need them (input size/format are
        # already fixed constants on the Python side) -- kept for parity
        # with the reference flow.
        self.input_attrs = []
        for i in range(self.n_inputs):
            attr = RknnTensorAttr()
            attr.index = i
            _check(_lib.rknn_query(self._ctx, RKNN_QUERY_INPUT_ATTR, C.byref(attr), C.sizeof(attr)),
                   f"rknn_query(INPUT_ATTR, {i})")
            self.input_attrs.append(attr)

        self.output_attrs = []
        for i in range(self.n_outputs):
            attr = RknnTensorAttr()
            attr.index = i
            _check(_lib.rknn_query(self._ctx, RKNN_QUERY_OUTPUT_ATTR, C.byref(attr), C.sizeof(attr)),
                   f"rknn_query(OUTPUT_ATTR, {i})")
            self.output_attrs.append(attr)

    def run(self, input_bytes: bytes):
        """Runs one inference pass with a single NHWC uint8 input (this
        binding only supports the single-input case, all this project
        needs). Returns a list of array('b', ...) -- one per output tensor,
        in this model's *native* quantized int8, not dequantized to float
        (want_float=0). Dequantizing here (want_float=1) would ask the
        runtime to hand back 4 bytes/element instead of 1 -- for
        yolov5n.rknn's 3 output tensors that's needlessly holding ~8.6MB of
        floats on a device with ~18MB free total, when a caller like
        spi_sender.py's car-presence check only ever needs a couple of the
        85 channels per anchor anyway. Callers that need real values
        dequantize themselves with this tensor's own scale/zp (see
        output_attrs[i].scale/.zp), ideally only for the slice they
        actually read."""
        inp = RknnInput()
        inp.index = 0
        buf = C.create_string_buffer(input_bytes, len(input_bytes))
        inp.buf = C.cast(buf, C.c_void_p)
        inp.size = len(input_bytes)
        inp.pass_through = 0
        inp.type = RKNN_TENSOR_UINT8
        inp.fmt = RKNN_TENSOR_NHWC
        _check(_lib.rknn_inputs_set(self._ctx, 1, C.byref(inp)), "rknn_inputs_set")

        _check(_lib.rknn_run(self._ctx, None), "rknn_run")

        outputs = (RknnOutput * self.n_outputs)()
        for i in range(self.n_outputs):
            outputs[i].want_float = 0
            outputs[i].is_prealloc = 0
            outputs[i].index = i
        _check(_lib.rknn_outputs_get(self._ctx, self.n_outputs, outputs, None), "rknn_outputs_get")

        import array
        results = []
        for i in range(self.n_outputs):
            n = outputs[i].size  # 1 byte/element, native int8
            byte_ptr = C.cast(outputs[i].buf, C.POINTER(C.c_int8 * n))
            results.append(array.array("b", byte_ptr.contents))  # copies out of the buf before release

        _lib.rknn_outputs_release(self._ctx, self.n_outputs, outputs)
        return results

    def close(self):
        _lib.rknn_destroy(self._ctx)
        self._ctx = rknn_context(0)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

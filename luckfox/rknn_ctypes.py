"""Minimal ctypes binding to the RKNN Mini Runtime (librknnmrt.so, present
on-device at /oem/usr/lib/librknnmrt.so on the LuckFox Pico Mini's RV1103).

Why ctypes and not the official Python API: rknn-toolkit2's on-device
counterpart (rknnlite/rknnlite2) is not installed on this LuckFox image, and
there's no package manager here to add it (see parking_detector.py) -- only
the raw C library and its header (rknn_api.h, from the official LuckFox Pico
SDK) exist on-device.

Uses the zero-copy memory API (rknn_create_mem/rknn_set_io_mem), not the
"legacy" buffer API (rknn_inputs_set/rknn_outputs_get) rknn_api.h documents
as the basic path and every rknn_model_zoo reference example uses. That
legacy path fails on this board's runtime build with RKNN_ERR_PARAM_INVALID
(-5, logged as "context config invalid") on every call, for reasons never
fully root-caused (checked: buffer construction, pass_through mode, init
flags, context handle size, runtime power state, regulator/clock state --
see git history on this file for the debugging trail) -- rknn_init/
rknn_query always succeed with correct metadata, only actually submitting a
job through the legacy path fails. Zero-copy works end-to-end (verified:
rknn_run returns 0 and produces real, varied, non-zero output), with one
catch: output memory must be bound using each tensor's *native* attributes
(RKNN_QUERY_NATIVE_OUTPUT_ATTR, not the plain RKNN_QUERY_OUTPUT_ATTR) --
binding with the logical NHWC attrs fails with "Unsupport output: <name>
for NPU NHWC". Native output layout is NC1HWC2 (channel-tiled: dims
[N, C1, H, W, C2], both C1 and C2 are 16 for this model, tiling 255 logical
channels into ceil(255/16)=16 groups of 16 -- logical channel c lives at
(c1, c2) = divmod(c, C2)), not the plain NCHW the legacy path's logical
attrs describe -- callers indexing into run()'s output arrays need to
account for this (see spi_sender.py's _max_car_confidence()).

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
RKNN_QUERY_NATIVE_OUTPUT_ATTR = 9  # NC1HWC2, tiled -- required for output rknn_set_io_mem

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


class RknnTensorMem(C.Structure):
    _fields_ = [
        ("virt_addr", C.c_void_p),
        ("phys_addr", C.c_uint64),
        ("fd", C.c_int32),
        ("offset", C.c_int32),
        ("size", C.c_uint32),
        ("flags", C.c_uint32),
        ("priv_data", C.c_void_p),
    ]


_lib = C.CDLL(_LIB_PATH)

_lib.rknn_init.argtypes = [C.POINTER(rknn_context), C.c_char_p, C.c_uint32, C.c_uint32, C.c_void_p]
_lib.rknn_init.restype = C.c_int

_lib.rknn_destroy.argtypes = [rknn_context]
_lib.rknn_destroy.restype = C.c_int

_lib.rknn_query.argtypes = [rknn_context, C.c_int, C.c_void_p, C.c_uint32]
_lib.rknn_query.restype = C.c_int

_lib.rknn_run.argtypes = [rknn_context, C.c_void_p]
_lib.rknn_run.restype = C.c_int

_lib.rknn_create_mem.argtypes = [rknn_context, C.c_uint32]
_lib.rknn_create_mem.restype = C.POINTER(RknnTensorMem)

_lib.rknn_set_io_mem.argtypes = [rknn_context, C.POINTER(RknnTensorMem), C.POINTER(RknnTensorAttr)]
_lib.rknn_set_io_mem.restype = C.c_int

_lib.rknn_destroy_mem.argtypes = [rknn_context, C.POINTER(RknnTensorMem)]
_lib.rknn_destroy_mem.restype = C.c_int


class RknnError(RuntimeError):
    pass


def _check(ret, what):
    if ret != 0:
        raise RknnError(f"{what} failed: {ret}")


_NPU_POWER_CONTROL = "/sys/devices/platform/ff660000.npu/power/control"


def _keep_npu_awake():
    """Disables the NPU's runtime-PM autosuspend by writing "on" to its
    power/control sysfs node. Not confirmed to be strictly required (the
    zero-copy fix below was found and verified with this already set), but
    it was suspended (power/runtime_status: "suspended") the first time
    this was investigated, and this write is cheap and idempotent -- safer
    to keep forcing it than to find out the hard way it mattered after a
    reboot resets it (this setting doesn't persist). Silently does nothing
    if the sysfs node doesn't exist (e.g. different kernel build) rather
    than failing model load over a best-effort nudge."""
    try:
        with open(_NPU_POWER_CONTROL, "w") as f:
            f.write("on")
    except OSError:
        pass


class RknnModel:
    """One loaded .rknn model, one NPU context, with persistent zero-copy
    I/O buffers (allocated once at load time, reused across run() calls --
    matches the zero-copy API's intended usage and avoids repeated
    rknn_create_mem/rknn_destroy_mem churn per inference). Not thread-safe
    (matches the underlying C API -- each rknn_context is meant to be
    driven from a single thread/task at a time); parking_detector.py only
    ever calls this from spi_sender.py's single main loop, so that's never
    an issue here."""

    def __init__(self, model_path: str):
        _keep_npu_awake()

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
        if self.n_inputs != 1:
            raise RknnError(f"this binding only supports single-input models, got {self.n_inputs}")

        self.input_attrs = []
        for i in range(self.n_inputs):
            attr = RknnTensorAttr()
            attr.index = i
            _check(_lib.rknn_query(self._ctx, RKNN_QUERY_INPUT_ATTR, C.byref(attr), C.sizeof(attr)),
                   f"rknn_query(INPUT_ATTR, {i})")
            self.input_attrs.append(attr)

        # Logical (NHWC) attrs -- exposed for callers that want a plain,
        # human-readable shape/dtype (e.g. spi_sender.py reads dims[2:4] for
        # grid_h/grid_w, and scale/zp, both identical between logical and
        # native attrs). NOT used for rknn_set_io_mem below -- see
        # native_output_attrs and the module docstring for why.
        self.output_attrs = []
        for i in range(self.n_outputs):
            attr = RknnTensorAttr()
            attr.index = i
            _check(_lib.rknn_query(self._ctx, RKNN_QUERY_OUTPUT_ATTR, C.byref(attr), C.sizeof(attr)),
                   f"rknn_query(OUTPUT_ATTR, {i})")
            self.output_attrs.append(attr)

        self.native_output_attrs = []
        for i in range(self.n_outputs):
            attr = RknnTensorAttr()
            attr.index = i
            _check(_lib.rknn_query(self._ctx, RKNN_QUERY_NATIVE_OUTPUT_ATTR, C.byref(attr), C.sizeof(attr)),
                   f"rknn_query(NATIVE_OUTPUT_ATTR, {i})")
            self.native_output_attrs.append(attr)

        in_attr = self.input_attrs[0]
        self._in_mem_ptr = _lib.rknn_create_mem(self._ctx, in_attr.size)
        if not self._in_mem_ptr:
            raise RknnError("rknn_create_mem failed for input")
        _check(_lib.rknn_set_io_mem(self._ctx, self._in_mem_ptr, C.byref(in_attr)), "rknn_set_io_mem(input)")

        self._out_mem_ptrs = []
        for attr in self.native_output_attrs:
            mem_ptr = _lib.rknn_create_mem(self._ctx, attr.size)
            if not mem_ptr:
                raise RknnError(f"rknn_create_mem failed for output {attr.index}")
            _check(_lib.rknn_set_io_mem(self._ctx, mem_ptr, C.byref(attr)),
                   f"rknn_set_io_mem(output {attr.index})")
            self._out_mem_ptrs.append(mem_ptr)

    def run(self, input_bytes: bytes):
        """Runs one inference pass with a single NHWC uint8 input (this
        binding only supports the single-input case, all this project
        needs). Returns a list of array('b', ...) -- one per output tensor,
        in this model's *native* quantized int8, NC1HWC2-tiled layout (see
        module docstring), not dequantized to float and not reshaped to
        logical NCHW. Callers dequantize/reindex themselves using this
        tensor's own scale/zp/dims (native_output_attrs), ideally only for
        the slice they actually need -- see spi_sender.py's
        _max_car_confidence() for why (asking the runtime to dequantize
        whole tensors we mostly discard would cost ~8.6MB on a device with
        ~18MB free)."""
        in_attr = self.input_attrs[0]
        if len(input_bytes) != in_attr.size:
            raise RknnError(f"input size mismatch: got {len(input_bytes)}, model wants {in_attr.size}")
        C.memmove(self._in_mem_ptr.contents.virt_addr, input_bytes, in_attr.size)

        _check(_lib.rknn_run(self._ctx, None), "rknn_run")

        import array
        results = []
        for mem_ptr in self._out_mem_ptrs:
            mem = mem_ptr.contents
            n = mem.size
            byte_ptr = C.cast(mem.virt_addr, C.POINTER(C.c_int8 * n))
            results.append(array.array("b", byte_ptr.contents))  # copies before the buffer's reused next run()
        return results

    def close(self):
        for mem_ptr in getattr(self, "_out_mem_ptrs", []):
            _lib.rknn_destroy_mem(self._ctx, mem_ptr)
        if getattr(self, "_in_mem_ptr", None):
            _lib.rknn_destroy_mem(self._ctx, self._in_mem_ptr)
        _lib.rknn_destroy(self._ctx)
        self._ctx = rknn_context(0)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

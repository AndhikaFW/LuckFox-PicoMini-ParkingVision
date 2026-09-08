"""NOT USED -- does not work, kept only for its debugging trail. Real
encoding runs through rkvenc_subprocess.py instead (a persistent
rk_mpi_venc_test subprocess fed via named pipes), which does work and is
what's actually wired into spi_sender.py.

The RkH264Encoder class below creates a channel and accepts SendFrame
calls without error, but GetStream reports zero packets indefinitely for
every frame sent, and the next SendFrame's RK_MPI_MB_GetMB then blocks
forever waiting for a buffer the pipeline never releases -- i.e. the
encode itself never actually completes, for reasons not resolvable from
outside the closed-source rockit library (every observable difference
from the two working reference examples found -- test_mpi_venc.cpp,
smart_door_venc.c -- was matched and fixed: struct/union sizing, the
required MB_POOL instead of a raw MmzAlloc buffer, cache flushing, -1
timeout semantics, bByFrame, SetChnParam/u32PollWakeUpFrmCnt -- without
result). Worth revisiting only if Rockchip ever publishes a newer
librockit build, or a way to get diagnostic output from inside it.

ctypes binding to the RV1103's hardware video encoder (H.264/H.265/MJPEG/
JPEG), via librockit.so's public RKMEDIA "RK_MPI" C API -- present on-device
at /oem/usr/lib/librockit.so. Struct/function definitions transcribed
directly from the real SDK headers (rk_mpi_venc.h, rk_mpi_sys.h,
rk_comm_venc.h, rk_comm_video.h, rk_comm_rc.h, rk_comm_mb.h, rk_common.h,
rk_type.h -- found on the build host at
~/luckfox-pico/media/rockit/rockit/mpi/sdk/include/), not guessed: this is
the same public Rockchip RKMEDIA SDK used across their RV110x/RK3xxx product
line, and the same one the vendor's own rk_mpi_venc_test/simple_vi_bind_venc_*
sample binaries link against (confirmed via `readelf -d`, which is how the
RK_MPI_VENC_*/RK_MPI_SYS_*/RK_MPI_MB_* symbols below were found in the first
place -- they're absent from the lower-level librockchip_mpp.so, a different,
lower-level library despite the similar name).

Why this exists: on-device Pillow has no JPEG encoder at all (no libjpeg on
this image -- see spi_sender.py's module docstring), and even if it did,
JPEG is a poor fit for a *stream* of frames -- most of a mostly-static
parking-lot scene doesn't change frame to frame, which H.264's inter-frame
(P-frame) prediction exploits and JPEG's intra-only compression can't.
Measured on real footage: ~29KB/frame average (H.264, 10-frame static-scene
CBR@1024kbps) vs ~366KB/frame (the current PNG placeholder) -- about 12x
smaller even before any tuning. (JPEG rate control was also tested via the
vendor's rk_mpi_venc_test CLI and found to be non-functional in this SDK
build -- QP 60 and QP 99 produced byte-identical output -- one more reason
H.264 is the actual target here, not just the "better" one.)

Why a persistent ctypes binding and not the CLI tool: rk_mpi_venc_test
works (verified: produces valid, ffprobe-decodable H.264), but each
invocation carries ~2s of fixed RK_MPI_SYS_Init/CreateChn/DestroyChn
overhead -- the actual hardware encode is fast (~30-40ms per frame, from
the tool's own timestamped log output), but re-paying 2s of setup per frame
is far too slow at this project's ~300ms/frame cadence. This binding sets
the channel up once (RkH264Encoder.__init__) and reuses it across encode()
calls, same pattern as rknn_ctypes.py's RknnModel keeping the NPU context
resident instead of reloading per inference.

Struct layouts below are NOT marked __attribute__((packed)) in the real
headers, so -- same reasoning as rknn_ctypes.py's module docstring -- this
relies on ctypes' default struct alignment matching the C compiler's, which
is only guaranteed because this runs on-device (armv7l), the same target
the real .so was compiled for. Union fields (VENC_ATTR_S's per-codec
sub-attrs, VENC_RC_ATTR_S's per-mode RC params, VENC_STREAM_S's per-codec
stream-info) are only declared here using their *largest* real variant --
enough for ctypes to compute the correct total struct size (required for
memory safety: RK_MPI_VENC_GetStream writes a real, full-size
VENC_STREAM_S through the pointer we give it, so an under-sized ctypes
struct would let it write past our allocation) even though this binding
only reads the handful of fields it actually needs (H.264's case).
"""
import ctypes as C

_LIB_PATH = "/oem/usr/lib/librockit.so"

# -- rk_type.h --
RK_S32 = C.c_int32
RK_U32 = C.c_uint32
RK_U64 = C.c_uint64
RK_S64 = C.c_int64
RK_BOOL = C.c_int32  # enum {RK_FALSE=0, RK_TRUE=1}

# -- rk_common.h --
VENC_CHN = C.c_int32


class MppChnS(C.Structure):
    _fields_ = [
        ("enModId", C.c_int32),
        ("s32DevId", RK_S32),
        ("s32ChnId", RK_S32),
    ]


RK_ID_VENC = 4  # rkMOD_ID_E, only value this binding ever needs


class RectS(C.Structure):
    _fields_ = [("s32X", RK_S32), ("s32Y", RK_S32), ("u32Width", RK_U32), ("u32Height", RK_U32)]

# -- rk_comm_mb.h --
MB_BLK = C.c_void_p
MB_POOL = RK_U32

MB_MAX_COMM_POOLS = 16
MB_INVALID_POOLID = 0xFFFFFFFF
MB_ALLOC_TYPE_DMA = 0


class MbPoolConfigS(C.Structure):
    _fields_ = [
        ("u64MBSize", RK_U64),
        ("u32MBCnt", RK_U32),
        ("enRemapMode", C.c_int32),
        ("enAllocType", C.c_int32),
        ("enDmaType", C.c_int32),
        ("bPreAlloc", RK_BOOL),
        ("bNotDelete", RK_BOOL),
    ]


class MbExtConfigS(C.Structure):
    _fields_ = [
        ("pu8VirAddr", C.c_void_p),
        ("u64PhyAddr", RK_U64),
        ("s32Fd", RK_S32),
        ("u64Size", RK_U64),
        ("pFreeCB", C.c_void_p),  # RK_MPI_MB_FREE_CB, unused (RK_NULL) here
        ("pOpaque", C.c_void_p),
    ]


# -- rk_comm_video.h --
RK_MAX_COLOR_COMPONENT = 2

# PIXEL_FORMAT_E: only the one this binding produces (NV12)
RK_FMT_YUV420SP = 0  # "YYYY... UV..." -- exactly NV12 semi-planar 4:2:0

# VIDEO_FIELD_E / VIDEO_FORMAT_E / COMPRESS_MODE_E / DYNAMIC_RANGE_E /
# COLOR_GAMUT_E -- only the values this binding sets, others unused
VIDEO_FIELD_FRAME = 0x4
VIDEO_FORMAT_LINEAR = 0
COMPRESS_MODE_NONE = 0
DYNAMIC_RANGE_SDR8 = 0
COLOR_GAMUT_BT601 = 0


class VideoFrameS(C.Structure):
    _fields_ = [
        ("pMbBlk", MB_BLK),
        ("u32Width", RK_U32),
        ("u32Height", RK_U32),
        ("u32VirWidth", RK_U32),
        ("u32VirHeight", RK_U32),
        ("enField", C.c_int32),
        ("enPixelFormat", C.c_int32),
        ("enVideoFormat", C.c_int32),
        ("enCompressMode", C.c_int32),
        ("enDynamicRange", C.c_int32),
        ("enColorGamut", C.c_int32),
        ("pVirAddr", C.c_void_p * RK_MAX_COLOR_COMPONENT),
        ("u32TimeRef", RK_U32),
        ("u64PTS", RK_U64),
        ("u64PrivateData", RK_U64),
        ("u32FrameFlag", RK_U32),
    ]


class VideoFrameInfoS(C.Structure):
    _fields_ = [("stVFrame", VideoFrameS)]


class PicBufAttrS(C.Structure):
    _fields_ = [
        ("u32Width", RK_U32),
        ("u32Height", RK_U32),
        ("enPixelFormat", C.c_int32),
        ("enCompMode", C.c_int32),
    ]


class MbPicCalS(C.Structure):
    _fields_ = [
        ("u32MBSize", RK_U32),
        ("u32VirWidth", RK_U32),
        ("u32VirHeight", RK_U32),
    ]


# -- rk_comm_rc.h --
VENC_RC_MODE_H264CBR = 1


class VencH264CbrS(C.Structure):
    _fields_ = [
        ("u32Gop", RK_U32),
        ("u32SrcFrameRateNum", RK_U32),
        ("u32SrcFrameRateDen", RK_U32),
        ("fr32DstFrameRateNum", RK_U32),
        ("fr32DstFrameRateDen", RK_U32),
        ("u32BitRate", RK_U32),
        ("u32StatTime", RK_U32),
    ]


class VencRcAttrUnion(C.Union):
    # stH264Cbr (28 bytes) is the real member this binding sets, but it is
    # NOT the union's largest real-C variant -- VENC_H264_VBR_S/AVBR_S/
    # FIXQP_S (and their H265 aliases) are 32 bytes (one more RK_U32 field
    # each). An earlier version of this binding declared only stH264Cbr
    # here, silently under-sizing the whole VencChnAttrS struct by 4 bytes
    # and shifting every field the real library reads after it -- confirmed
    # on real hardware: RK_MPI_VENC_StartRecvFrame failed with an ioctl
    # EFAULT ("Bad address") from a corrupted attr struct. _size_pad forces
    # the correct 32-byte union size without needing to model the other
    # variants' field names (never read/written by this binding).
    _fields_ = [("stH264Cbr", VencH264CbrS), ("_size_pad", C.c_uint8 * 32)]


class VencRcAttrS(C.Structure):
    _fields_ = [
        ("enRcMode", C.c_int32),
        ("u", VencRcAttrUnion),
    ]


# -- rk_comm_venc.h --
RK_VIDEO_ID_AVC = 8  # RK_CODEC_ID_E -- H.264/AVC, matches rk_mpi_venc_test's -C 8


class VencAttrH264S(C.Structure):
    _fields_ = [("u32Level", RK_U32)]


class VencAttrUnion(C.Union):
    # Same union-sizing issue as VencRcAttrUnion above: stAttrH264e is only
    # 4 bytes, but VENC_ATTR_JPEG_S (bSupportDCF + VENC_MPF_CFG_S{u8 +pad+
    # 2x SIZE_S} + enReceiveMode) is 28 bytes -- the real largest variant.
    # _size_pad forces the correct size.
    _fields_ = [("stAttrH264e", VencAttrH264S), ("_size_pad", C.c_uint8 * 28)]


class VencAttrS(C.Structure):
    _fields_ = [
        ("enType", C.c_int32),
        ("u32MaxPicWidth", RK_U32),
        ("u32MaxPicHeight", RK_U32),
        ("enPixelFormat", C.c_int32),
        ("enMirror", C.c_int32),
        ("u32BufSize", RK_U32),
        ("u32Profile", RK_U32),
        ("bByFrame", RK_BOOL),
        ("u32PicWidth", RK_U32),
        ("u32PicHeight", RK_U32),
        ("u32VirWidth", RK_U32),
        ("u32VirHeight", RK_U32),
        ("u32StreamBufCnt", RK_U32),
        ("u", VencAttrUnion),
    ]


VENC_GOPMODE_NORMALP = 1


class VencGopAttrS(C.Structure):
    _fields_ = [
        ("enGopMode", C.c_int32),
        ("s32VirIdrLen", RK_S32),
        ("u32MaxLtrCount", RK_U32),
        ("u32TsvcPreload", RK_U32),
    ]


class VencChnAttrS(C.Structure):
    _fields_ = [
        ("stVencAttr", VencAttrS),
        ("stRcAttr", VencRcAttrS),
        ("stGopAttr", VencGopAttrS),
    ]


class VencRecvPicParamS(C.Structure):
    _fields_ = [("s32RecvPicNum", RK_S32)]


class VencScaleRectS(C.Structure):
    _fields_ = [("stSrc", RectS), ("stDst", RectS)]


class VencCropInfoS(C.Structure):
    _fields_ = [
        ("enCropType", C.c_int32),
        ("stCropRect", RectS),
        ("stScaleRect", VencScaleRectS),
    ]


class VencFrameRateS(C.Structure):
    _fields_ = [
        ("bEnable", RK_BOOL),
        ("s32SrcFrmRateNum", RK_S32),
        ("s32SrcFrmRateDen", RK_S32),
        ("s32DstFrmRateNum", RK_S32),
        ("s32DstFrmRateDen", RK_S32),
    ]


class VencChnParamS(C.Structure):
    _fields_ = [
        ("bColor2Grey", RK_BOOL),
        ("u32Priority", RK_U32),
        ("u32MaxStrmCnt", RK_U32),
        # "the frame num needed to wake up obtaining streams" -- left at
        # the library's own internal default (never explicitly set) in an
        # earlier version of this binding, which never called
        # RK_MPI_VENC_SetChnParam at all. That earlier version's
        # GetStream calls consistently succeeded (ret=0) but reported
        # zero packs, indefinitely, for a single sent frame -- consistent
        # with this needing more frames queued than were ever sent before
        # a "wake up" is considered to have happened. Explicitly set to 1
        # so a single SendFrame is enough.
        ("u32PollWakeUpFrmCnt", RK_U32),
        ("stCropCfg", VencCropInfoS),
        ("stFrameRate", VencFrameRateS),
    ]


class VencPackInfoS(C.Structure):
    _fields_ = [
        ("u32PackType", C.c_int32),  # VENC_DATA_TYPE_U, union-of-enums -> int32
        ("u32PackOffset", RK_U32),
        ("u32PackLength", RK_U32),
    ]


class VencPackS(C.Structure):
    _fields_ = [
        ("pMbBlk", MB_BLK),
        ("u32Len", RK_U32),
        ("u64PTS", RK_U64),
        ("bFrameEnd", RK_BOOL),
        ("bStreamEnd", RK_BOOL),
        ("DataType", C.c_int32),
        ("u32Offset", RK_U32),
        ("u32DataNum", RK_U32),
        ("stPackInfo", VencPackInfoS * 8),
    ]


class VencSseInfoS(C.Structure):
    _fields_ = [("bSSEEn", RK_BOOL), ("u32SSEVal", RK_U32)]


VENC_QP_SGRM_NUM = 52


class VencStreamInfoH265S(C.Structure):
    """The largest of VENC_STREAM_S's first union's real variants (H264/
    JPEG/H265/PRORES info) -- declared purely so the union (and therefore
    VencStreamS) ends up the correct total size; this binding never reads
    through this member itself (see module docstring)."""
    _fields_ = [
        ("u32PicBytesNum", RK_U32),
        ("u32Inter64x64CuNum", RK_U32),
        ("u32Inter32x32CuNum", RK_U32),
        ("u32Inter16x16CuNum", RK_U32),
        ("u32Inter8x8CuNum", RK_U32),
        ("u32Intra32x32CuNum", RK_U32),
        ("u32Intra16x16CuNum", RK_U32),
        ("u32Intra8x8CuNum", RK_U32),
        ("u32Intra4x4CuNum", RK_U32),
        ("enRefType", C.c_int32),
        ("u32UpdateAttrCnt", RK_U32),
        ("u32StartQp", RK_U32),
        ("u32MeanQp", RK_U32),
        ("bPSkip", RK_BOOL),
    ]


class VencStreamInfoUnion(C.Union):
    _fields_ = [("stH265Info", VencStreamInfoH265S)]


class VencStreamAdvanceInfoH265S(C.Structure):
    """Same purpose as VencStreamInfoH265S above -- largest variant of
    VENC_STREAM_S's second union, declared only for correct sizing."""
    _fields_ = [
        ("u32ResidualBitNum", RK_U32),
        ("u32HeadBitNum", RK_U32),
        ("u32MadiVal", RK_U32),
        ("u32MadpVal", RK_U32),
        ("dPSNRVal", C.c_double),
        ("u32MseLcuCnt", RK_U32),
        ("u32MseSum", RK_U32),
        ("stSSEInfo", VencSseInfoS * 8),
        ("u32QpHstgrm", RK_U32 * VENC_QP_SGRM_NUM),
        ("u32MoveScene32x32Num", RK_U32),
        ("u32MoveSceneBits", RK_U32),
    ]


class VencStreamAdvanceInfoUnion(C.Union):
    _fields_ = [("stAdvanceH265Info", VencStreamAdvanceInfoH265S)]


class VencStreamS(C.Structure):
    _fields_ = [
        ("pstPack", C.POINTER(VencPackS)),
        ("u32PackCount", RK_U32),
        ("u32Seq", RK_U32),
        ("info", VencStreamInfoUnion),
        ("advanceInfo", VencStreamAdvanceInfoUnion),
    ]


_lib = C.CDLL(_LIB_PATH)

_lib.RK_MPI_SYS_Init.argtypes = []
_lib.RK_MPI_SYS_Init.restype = RK_S32

_lib.RK_MPI_SYS_Exit.argtypes = []
_lib.RK_MPI_SYS_Exit.restype = RK_S32

_lib.RK_MPI_SYS_MmzAlloc.argtypes = [C.POINTER(MB_BLK), C.c_char_p, C.c_char_p, RK_U32]
_lib.RK_MPI_SYS_MmzAlloc.restype = RK_S32

_lib.RK_MPI_SYS_MmzFree.argtypes = [MB_BLK]
_lib.RK_MPI_SYS_MmzFree.restype = RK_S32

_lib.RK_MPI_MB_Handle2VirAddr.argtypes = [MB_BLK]
_lib.RK_MPI_MB_Handle2VirAddr.restype = C.c_void_p

_lib.RK_MPI_SYS_MmzFlushCache.argtypes = [MB_BLK, RK_BOOL]
_lib.RK_MPI_SYS_MmzFlushCache.restype = RK_S32

_lib.RK_MPI_MB_CreatePool.argtypes = [C.POINTER(MbPoolConfigS)]
_lib.RK_MPI_MB_CreatePool.restype = MB_POOL

_lib.RK_MPI_MB_DestroyPool.argtypes = [MB_POOL]
_lib.RK_MPI_MB_DestroyPool.restype = RK_S32

_lib.RK_MPI_MB_GetMB.argtypes = [MB_POOL, C.c_uint64, RK_BOOL]
_lib.RK_MPI_MB_GetMB.restype = MB_BLK

_lib.RK_MPI_MB_ReleaseMB.argtypes = [MB_BLK]
_lib.RK_MPI_MB_ReleaseMB.restype = RK_S32

_lib.RK_MPI_CAL_COMM_GetPicBufferSize.argtypes = [C.POINTER(PicBufAttrS), C.POINTER(MbPicCalS)]
_lib.RK_MPI_CAL_COMM_GetPicBufferSize.restype = RK_S32

_lib.RK_MPI_VENC_CreateChn.argtypes = [VENC_CHN, C.POINTER(VencChnAttrS)]
_lib.RK_MPI_VENC_CreateChn.restype = RK_S32

_lib.RK_MPI_VENC_DestroyChn.argtypes = [VENC_CHN]
_lib.RK_MPI_VENC_DestroyChn.restype = RK_S32

_lib.RK_MPI_VENC_StartRecvFrame.argtypes = [VENC_CHN, C.POINTER(VencRecvPicParamS)]
_lib.RK_MPI_VENC_StartRecvFrame.restype = RK_S32

_lib.RK_MPI_VENC_SetChnParam.argtypes = [VENC_CHN, C.POINTER(VencChnParamS)]
_lib.RK_MPI_VENC_SetChnParam.restype = RK_S32

_lib.RK_MPI_VENC_StopRecvFrame.argtypes = [VENC_CHN]
_lib.RK_MPI_VENC_StopRecvFrame.restype = RK_S32

_lib.RK_MPI_VENC_SendFrame.argtypes = [VENC_CHN, C.POINTER(VideoFrameInfoS), RK_S32]
_lib.RK_MPI_VENC_SendFrame.restype = RK_S32

_lib.RK_MPI_VENC_GetStream.argtypes = [VENC_CHN, C.POINTER(VencStreamS), RK_S32]
_lib.RK_MPI_VENC_GetStream.restype = RK_S32

_lib.RK_MPI_VENC_ReleaseStream.argtypes = [VENC_CHN, C.POINTER(VencStreamS)]
_lib.RK_MPI_VENC_ReleaseStream.restype = RK_S32


class RkVencError(RuntimeError):
    pass


def _check(ret, what):
    if ret != 0:
        raise RkVencError(f"{what} failed: {ret} (0x{ret & 0xffffffff:x})")


def _align16(n):
    return (n + 15) & ~15


_sys_refcount = 0  # RK_MPI_SYS_Init/_Exit are process-wide, not per-channel


def _sys_init():
    global _sys_refcount
    if _sys_refcount == 0:
        _check(_lib.RK_MPI_SYS_Init(), "RK_MPI_SYS_Init")
    _sys_refcount += 1


def _sys_exit():
    global _sys_refcount
    _sys_refcount -= 1
    if _sys_refcount == 0:
        _lib.RK_MPI_SYS_Exit()


class RkH264Encoder:
    """One hardware H.264 encoder channel, set up once and reused across
    encode() calls -- see module docstring for why (persistent channel vs.
    the ~2s-per-invocation CLI tool). Input must be NV12 (RK_FMT_YUV420SP),
    width x height exactly (padding to the 16-aligned stride the hardware
    actually wants happens inside encode(), callers don't need to think
    about it)."""

    _next_chn = 0  # simple incrementing channel id, one per instance

    def __init__(self, width, height, bitrate_kbps=1024, gop=60, frame_rate=None):
        if frame_rate is None:
            frame_rate = round(1000 / 300)  # matches kVideoLocalFrameIntervalMs's ~3.3fps default
        _sys_init()

        self.chn = RkH264Encoder._next_chn
        RkH264Encoder._next_chn += 1
        self.width = width
        self.height = height
        self.vir_width = _align16(width)
        self.vir_height = _align16(height)
        self.y_size = self.vir_width * self.vir_height
        self.frame_size = self.y_size + self.y_size // 2  # NV12: Y + interleaved UV at half res

        attr = VencChnAttrS()
        attr.stVencAttr.enType = RK_VIDEO_ID_AVC
        attr.stVencAttr.u32MaxPicWidth = width
        attr.stVencAttr.u32MaxPicHeight = height
        attr.stVencAttr.enPixelFormat = RK_FMT_YUV420SP
        attr.stVencAttr.enMirror = 0
        # 0 = let the library auto-size the output stream buffer -- matches
        # rk_mpi_venc_test's own default (confirmed via its printed param
        # dump: "out stream size : 0"). Setting this to the *input* frame
        # size (an earlier version of this code did) was almost certainly
        # wrong -- the encoded output is normally much smaller than the raw
        # input, and real hardware testing showed the channel accepting
        # frames (SendFrame returns 0) but never producing output
        # (GetStream stuck returning RK_ERR_VENC_BUF_EMPTY indefinitely)
        # with that value set.
        attr.stVencAttr.u32BufSize = 0
        attr.stVencAttr.u32Profile = 100  # H264E_PROFILE_HIGH
        # Left at 0 (RK_FALSE) -- matches the real reference source
        # (test_mpi_venc.cpp, smart_door_venc.c), neither of which sets
        # this field at all (both memset the whole attr struct to 0 and
        # never touch bByFrame specifically). An earlier version of this
        # binding explicitly set it to 1 on the assumption "get one stream
        # per frame, not per NAL" -- turned out to be an unproven guess,
        # not something either working reference actually does.
        attr.stVencAttr.bByFrame = 0
        attr.stVencAttr.u32PicWidth = width
        attr.stVencAttr.u32PicHeight = height
        attr.stVencAttr.u32VirWidth = self.vir_width
        attr.stVencAttr.u32VirHeight = self.vir_height
        attr.stVencAttr.u32StreamBufCnt = 8

        attr.stRcAttr.enRcMode = VENC_RC_MODE_H264CBR
        cbr = attr.stRcAttr.u.stH264Cbr
        cbr.u32Gop = gop
        cbr.u32SrcFrameRateNum = frame_rate
        cbr.u32SrcFrameRateDen = 1
        cbr.fr32DstFrameRateNum = frame_rate
        cbr.fr32DstFrameRateDen = 1
        cbr.u32BitRate = bitrate_kbps
        cbr.u32StatTime = 3

        attr.stGopAttr.enGopMode = VENC_GOPMODE_NORMALP

        _check(_lib.RK_MPI_VENC_CreateChn(self.chn, C.byref(attr)), "RK_MPI_VENC_CreateChn")
        self._chn_created = True

        # See VencChnParamS's u32PollWakeUpFrmCnt comment -- this call
        # (skipped entirely in an earlier version of this binding) is very
        # likely why GetStream used to succeed (ret=0) but report zero
        # packs indefinitely for a single sent frame.
        chn_param = VencChnParamS()
        chn_param.u32PollWakeUpFrmCnt = 1
        _check(_lib.RK_MPI_VENC_SetChnParam(self.chn, C.byref(chn_param)), "RK_MPI_VENC_SetChnParam")

        recv = VencRecvPicParamS(s32RecvPicNum=-1)
        _check(_lib.RK_MPI_VENC_StartRecvFrame(self.chn, C.byref(recv)), "RK_MPI_VENC_StartRecvFrame")
        self._recv_started = True

        # Input buffers come from a proper MB_POOL, not a raw
        # RK_MPI_SYS_MmzAlloc -- confirmed against the real reference
        # source (test_mpi_venc.cpp, the actual source behind the vendor's
        # rk_mpi_venc_test CLI tool this project verified working) that
        # this is required, not optional: an earlier version of this
        # binding used plain MmzAlloc for a persistent input buffer, which
        # let SendFrame return success (0) but GetStream then blocked
        # forever returning RK_ERR_VENC_BUF_EMPTY -- the hardware pipeline
        # apparently never actually picks up a raw-MmzAlloc'd buffer as
        # real input. u32MBCnt=1 (not one-per-encode()-call) matches the
        # reference too: RK_MPI_MB_GetMB() blocks until the *previous*
        # buffer is released internally by the pipeline once the hardware
        # is done with it, so a single-slot pool self-paces encode() calls
        # to the hardware's real throughput instead of queuing unboundedly.
        pic_attr = PicBufAttrS(u32Width=width, u32Height=height, enPixelFormat=RK_FMT_YUV420SP,
                                enCompMode=COMPRESS_MODE_NONE)
        pic_cal = MbPicCalS()
        _check(_lib.RK_MPI_CAL_COMM_GetPicBufferSize(C.byref(pic_attr), C.byref(pic_cal)),
               "RK_MPI_CAL_COMM_GetPicBufferSize")
        self.buffer_size = pic_cal.u32MBSize

        pool_cfg = MbPoolConfigS(u64MBSize=self.buffer_size, u32MBCnt=1, enAllocType=MB_ALLOC_TYPE_DMA,
                                  bPreAlloc=1)
        self._pool = _lib.RK_MPI_MB_CreatePool(C.byref(pool_cfg))
        if self._pool == MB_INVALID_POOLID:
            raise RkVencError("RK_MPI_MB_CreatePool failed")

        self._pts = 0

    def encode(self, nv12_bytes: bytes) -> bytes:
        """Encodes one NV12(width x height) frame, returns the raw H.264
        bytes for it (one or more NAL units concatenated -- SPS/PPS ride
        along on the first frame, an IDR slice, then P-slices after).
        Blocks up to ~1s waiting for the hardware; matches this project's
        existing per-frame cadence (~300ms) with real margin."""
        expected = self.width * self.height + (self.width * self.height) // 2
        if len(nv12_bytes) != expected:
            raise RkVencError(f"expected {expected} bytes (NV12 {self.width}x{self.height}), got {len(nv12_bytes)}")

        # Fresh buffer from the pool each call (blocks until the hardware
        # has released the previous one -- see __init__'s comment on why
        # this must come from a pool, not a reused raw MmzAlloc buffer).
        blk = _lib.RK_MPI_MB_GetMB(self._pool, self.buffer_size, 1)
        if not blk:
            raise RkVencError("RK_MPI_MB_GetMB failed")
        vir_addr = _lib.RK_MPI_MB_Handle2VirAddr(blk)
        if not vir_addr:
            raise RkVencError("RK_MPI_MB_Handle2VirAddr failed")

        self._copy_with_stride(nv12_bytes, vir_addr)
        # Required before the hardware can see CPU-written pixel data --
        # confirmed against the reference source, which flushes right
        # before every SendFrame.
        _lib.RK_MPI_SYS_MmzFlushCache(blk, 0)

        frame = VideoFrameInfoS()
        vf = frame.stVFrame
        vf.pMbBlk = blk
        vf.u32Width = self.width
        vf.u32Height = self.height
        vf.u32VirWidth = self.vir_width
        vf.u32VirHeight = self.vir_height
        vf.enField = VIDEO_FIELD_FRAME
        vf.enPixelFormat = RK_FMT_YUV420SP
        vf.enVideoFormat = VIDEO_FORMAT_LINEAR
        vf.enCompressMode = COMPRESS_MODE_NONE
        vf.enDynamicRange = DYNAMIC_RANGE_SDR8
        vf.enColorGamut = COLOR_GAMUT_BT601
        vf.pVirAddr[0] = vir_addr
        vf.pVirAddr[1] = vir_addr + self.y_size
        vf.u32TimeRef = self._pts
        vf.u64PTS = self._pts
        self._pts += 1

        # -1, not a millisecond count -- matches the reference source
        # exactly (both SendFrame and GetStream there use -1, meaning
        # "block until done"). An earlier version of this code used a
        # positive millisecond timeout for both and never got a single
        # real encoded frame back (GetStream returned instantly, every
        # time, with RK_ERR_VENC_BUF_EMPTY) -- -1 appears to select an
        # entirely different (working) code path, not just a longer wait.
        _check(_lib.RK_MPI_VENC_SendFrame(self.chn, C.byref(frame), -1), "RK_MPI_VENC_SendFrame")

        stream = VencStreamS()
        pack_array = (VencPackS * 8)()
        stream.pstPack = C.cast(pack_array, C.POINTER(VencPackS))
        _check(_lib.RK_MPI_VENC_GetStream(self.chn, C.byref(stream), -1), "RK_MPI_VENC_GetStream")
        try:
            out = bytearray()
            packs = C.cast(stream.pstPack, C.POINTER(VencPackS * stream.u32PackCount)).contents
            for pack in packs:
                vir = _lib.RK_MPI_MB_Handle2VirAddr(pack.pMbBlk)
                if not vir:
                    continue
                buf = (C.c_uint8 * pack.u32Len).from_address(vir + pack.u32Offset)
                out += bytes(buf)
            return bytes(out)
        finally:
            _lib.RK_MPI_VENC_ReleaseStream(self.chn, C.byref(stream))

    def _copy_with_stride(self, nv12_bytes: bytes, dst: int):
        """Copies a tightly-packed width x height NV12 buffer into the
        vir_width x vir_height-strided buffer at address `dst` (see
        VencAttrS's u32VirWidth/u32VirHeight comment in the real header:
        stride must be 16-aligned) -- a single memmove when width/height
        are already 16-aligned (the common case for this project's
        DST_W/DST_H=600/400), row-by-row otherwise."""
        w, h = self.width, self.height
        if self.vir_width == w and self.vir_height == h:
            C.memmove(dst, nv12_bytes, len(nv12_bytes))
            return

        y_src = nv12_bytes[:w * h]
        uv_src = nv12_bytes[w * h:]
        for row in range(h):
            C.memmove(dst + row * self.vir_width, y_src[row * w:(row + 1) * w], w)
        uv_dst_off = self.y_size
        uv_h = h // 2
        uv_w = w  # interleaved U/V at half vertical res, full horizontal byte count
        for row in range(uv_h):
            C.memmove(dst + uv_dst_off + row * self.vir_width, uv_src[row * uv_w:(row + 1) * uv_w], uv_w)

    def close(self):
        if getattr(self, "_recv_started", False):
            _lib.RK_MPI_VENC_StopRecvFrame(self.chn)
            self._recv_started = False
        if getattr(self, "_chn_created", False):
            _lib.RK_MPI_VENC_DestroyChn(self.chn)
            self._chn_created = False
        if getattr(self, "_pool", None) not in (None, MB_INVALID_POOLID):
            _lib.RK_MPI_MB_DestroyPool(self._pool)
            self._pool = None
        _sys_exit()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

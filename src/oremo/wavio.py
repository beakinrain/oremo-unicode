"""RIFF/WAVE reading and writing.

Samples are handled internally as float64 in *16-bit scale* (i.e. a full
scale sine has amplitude 32768) whatever the file format is, which is the
scale Snack used for Lin16 sounds and the scale all of OREMO's thresholds
(waveScale=32768, power in dB, ...) were designed for.
"""

import struct

import numpy as np

# encodings (names follow Snack): Lin8 (unsigned), Lin16, Lin24, Lin32, Float
ENC_BITS = {"Lin8": 8, "Lin16": 16, "Lin24": 24, "Lin32": 32, "Float": 32, "Float64": 64}

WAVE_FORMAT_PCM = 1
WAVE_FORMAT_IEEE_FLOAT = 3
WAVE_FORMAT_EXTENSIBLE = 0xFFFE


class WavError(Exception):
    pass


def read_wav(path):
    """Return (data[n, ch] float64 16-bit scale, rate, encoding)."""
    with open(path, "rb") as fp:
        raw = fp.read()
    if len(raw) < 12 or raw[0:4] not in (b"RIFF", b"RIFX") or raw[8:12] != b"WAVE":
        raise WavError("not a RIFF/WAVE file: %s" % path)
    big = raw[0:4] == b"RIFX"
    e = ">" if big else "<"
    pos = 12
    fmt = None
    data = None
    while pos + 8 <= len(raw):
        cid = raw[pos:pos + 4]
        size = struct.unpack(e + "I", raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = body
        elif cid == b"data":
            data = body
            if fmt is not None:
                # some writers put a bogus size (0 / 0xFFFFFFFF) in streamed files
                if size == 0 or pos + 8 + size > len(raw):
                    data = raw[pos + 8:]
                break
        pos += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise WavError("broken wav file (no fmt/data chunk): %s" % path)
    tag, ch, rate, _brate, align, bits = struct.unpack(e + "HHIIHH", fmt[:16])
    if tag == WAVE_FORMAT_EXTENSIBLE and len(fmt) >= 26:
        tag = struct.unpack(e + "H", fmt[24:26])[0]
    if ch <= 0:
        raise WavError("invalid channel count")
    bps = max(1, align // ch) if align else (bits + 7) // 8
    nframes = len(data) // (bps * ch)
    data = data[:nframes * bps * ch]
    if tag == WAVE_FORMAT_IEEE_FLOAT:
        if bps == 4:
            a = np.frombuffer(data, dtype=e + "f4").astype(np.float64) * 32768.0
            enc = "Float"
        elif bps == 8:
            a = np.frombuffer(data, dtype=e + "f8") * 32768.0
            enc = "Float64"
        else:
            raise WavError("unsupported float width %d" % bps)
    elif tag == WAVE_FORMAT_PCM:
        if bps == 1:
            a = (np.frombuffer(data, dtype=np.uint8).astype(np.float64) - 128.0) * 256.0
            enc = "Lin8"
        elif bps == 2:
            a = np.frombuffer(data, dtype=e + "i2").astype(np.float64)
            enc = "Lin16"
        elif bps == 3:
            b = np.frombuffer(data, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
            if big:
                v = (b[:, 0] << 16) | (b[:, 1] << 8) | b[:, 2]
            else:
                v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            v = np.where(v >= 0x800000, v - 0x1000000, v)
            a = v.astype(np.float64) / 256.0
            enc = "Lin24"
        elif bps == 4:
            a = np.frombuffer(data, dtype=e + "i4").astype(np.float64) / 65536.0
            enc = "Lin32"
        else:
            raise WavError("unsupported PCM width %d" % bps)
    else:
        raise WavError("unsupported wav format tag %d" % tag)
    a = a.reshape(-1, ch)
    return a, int(rate), enc


def _to_bytes(a, enc):
    if enc == "Lin16":
        return np.clip(np.round(a), -32768, 32767).astype("<i2").tobytes(), WAVE_FORMAT_PCM, 16
    if enc == "Lin8":
        v = np.clip(np.round(a / 256.0 + 128.0), 0, 255).astype(np.uint8)
        return v.tobytes(), WAVE_FORMAT_PCM, 8
    if enc == "Lin24":
        v = np.clip(np.round(a * 256.0), -8388608, 8388607).astype(np.int32)
        b = np.empty((v.size, 3), dtype=np.uint8)
        u = v.reshape(-1).astype(np.uint32)
        b[:, 0] = u & 0xFF
        b[:, 1] = (u >> 8) & 0xFF
        b[:, 2] = (u >> 16) & 0xFF
        return b.tobytes(), WAVE_FORMAT_PCM, 24
    if enc == "Lin32":
        v = np.clip(np.round(a * 65536.0), -2147483648, 2147483647).astype("<i4")
        return v.tobytes(), WAVE_FORMAT_PCM, 32
    if enc == "Float64":
        return (a / 32768.0).astype("<f8").tobytes(), WAVE_FORMAT_IEEE_FLOAT, 64
    # Float
    return (a / 32768.0).astype("<f4").tobytes(), WAVE_FORMAT_IEEE_FLOAT, 32


def write_wav(path, a, rate, enc="Lin16"):
    """Write data[n, ch] (16-bit scale float) as a RIFF/WAVE file."""
    a = np.asarray(a, dtype=np.float64)
    if a.ndim == 1:
        a = a.reshape(-1, 1)
    ch = a.shape[1]
    body, tag, bits = _to_bytes(a, enc)
    bps = bits // 8
    align = bps * ch
    if tag == WAVE_FORMAT_PCM and (bits > 16 or ch > 2):
        # WAVE_FORMAT_EXTENSIBLE is recommended for >16 bit or >2 ch
        sub = b"\x01\x00\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"
        mask = 0x4 if ch == 1 else (0x3 if ch == 2 else 0)
        fmt = struct.pack("<HHIIHHHHI", WAVE_FORMAT_EXTENSIBLE, ch, rate, rate * align,
                          align, bits, 22, bits, mask) + sub
    elif tag == WAVE_FORMAT_IEEE_FLOAT:
        fmt = struct.pack("<HHIIHHH", tag, ch, rate, rate * align, align, bits, 0)
    else:
        fmt = struct.pack("<HHIIHH", tag, ch, rate, rate * align, align, bits)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    if tag == WAVE_FORMAT_IEEE_FLOAT:
        chunks += b"fact" + struct.pack("<II", 4, a.shape[0])
    chunks += b"data" + struct.pack("<I", len(body)) + body
    if len(body) & 1:
        chunks += b"\x00"
    with open(path, "wb") as fp:
        fp.write(b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks)

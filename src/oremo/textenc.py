"""Text encoding detection / conversion and filename mojibake repair.

The original OREMO read and wrote every text file (reclist, typelist, comment
file, guide-BGM setting file, ust, oto.ini ...) with the *system* code page.
Files made on Japanese Windows are Shift_JIS, so on Simplified-Chinese Windows
(code page 936 / GBK) they were decoded as GBK and turned into mojibake, and the
wav files recorded from such a list got mojibake file names.

This module provides:
  * detect()/decode_bytes()/read_text(): robust auto detection
    (BOM, UTF-8, UTF-16 w/o BOM, Shift_JIS vs GBK vs Big5 heuristics)
  * write_text(): write with a chosen encoding and optional fallback when a
    character cannot be represented (e.g. simplified hanzi in Shift_JIS)
  * repair_mojibake(): recover names that were decoded with the wrong code page
"""

import codecs
import locale
import os
import re
import sys

# --------------------------------------------------------------------------
# Encoding names

AUTO = "auto"
SYSTEM = "system"

# (internal name, display name). Internal names are Python codec names except
# AUTO/SYSTEM and 'utf-8-sig' which means UTF-8 with BOM.
ENCODINGS = [
    ("cp932", "Shift_JIS (CP932)"),
    ("gbk", "GBK (CP936)"),
    ("gb18030", "GB18030"),
    ("big5", "Big5 (CP950)"),
    ("euc_jp", "EUC-JP"),
    ("utf-8", "UTF-8"),
    ("utf-8-sig", "UTF-8 (BOM)"),
    ("utf-16", "UTF-16 (BOM)"),
    ("cp949", "EUC-KR (CP949)"),
    ("cp1252", "Western (CP1252)"),
]

ENCODING_LABELS = dict(ENCODINGS)


def system_encoding():
    """ANSI code page of the running Windows (what Tcl used as 'system')."""
    if sys.platform == "win32":
        try:
            import ctypes
            return "cp%d" % ctypes.windll.kernel32.GetACP()
        except Exception:
            pass
    return locale.getpreferredencoding(False) or "utf-8"


def normalize(enc):
    """Resolve SYSTEM and aliases to a Python codec name."""
    if not enc or enc == AUTO:
        return None
    if enc == SYSTEM:
        return system_encoding()
    try:
        return codecs.lookup(enc).name if enc not in ("utf-8-sig",) else enc
    except LookupError:
        return None


def label(enc):
    if enc == AUTO:
        return "Auto"
    if enc == SYSTEM:
        return "System (%s)" % system_encoding()
    return ENCODING_LABELS.get(enc, enc)


# --------------------------------------------------------------------------
# Scoring helpers

_HIRA = re.compile(r"[ぁ-ゟ]")
_KATA = re.compile(r"[゠-ヿ]")
_HWKANA = re.compile(r"[｡-ﾟ]")
_CJK = re.compile(r"[一-鿿]")
_PUA = re.compile(r"[-]")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BOX = re.compile(r"[─-╿]")


def _in_gb2312(ch):
    try:
        ch.encode("gb2312")
        return True
    except UnicodeEncodeError:
        return False


def _jis_level(ch):
    """1 = JIS level-1 kanji, 2 = level-2, 3 = vendor extension, 0 = not kanji."""
    try:
        b = ch.encode("cp932")
    except UnicodeEncodeError:
        return 0
    if len(b) != 2:
        return 0
    code = (b[0] << 8) | b[1]
    if 0x889F <= code <= 0x9872:
        return 1
    if 0x989F <= code <= 0xEAA4:
        return 2
    return 3


def text_score(text, enc):
    """How natural does *text* look if it was decoded with *enc*?

    Higher is better.  Only relative values matter.
    """
    s = 0.0
    n = 0
    for ch in text:
        o = ord(ch)
        if o < 0x80:
            if _CTRL.match(ch):
                s -= 5
            continue
        n += 1
        if _HIRA.match(ch):
            s += 3
        elif _KATA.match(ch):
            s += 2
        elif _HWKANA.match(ch):
            s -= 3
        elif _PUA.match(ch):
            s -= 6
        elif _BOX.match(ch):
            s -= 1
        elif _CJK.match(ch):
            if enc in ("cp932", "shift_jis", "euc_jp"):
                lv = _jis_level(ch)
                s += {1: 1.5, 2: -0.3, 3: -2.0}.get(lv, 0.0)
            elif enc in ("gbk", "gb18030", "gb2312"):
                s += 1.5 if _in_gb2312(ch) else -1.5
            elif enc in ("big5", "cp950"):
                s += 0.8
            else:
                s += 0.5
        elif 0x3000 <= o <= 0x303f or 0xff01 <= o <= 0xff5e:
            s += 0.5  # CJK punctuation / full-width forms
        elif o == 0xfffd:
            s -= 10
        elif 0x80 <= o < 0x100:
            s -= 0.5  # latin-1 soup is a classic mojibake symptom
        else:
            s -= 0.2
    return s


# --------------------------------------------------------------------------
# Detection

_CANDIDATES = ("cp932", "gbk", "big5")


def detect(data):
    """Return the most probable encoding name for *data* (bytes).

    Returned values: 'utf-8-sig', 'utf-16', 'utf-8', 'ascii', or one of the
    code pages in _CANDIDATES.
    """
    if data.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"
    # UTF-16 without BOM: lots of zero bytes in alternating positions
    if len(data) >= 4:
        sample = data[:4000]
        z_even = sample[0::2].count(0)
        z_odd = sample[1::2].count(0)
        half = max(1, len(sample) // 2)
        if z_odd > half * 0.3 and z_even < half * 0.05:
            return "utf-16-le"
        if z_even > half * 0.3 and z_odd < half * 0.05:
            return "utf-16-be"
    try:
        data.decode("ascii")
        return "ascii"
    except UnicodeDecodeError:
        pass
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    best, best_score = None, None
    for enc in _CANDIDATES:
        try:
            txt = data.decode(enc)
        except UnicodeDecodeError:
            continue
        sc = text_score(txt, enc)
        if best_score is None or sc > best_score:
            best, best_score = enc, sc
    if best is None:
        # nothing decodes strictly: fall back to the system code page
        best = system_encoding()
    return best


def decode_bytes(data, enc=AUTO):
    """Decode *data*. Returns (text, used_encoding)."""
    real = normalize(enc)
    if real is None:
        real = detect(data)
    if real == "ascii":
        real_dec = "utf-8"
    else:
        real_dec = real
    try:
        text = data.decode(real_dec)
    except UnicodeDecodeError:
        text = data.decode(real_dec, errors="replace")
    if text.startswith("﻿"):
        text = text[1:]
    return text, real


def read_text(path, enc=AUTO):
    """Read a text file. Returns (text, used_encoding). Raises OSError."""
    with open(path, "rb") as fp:
        data = fp.read()
    return decode_bytes(data, enc)


def can_encode(text, enc):
    try:
        text.encode(normalize(enc) or "utf-8")
        return True
    except UnicodeEncodeError:
        return False


def encode_text(text, enc, fallback="utf-8-sig"):
    """Encode text. Returns (bytes, used_encoding).

    If *enc* cannot represent every character and *fallback* is given the
    text is encoded with *fallback* instead.
    """
    real = normalize(enc) or "utf-8"
    if real == "ascii":
        real = "utf-8"
    try:
        return text.encode(real), real
    except UnicodeEncodeError:
        if fallback:
            fb = normalize(fallback) or "utf-8"
            return text.encode(fb), fb
        return text.encode(real, errors="replace"), real


def write_text(path, text, enc, fallback="utf-8-sig", newline="\r\n"):
    """Write text file. Returns the encoding actually used."""
    if newline is not None:
        text = text.replace("\r\n", "\n").replace("\n", newline)
    data, used = encode_text(text, enc, fallback)
    with open(path, "wb") as fp:
        fp.write(data)
    return used


def is_utf8_family(enc):
    return (enc or "").replace("_", "-").lower().startswith("utf-8")


# --------------------------------------------------------------------------
# Mojibake repair (file names and short strings)

# (wrongly used decoder, real encoding)
REPAIR_PAIRS = [
    ("gbk", "cp932"),      # Shift_JIS name shown on Chinese Windows (zip, OREMO)
    ("cp932", "gbk"),      # GBK name shown on Japanese Windows
    ("cp437", "cp932"),    # zip without UTF-8 flag, extracted by cp437 tools
    ("cp437", "gbk"),
    ("cp437", "utf-8"),
    ("cp1252", "cp932"),
    ("cp1252", "gbk"),
    ("cp1252", "utf-8"),
    ("latin-1", "cp932"),
    ("latin-1", "gbk"),
    ("latin-1", "utf-8"),
    ("gbk", "utf-8"),      # UTF-8 bytes shown as GBK
    ("cp932", "utf-8"),    # UTF-8 bytes shown as Shift_JIS
    ("big5", "cp932"),
    ("cp932", "big5"),
    ("big5", "gbk"),
    ("gbk", "big5"),
]


def transcode(text, wrong, real):
    """text.encode(wrong).decode(real) or None if impossible."""
    try:
        return text.encode(wrong).decode(real)
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None


def repair_candidates(text):
    """Return list of (score_gain, repaired, wrong, real) sorted best first."""
    base = text_score(text, "")
    out = []
    seen = set()
    for wrong, real in REPAIR_PAIRS:
        fixed = transcode(text, wrong, real)
        if fixed is None or fixed == text or fixed in seen:
            continue
        seen.add(fixed)
        gain = text_score(fixed, real) - base
        out.append((gain, fixed, wrong, real))
    out.sort(key=lambda x: -x[0])
    return out


def repair_mojibake(text, wrong=AUTO, real=AUTO, min_gain=1.0):
    """Try to recover *text*.

    With explicit wrong/real encodings the transformation is applied
    directly.  In AUTO mode the best scoring candidate is returned when it
    improves the naturalness score by at least *min_gain*.
    Returns (repaired_text or None, wrong, real).
    """
    if wrong != AUTO and real != AUTO:
        fixed = transcode(text, normalize(wrong) or wrong, normalize(real) or real)
        return fixed, wrong, real
    cands = repair_candidates(text)
    if wrong != AUTO:
        cands = [c for c in cands if c[2] == normalize(wrong)]
    if real != AUTO:
        cands = [c for c in cands if c[3] == normalize(real)]
    if cands and cands[0][0] >= min_gain:
        return cands[0][1], cands[0][2], cands[0][3]
    return None, None, None


INVALID_FILENAME_CHARS = '\\/:*?"<>|'


def invalid_filename_chars(name):
    return [c for c in name if c in INVALID_FILENAME_CHARS or ord(c) < 32]


def safe_join(*parts):
    return os.path.join(*parts)

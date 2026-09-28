"""Tk drawing helpers that replace Snack's canvas items and Tcl procedures
(waveform item, spectrogram item, snack::timeAxis, snack::frequencyAxis,
snack::createIcons)."""

import math
import re
import tkinter as tk
import tkinter.font as tkfont

import numpy as np

# --------------------------------------------------------------------------
# icons

_PLAY_XBM = """
#define play_width 16
#define play_height 16
static unsigned char play_bits[] = {
0x00,0x00,0x00,0x00,0x0c,0x00,0x1c,0x00,0x3c,0x00,0x7c,0x00,0xfc,0x00,0xfc,0x01,
0xfc,0x03,0xfc,0x01,0xfc,0x00,0x7c,0x00,0x3c,0x00,0x1c,0x00,0x0c,0x00,0x00,0x00};
"""

_STOP_XBM = """
#define stop_width 16
#define stop_height 16
static unsigned char stop_bits[] = {
0x00,0x00,0x00,0x00,0x00,0x00,0xf8,0x1f,0xf8,0x1f,0xf8,0x1f,0xf8,0x1f,0xf8,0x1f,
0xf8,0x1f,0xf8,0x1f,0xf8,0x1f,0xf8,0x1f,0xf8,0x1f,0x00,0x00,0x00,0x00,0x00,0x00};
"""

_FOLDER = [
    "................",
    "................",
    "..#####.........",
    ".#yyyyy#........",
    "#yyyyyyy#######.",
    "#yyyyyyyyyyyyy#.",
    "#yyyyyyyyyyyyy#.",
    "#yy###########.#",
    "#yy#ooooooooooo#",
    "#y#ooooooooooo#.",
    "#y#ooooooooooo#.",
    "##ooooooooooo#..",
    "##ooooooooooo#..",
    "#############...",
    "................",
    "................",
]


SCALE = 1.0  # pixel scale factor for high DPI screens (set by the application)


def _scale_xbm(xbm, k, name):
    """Enlarge a 16x16 XBM by the integer factor k."""
    if k <= 1:
        return xbm
    nums = [int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", xbm)]
    rows = []
    for y in range(16):
        bits = [(nums[y * 2 + (x // 8)] >> (x % 8)) & 1 for x in range(16)]
        big = [b for b in bits for _ in range(k)]
        rows += [big] * k
    w = 16 * k
    out = []
    for row in rows:
        for byte in range(0, w, 8):
            v = 0
            for i, b in enumerate(row[byte:byte + 8]):
                v |= b << i
            out.append("0x%02x" % v)
    return "#define %s_width %d\n#define %s_height %d\nstatic unsigned char %s_bits[] = {\n%s};" % (
        name, w, name, w, name, ", ".join(out))   # Tk reads words of <= 100 chars


def create_icons(root, scale=1.0):
    k = max(1, int(round(scale)))
    icons = {}
    icons["snackPlay"] = tk.BitmapImage(master=root, data=_scale_xbm(_PLAY_XBM, k, "play"), name="snackPlay")
    icons["snackStop"] = tk.BitmapImage(master=root, data=_scale_xbm(_STOP_XBM, k, "stop"), name="snackStop")
    img = tk.PhotoImage(master=root, width=16, height=16)
    colors = {"#": "#000000", "y": "#ffff00", "o": "#c0c000"}
    for y, row in enumerate(_FOLDER):
        for x, c in enumerate(row):
            if c in colors:
                img.put(colors[c], (x, y))
    big = tk.PhotoImage(master=root, name="snackOpen")
    big.tk.call(big, "copy", img, "-zoom", k, k)
    icons["snackOpen"] = big
    return icons


# --------------------------------------------------------------------------
# axes


def _fmt_num(v):
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return s


def time_axis(canvas, ox, oy, width, height, pps, tags="snack_t_axis",
              font=("Helvetica", 8), fill="black", starttime=0.0):
    """snack::timeAxis replacement."""
    if pps <= 0 or width <= 0:
        return
    f = tkfont.Font(font=font)
    ticklist = [0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05,
                0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300, 600, 1200, 1800, 3600]
    lw = f.measure("00.00") + 8
    npt = None
    for e in ticklist:
        if e * pps >= lw:
            npt = e
            break
    if npt is None:  # nothing loaded (pps ~ 0): no readable scale
        return
    j = int(math.ceil(starttime / npt))
    while True:
        tm = j * npt
        x = ox + (tm - starttime) * pps
        if x > ox + width:
            break
        if x >= ox:
            canvas.create_line(x, oy, x, oy + 4 * SCALE, fill=fill, tags=tags)
            if x > ox + 1:
                canvas.create_text(x, oy + 3 * SCALE, text=_fmt_num(tm), anchor="n",
                                   font=font, fill=fill, tags=tags)
        j += 1


def frequency_axis(canvas, x, y, width, height, topfr=8000, tags="snack_y_axis",
                   font=("Helvetica", 8), fill="black", draw0=False):
    """snack::frequencyAxis replacement."""
    if height <= 0 or topfr <= 0:
        return
    f = tkfont.Font(font=font)
    linespace = f.metrics("linespace")
    ascent = f.metrics("ascent")
    ticklist = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]
    npt = ticklist[-1]
    dy = height
    for e in ticklist:
        npt = e
        dy = float(height * npt) / topfr
        if dy >= linespace:
            break
    hztext = "kHz" if topfr >= 1000 else "Hz"
    i = 0.0 if draw0 else dy
    j = 0 if draw0 else 1
    while i < height:
        yc = height + y - i
        t = j * npt if npt < 1000 else j * npt / 1000.0
        tstr = _fmt_num(t)
        if yc > 8 + y:
            if (yc - ascent) > (y + linespace) or f.measure(hztext) < (width - 8 * SCALE - f.measure(tstr)):
                canvas.create_text(x + width - 8 * SCALE, yc - 2, text=tstr, fill=fill, font=font,
                                   anchor="e", tags=tags)
            canvas.create_line(x + width - 5 * SCALE, yc, x + width, yc, tags=tags, fill=fill)
        i += dy
        j += 1
    canvas.create_text(x + 2, y + 1, text=hztext, font=font, anchor="nw", tags=tags, fill=fill)
    return npt


# --------------------------------------------------------------------------
# waveform item


def draw_waveform(canvas, x0, y0, mono, width, height, limit=0, fill="black", tags=("wave",)):
    """Snack's waveform canvas item: min/max per pixel column."""
    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        return
    n = len(mono)
    mid = y0 + height / 2.0
    if n == 0:
        return
    lim = float(limit) if limit and float(limit) > 0 else float(max(np.max(np.abs(mono)), 1.0))
    scale = (height / 2.0) / lim
    edges = (np.arange(width + 1) * n / float(width)).astype(np.int64)
    edges[-1] = n
    coords = []
    if n >= width:
        starts = edges[:-1]
        lens = np.maximum(edges[1:] - starts, 1)
        mx = np.maximum.reduceat(mono, starts)
        mn = np.minimum.reduceat(mono, starts)
        del lens
    else:
        idx = np.minimum((np.arange(width) * n / float(width)).astype(np.int64), n - 1)
        mx = mono[idx]
        mn = mono[idx]
    ymx = np.clip(mid - mx * scale, y0, y0 + height)
    ymn = np.clip(mid - mn * scale, y0, y0 + height)
    for i in range(width):
        xx = x0 + i
        if i & 1:
            coords.extend((xx, ymn[i], xx, ymx[i]))
        else:
            coords.extend((xx, ymx[i], xx, ymn[i] + 0.5))
    if len(coords) >= 4:
        canvas.create_line(*coords, fill=fill, tags=tags)

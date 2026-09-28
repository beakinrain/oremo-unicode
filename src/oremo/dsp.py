"""Signal processing used by OREMO (replacement for the Snack extension and
for the external SPTK based tool ``modifyPre.exe``).

All signals are float64 numpy arrays in 16-bit scale.
"""

import math

import numpy as np

# --------------------------------------------------------------------------
# windows


def make_window(kind, n):
    n = max(1, int(n))
    if n == 1:
        return np.ones(1)
    k = (kind or "Hamming").lower()
    if k.startswith("hamm"):
        return np.hamming(n)
    if k.startswith("hann"):
        return np.hanning(n)
    if k.startswith("bart"):
        return np.bartlett(n)
    if k.startswith("black"):
        return np.blackman(n)
    return np.ones(n)


def _clampf(val, lo, hi, default):
    try:
        v = float(val)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return min(max(v, lo), hi)


def sane_pitch_args(rate, frame_length, window_length, maxpitch, minpitch):
    """Clamp F0 settings to values the trackers can handle."""
    frame_length = _clampf(frame_length, 0.001, 0.5, 0.01)
    window_length = _clampf(window_length, 0.001, 0.1, 0.01)
    minpitch = _clampf(minpitch, 20.0, rate / 4.0, 60.0)
    maxpitch = _clampf(maxpitch, minpitch + 1.0, rate / 2.0 - 1.0, max(minpitch * 2, 400.0))
    return frame_length, window_length, maxpitch, minpitch


def to_mono(a):
    a = np.asarray(a, dtype=np.float64)
    if a.ndim == 1:
        return a
    if a.shape[1] == 1:
        return a[:, 0]
    return a.mean(axis=1)


def _frames(x, centers, length):
    """Extract frames of *length* centred at *centers* (zero padded)."""
    length = int(length)
    half = length // 2
    pad = np.concatenate([np.zeros(half + 1), x, np.zeros(length + 1)])
    idx = np.asarray(centers, dtype=np.int64) - half + half + 1
    idx = np.clip(idx, 0, len(pad) - length)
    view = np.lib.stride_tricks.sliding_window_view(pad, length)
    return view[idx]


# --------------------------------------------------------------------------
# power (Snack "sound power")


def power(x, rate, frame_length=0.01, window="Hanning", preemph=0.97,
          window_length=None, start=0, end=-1):
    """Short time power in dB, one value per *frame_length* seconds.

    Mirrors ``snd power -framelength fl -windowtype w -preemphasisfactor p
    -windowlength wl -start s -end e``.
    """
    x = to_mono(x)
    if end is None or end < 0 or end > len(x):
        end = len(x)
    start = max(0, int(start))
    seg = x[start:int(end)]
    if len(seg) == 0:
        return np.zeros(0)
    # guard against absurd values typed in the settings (0, negative, huge)
    frame_length = _clampf(frame_length, 0.001, 1.0, 0.01)
    preemph = _clampf(preemph, -1.0, 1.0, 0.0)
    step = max(1, int(round(frame_length * rate)))
    wl = int(window_length) if window_length and window_length > 0 else step
    wl = int(min(max(2, wl), rate))   # at most 1 second
    if preemph:
        seg = np.concatenate([[seg[0]], seg[1:] - preemph * seg[:-1]])
    n = int(len(seg) // step)
    if n <= 0:
        n = 1
    centers = np.arange(n) * step + step // 2
    fr = _frames(seg, centers, wl) * make_window(window, wl)
    ms = np.sum(fr * fr, axis=1) / wl
    return 10.0 * np.log10(np.maximum(ms, 1.0))


# --------------------------------------------------------------------------
# F0 estimation


def _lowpass_decimate(x, rate, target=11000):
    d = max(1, int(rate // target))
    if d == 1:
        return x.copy(), rate, 1
    taps = 8 * d + 1
    n = np.arange(taps) - (taps - 1) / 2.0
    cutoff = 0.9 / d / 2.0  # normalized to fs
    h = np.sinc(2 * cutoff * n) * np.blackman(taps)
    h /= h.sum()
    y = np.convolve(x, h, mode="same")[::d]
    return y, rate / d, d


def _nccf(frames_ext, n, lags):
    """frames_ext: (F, n+maxlag). Returns NCCF (F, len(lags))."""
    ref = frames_ext[:, :n]
    e0 = np.sum(ref * ref, axis=1)
    csum = np.concatenate([np.zeros((frames_ext.shape[0], 1)),
                           np.cumsum(frames_ext * frames_ext, axis=1)], axis=1)
    out = np.empty((frames_ext.shape[0], len(lags)))
    for i, k in enumerate(lags):
        seg = frames_ext[:, k:k + n]
        num = np.sum(ref * seg, axis=1)
        ek = csum[:, k + n] - csum[:, k]
        out[:, i] = num / np.sqrt(e0 * ek + 1e-9)
    return out


def pitch_esps(x, rate, frame_length=0.01, window_length=0.0075,
               maxpitch=400.0, minpitch=60.0, progress=None):
    """RAPT style F0 tracker (normalised cross correlation + dynamic
    programming), the algorithm behind Snack's ``-method ESPS``.

    Returns an array of F0 values [Hz] (0 = unvoiced), one per frame.
    """
    x = to_mono(x)
    if len(x) < 16 or maxpitch <= minpitch or minpitch <= 0:
        return np.zeros(0)
    step = max(1, int(round(frame_length * rate)))
    nfr = int(len(x) // step)
    if nfr <= 0:
        return np.zeros(0)
    window_length = max(float(window_length), 0.0075)
    xd, rd, dec = _lowpass_decimate(x, rate)
    n_d = max(8, int(round(window_length * rd)))
    kmin_d = max(2, int(math.floor(rd / maxpitch)) - 1)
    kmax_d = int(math.ceil(rd / minpitch)) + 1
    lags_d = np.arange(kmin_d, kmax_d + 1)
    centers_d = (np.arange(nfr) * step + step // 2) / dec
    L = n_d + kmax_d + 1
    starts = (centers_d - n_d / 2.0).astype(np.int64)
    pad = np.concatenate([np.zeros(L), xd, np.zeros(2 * L)])
    view = np.lib.stride_tricks.sliding_window_view(pad, L)
    fr = view[np.clip(starts + L, 0, len(pad) - L)]
    fr = fr - fr[:, :n_d].mean(axis=1, keepdims=True)
    coarse = _nccf(fr, n_d, lags_d)

    # frame energy (full rate)
    n_full = max(8, int(round(window_length * rate)))
    rms_fr = _frames(x, np.arange(nfr) * step + step // 2, n_full)
    rms = np.sqrt(np.mean(rms_fr * rms_fr, axis=1)) + 1e-3

    # candidate extraction + refinement at full rate
    n_f = n_full
    kmin_f = max(2, int(math.floor(rate / maxpitch)))
    kmax_f = int(math.ceil(rate / minpitch))
    Lf = n_f + kmax_f + dec + 2
    padf = np.concatenate([np.zeros(Lf), x, np.zeros(2 * Lf)])
    starts_f = (np.arange(nfr) * step + step // 2 - n_f // 2).astype(np.int64) + Lf
    max_cands = 8
    cand_f = np.zeros((nfr, max_cands))
    cand_c = np.zeros((nfr, max_cands))
    cand_n = np.zeros(nfr, dtype=np.int64)
    maxc = np.zeros(nfr)
    for i in range(nfr):
        c = coarse[i]
        if len(c) < 3:
            continue
        peaks = np.where((c[1:-1] > c[:-2]) & (c[1:-1] >= c[2:]))[0] + 1
        if len(peaks) == 0:
            continue
        pk = c[peaks]
        thr = max(0.3 * pk.max(), 0.25)
        sel = peaks[pk >= thr]
        sel = sel[np.argsort(-c[sel])][:max_cands]
        if len(sel) == 0:
            continue
        seg0 = padf[starts_f[i]:starts_f[i] + n_f]
        seg0 = seg0 - seg0.mean()
        e0 = np.dot(seg0, seg0) + 1e-9
        j = 0
        for p in sel:
            center = int(round(lags_d[p] * dec))
            best_k, best_v, vals = None, -2.0, {}
            for k in range(max(kmin_f, center - dec - 1), min(kmax_f, center + dec + 1) + 1):
                segk = padf[starts_f[i] + k:starts_f[i] + k + n_f]
                segk = segk - segk.mean()
                v = np.dot(seg0, segk) / math.sqrt(e0 * (np.dot(segk, segk) + 1e-9))
                vals[k] = v
                if v > best_v:
                    best_v, best_k = v, k
            if best_k is None:
                continue
            # parabolic interpolation
            kk = float(best_k)
            if best_k - 1 in vals and best_k + 1 in vals:
                a, b, cc = vals[best_k - 1], best_v, vals[best_k + 1]
                den = a - 2 * b + cc
                if den < 0:
                    kk = best_k + 0.5 * (a - cc) / den
            f = rate / kk
            if f < minpitch or f > maxpitch:
                continue
            cand_f[i, j] = f
            cand_c[i, j] = best_v
            j += 1
        cand_n[i] = j
        if j:
            maxc[i] = cand_c[i, :j].max()
        if progress and i % 50 == 0:
            progress("", i / float(nfr))

    # dynamic programming (RAPT cost structure)
    lag_wt = 0.3
    freq_wt = 0.02 / max(frame_length, 1e-4) * 0.01 * 100.0 * 0.1
    trans_cost = 0.005
    trans_amp = 0.5
    double_cost = 0.35
    vo_bias = 0.0
    silence = 30.0  # rms threshold (16bit scale) below which frames are unvoiced
    INF = 1e30
    ns = max_cands + 1  # state 0 = unvoiced
    prev_cost = np.full(ns, INF)
    back = np.zeros((nfr, ns), dtype=np.int64)
    cost_hist = []
    for i in range(nfr):
        local = np.full(ns, INF)
        local[0] = vo_bias + maxc[i]
        nc = cand_n[i]
        if rms[i] >= silence:
            for j in range(nc):
                lag_norm = (rate / cand_f[i, j]) / kmax_f
                local[j + 1] = 1.0 - cand_c[i, j] * (1.0 - lag_wt * lag_norm)
        if i == 0:
            cur = local.copy()
            back[i] = 0
        else:
            cur = np.full(ns, INF)
            r = rms[i] / rms[i - 1]
            r = min(max(r, 0.05), 20.0)
            pn = cand_n[i - 1]
            for s in range(ns):
                if local[s] >= INF:
                    continue
                best, arg = INF, 0
                for q in range(ns):
                    if prev_cost[q] >= INF:
                        continue
                    if s == 0 and q == 0:
                        t = 0.0
                    elif s == 0:          # voiced -> unvoiced
                        t = trans_cost + trans_amp * min(r, 2.0)
                    elif q == 0:          # unvoiced -> voiced
                        t = trans_cost + trans_amp * min(1.0 / r, 2.0)
                    else:
                        if q - 1 >= pn:
                            continue
                        lr = abs(math.log(cand_f[i, s - 1] / cand_f[i - 1, q - 1]))
                        lr2 = double_cost + abs(lr - math.log(2.0))
                        t = freq_wt * min(lr, lr2)
                    v = prev_cost[q] + t
                    if v < best:
                        best, arg = v, q
                cur[s] = best + local[s]
                back[i, s] = arg
        prev_cost = cur
        cost_hist.append(None)
    # backtrack
    f0 = np.zeros(nfr)
    s = int(np.argmin(prev_cost))
    for i in range(nfr - 1, -1, -1):
        if s > 0 and s - 1 < cand_n[i]:
            f0[i] = cand_f[i, s - 1]
        s = int(back[i, s]) if i > 0 else 0
    # remove isolated voiced frames
    for i in range(nfr):
        if f0[i] > 0:
            l = f0[i - 1] if i > 0 else 0
            r_ = f0[i + 1] if i + 1 < nfr else 0
            if l == 0 and r_ == 0:
                f0[i] = 0
    if progress:
        progress("", 1.0)
    return f0


def pitch_amdf(x, rate, frame_length=0.01, window_length=0.01,
               maxpitch=400.0, minpitch=60.0, progress=None):
    """Average magnitude difference function pitch tracker (Snack AMDF)."""
    x = to_mono(x)
    step = max(1, int(round(frame_length * rate)))
    nfr = int(len(x) // step)
    if nfr <= 0 or maxpitch <= minpitch or minpitch <= 0:
        return np.zeros(0)
    xd, rd, dec = _lowpass_decimate(x, rate, 16000)
    n = max(8, int(round(max(window_length, 2.0 / minpitch) * rd)))
    kmin = max(2, int(rd / maxpitch))
    kmax = int(math.ceil(rd / minpitch))
    L = n + kmax + 1
    centers = (np.arange(nfr) * step + step // 2) / dec
    starts = (centers - n / 2.0).astype(np.int64)
    pad = np.concatenate([np.zeros(L), xd, np.zeros(2 * L)])
    view = np.lib.stride_tricks.sliding_window_view(pad, L)
    fr = view[np.clip(starts + L, 0, len(pad) - L)]
    ref = fr[:, :n]
    lags = np.arange(kmin, kmax + 1)
    amdf = np.empty((nfr, len(lags)))
    for i, k in enumerate(lags):
        amdf[:, i] = np.mean(np.abs(ref - fr[:, k:k + n]), axis=1)
    scale = np.mean(np.abs(ref), axis=1) + 1e-9
    f0 = np.zeros(nfr)
    for i in range(nfr):
        a = amdf[i]
        j = int(np.argmin(a))
        # prefer the shortest lag whose dip is close to the global minimum
        thr = a[j] + 0.1 * (a.max() - a[j])
        dips = np.where((a[1:-1] <= a[:-2]) & (a[1:-1] <= a[2:]) & (a[1:-1] <= thr))[0] + 1
        if len(dips):
            j = int(dips[0])
        ratio = a[j] / scale[i]
        rms = math.sqrt(np.mean(ref[i] * ref[i]))
        if ratio < 0.45 and rms > 30.0:
            kk = float(lags[j])
            if 0 < j < len(a) - 1:
                den = a[j - 1] - 2 * a[j] + a[j + 1]
                if den > 0:
                    kk += 0.5 * (a[j - 1] - a[j + 1]) / den
            f0[i] = rd / kk
    # 3 point median smoothing
    if nfr >= 3:
        sm = f0.copy()
        for i in range(1, nfr - 1):
            sm[i] = sorted((f0[i - 1], f0[i], f0[i + 1]))[1]
        f0 = sm
    if progress:
        progress("", 1.0)
    return f0


def pitch(x, rate, method="ESPS", frame_length=0.01, window_length=0.01, maxpitch=400.0,
          minpitch=60.0, progress=None):
    fl, wl, mx, mn = sane_pitch_args(rate, frame_length, window_length, maxpitch, minpitch)
    kw = dict(frame_length=fl, window_length=wl, maxpitch=mx, minpitch=mn, progress=progress)
    if str(method).upper() == "AMDF":
        return pitch_amdf(x, rate, **kw)
    return pitch_esps(x, rate, **kw)


# --------------------------------------------------------------------------
# spectrogram


def _contrast_gain(contrast):
    c = float(contrast)
    return 1.0 + c / 25.0 if c >= 0 else 25.0 / (25.0 - c)


def parse_colormap(spec):
    """Colour list (e.g. '#000 #004 ...') -> Nx3 uint8 array or None for grey."""
    if isinstance(spec, (list, tuple)):
        items = [str(s) for s in spec]
    else:
        items = str(spec).split()
    items = [s.strip().strip("{}\"") for s in items if s.strip().strip("{}\"")]
    if not items:
        return None
    cols = []
    for c in items:
        c = c.lstrip("#")
        if len(c) == 3:
            r, g, b = (int(ch * 2, 16) for ch in c)
        elif len(c) == 6:
            r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        else:
            continue
        cols.append((r, g, b))
    if not cols:
        return None
    return np.array(cols, dtype=np.float64)


def spectrogram_ppm(x, rate, width, height, pps, fftlen=512, winlen=128,
                    window="Hamming", preemph=0.97, topfr=8000.0,
                    contrast=0.0, brightness=0.0, colormap=None):
    """Render a spectrogram as binary PPM (P6) bytes of size width x height."""
    width = max(1, int(width))
    height = max(1, int(height))
    x = to_mono(x)
    fftlen = int(_clampf(fftlen, 8, 65536, 512))
    winlen = int(min(_clampf(winlen, 2, 65536, 128), fftlen))
    preemph = _clampf(preemph, -1.0, 1.0, 0.0)
    contrast = _clampf(contrast, -1000.0, 1000.0, 0.0)
    brightness = _clampf(brightness, -1000.0, 1000.0, 0.0)
    topfr = _clampf(topfr, 0.0, rate / 2.0, rate / 2.0)
    img = np.full((height, width, 3), 255, dtype=np.uint8)
    if len(x) > 0 and pps > 0:
        if preemph:
            x = np.concatenate([[x[0]], x[1:] - float(preemph) * x[:-1]])
        centers = ((np.arange(width) + 0.5) / pps * rate).astype(np.int64)
        valid = centers < len(x)
        nv = int(valid.sum())
        if nv > 0:
            w = make_window(window, winlen)
            fr = _frames(x, centers[:nv], winlen) * w
            spec = np.fft.rfft(fr, n=fftlen, axis=1)
            pw = (spec.real ** 2 + spec.imag ** 2) / (np.sum(w) ** 2 / 4.0 + 1e-12)
            db = 10.0 * np.log10(pw + 1e-3)
            topfr = min(float(topfr) if topfr else rate / 2.0, rate / 2.0)
            freqs = topfr * (height - 0.5 - np.arange(height)) / height
            bins = freqs / rate * fftlen
            b0 = np.clip(np.floor(bins).astype(np.int64), 0, db.shape[1] - 1)
            b1 = np.clip(b0 + 1, 0, db.shape[1] - 1)
            frac = bins - np.floor(bins)
            rows = db[:, b0] * (1 - frac) + db[:, b1] * frac  # (nv, height)
            # 16bit full scale sine ~ 84 dB; show about 70 dB of range
            hi, lo = 84.0, 14.0
            lvl = (rows - lo) / (hi - lo)
            lvl = (lvl - 0.5) * _contrast_gain(contrast) + 0.5 + float(brightness) / 100.0
            lvl = np.clip(lvl, 0.0, 1.0).T  # (height, nv)
            cmap = colormap
            if cmap is None or len(cmap) < 2:
                g = (255.0 * (1.0 - lvl)).astype(np.uint8)
                img[:, :nv, 0] = g
                img[:, :nv, 1] = g
                img[:, :nv, 2] = g
            else:
                idx = np.clip((lvl * (len(cmap) - 1) + 0.5).astype(np.int64), 0, len(cmap) - 1)
                img[:, :nv, :] = cmap[idx].astype(np.uint8)
    header = b"P6\n%d %d\n255\n" % (width, height)
    return header + img.tobytes()


# --------------------------------------------------------------------------
# filters


def remove_dc(x):
    """Snack: filter iir -numerator "0.99 -0.99" -denominator "1 -0.99"."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 2:
        return np.stack([remove_dc(x[:, c]) for c in range(x.shape[1])], axis=1)
    n = len(x)
    if n == 0:
        return x
    u = 0.99 * x
    u[1:] -= 0.99 * x[:-1]
    klen = min(n, 4000)
    h = 0.99 ** np.arange(klen)
    size = 1
    while size < n + klen:
        size *= 2
    y = np.fft.irfft(np.fft.rfft(u, size) * np.fft.rfft(h, size), size)[:n]
    return y


def normalize_peak(x, peak=32767.0):
    m = np.max(np.abs(x)) if len(x) else 0
    if m <= 0:
        return x
    return x * (peak / m)


# --------------------------------------------------------------------------
# tuning fork ("onsa") synthesiser: generator + 4 formant filters


class Resonator:
    """Klatt resonator (Snack "filter formant")."""

    def __init__(self, freq, bw, rate):
        r = math.exp(-math.pi * bw / rate)
        self.a1 = 2.0 * r * math.cos(2.0 * math.pi * freq / rate)
        self.a2 = -r * r
        self.b = 1.0 - self.a1 - self.a2
        self.y1 = 0.0
        self.y2 = 0.0

    def process(self, x):
        a1, a2, b = self.a1, self.a2, self.b
        y1, y2 = self.y1, self.y2
        out = [0.0] * len(x)
        for i, v in enumerate(x):
            y = b * v + a1 * y1 + a2 * y2
            out[i] = y
            y2, y1 = y1, y
        self.y1, self.y2 = y1, y2
        return out


class OnsaSynth:
    """snack::filter generator $freq $vol 0.01 triangle $len composed with
    formant 500/50, 1500/75, 2500/100, 3500/150."""

    def __init__(self, freq, vol, rate, length=-1, shape=0.01):
        self.freq = float(freq)
        self.vol = float(vol)
        self.rate = int(rate)
        self.shape = shape
        self.remaining = length if length is not None and length >= 0 else -1
        self.phase = 0.0
        self.filters = [Resonator(500, 50, rate), Resonator(1500, 75, rate),
                        Resonator(2500, 100, rate), Resonator(3500, 150, rate)]
        # gain normalisation so that the output peak is about *vol*
        self.gain = self._estimate_gain()

    def _raw(self, n):
        ph = self.phase + np.arange(n) * self.freq / self.rate
        self.phase = (self.phase + n * self.freq / self.rate) % 1.0
        p = ph % 1.0
        s = self.shape
        return np.where(p < s, -1.0 + 2.0 * p / s, 1.0 - 2.0 * (p - s) / (1.0 - s))

    def _estimate_gain(self):
        save = self.phase
        fl = [Resonator(500, 50, self.rate), Resonator(1500, 75, self.rate),
              Resonator(2500, 100, self.rate), Resonator(3500, 150, self.rate)]
        n = int(self.rate * 0.1)
        x = list(self._raw(n))
        for f in fl:
            x = f.process(x)
        self.phase = save
        peak = max(abs(v) for v in x[n // 2:]) if n > 2 else 1.0
        return 1.0 / peak if peak > 1.0 else 1.0

    def next(self, n):
        """Return up to n samples (int16 scale), fewer at the end, None if done."""
        if self.remaining == 0:
            return None
        if self.remaining > 0:
            n = min(n, self.remaining)
            self.remaining -= n
        x = list(self._raw(n))
        for f in self.filters:
            x = f.process(x)
        return np.asarray(x) * (self.vol * self.gain)


# --------------------------------------------------------------------------
# MFCC based pre-utterance correction (port of tools/modifyPre.c + SPTK)


def _mel(f):
    return 1127.01048 * np.log(1.0 + f / 700.0)


def mfcc_sptk(x, rate, frame_length=4096, frame_period=256, order=30,
              channels=30, lifter=15, preemph=0.97):
    """wavdump | frame -l L -p P | window -l L -n 1 | mfcc -l L -f fs -m M -n N -c C -w 0"""
    x = to_mono(x) / 32768.0
    L = int(frame_length)
    P = int(frame_period)
    nfr = int(len(x) // P) + 1
    centers = np.arange(nfr) * P
    fr = _frames(x, centers, L)
    # window (Blackman, power normalised)
    w = np.blackman(L)
    w /= math.sqrt(np.sum(w * w))
    fr = fr * w
    # mfcc: pre-emphasis + Hamming
    if preemph:
        fr = np.concatenate([fr[:, :1], fr[:, 1:] - preemph * fr[:, :-1]], axis=1)
    fr = fr * np.hamming(L)
    spec = np.abs(np.fft.rfft(fr, n=L, axis=1))
    nb = spec.shape[1]
    fmax = rate / 2.0
    mel_max = _mel(fmax)
    mel_pts = np.linspace(0, mel_max, channels + 2)
    bin_mel = _mel(np.arange(nb) * rate / float(L))
    fb = np.zeros((channels, nb))
    for c in range(channels):
        lo, ce, hi = mel_pts[c], mel_pts[c + 1], mel_pts[c + 2]
        up = (bin_mel - lo) / (ce - lo)
        dn = (hi - bin_mel) / (hi - ce)
        fb[c] = np.maximum(0.0, np.minimum(up, dn))
    melspec = np.log(np.maximum(spec @ fb.T, 1.0e-5))
    j = np.arange(channels) + 0.5
    n = np.arange(1, order + 1)
    dct = np.sqrt(2.0 / channels) * np.cos(np.pi * np.outer(n, j) / channels)
    cep = melspec @ dct.T
    if lifter and lifter > 0:
        cep = cep * (1.0 + (lifter / 2.0) * np.sin(np.pi * n / lifter))
    return cep.astype(np.float32)


def parse_modify_pre_options(opt):
    """Parse the option string of modifyPre (genParam(autoAdjustRen2Opt))."""
    o = {"l": 4096, "p": 256, "m": 30, "t": 0.8, "s1": 100, "s2": 10}
    toks = str(opt).split()
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.startswith("-") and i + 1 < len(toks):
            key = t[1:]
            if key in ("l", "p", "m", "s1", "s2"):
                try:
                    o[key] = int(float(toks[i + 1]))
                except ValueError:
                    pass
                i += 2
                continue
            if key == "t":
                try:
                    o["t"] = float(toks[i + 1])
                except ValueError:
                    pass
                i += 2
                continue
            if key == "d":
                i += 2
                continue
        i += 1
    return o


def modify_pre(x, rate, positions, opt="", sample_rate_for_frames=44100):
    """Return corrected pre-utterance positions [sec] (list, same length).

    *sample_rate_for_frames* reproduces modifyPre.c which hard coded 44100 Hz
    when converting between seconds and frames.
    """
    o = parse_modify_pre_options(opt)
    L, P, M = o["l"], o["p"], o["m"]
    borderT, sr1, sr2 = o["t"], o["s1"], o["s2"]
    mf = mfcc_sptk(x, rate, L, P, M, M, 15)
    frame_num = mf.shape[0]
    SR = float(sample_rate_for_frames)
    out = []
    for p in positions:
        src = int(float(p) * SR / P)
        xl = max(0, src - sr1)
        xr = min(frame_num, src + sr1)
        yl = max(0, src - sr2)
        yr = min(frame_num, src + sr2)
        xnum = xr - xl
        ynum = yr - yl
        if xnum <= 0 or ynum <= 0:
            out.append(float(p))
            continue
        sxd = src - xl - (src - yl)
        a = mf[xl:xr]
        b = mf[yl:yr]
        diff = np.sqrt(np.sum((a[:, None, :] - b[None, :, :]) ** 2, axis=2) / M)  # (xnum, ynum)
        histo = np.zeros(xnum)
        for yd in range(ynum):
            ave = diff[:, yd].mean()
            xd = min(sxd + yd, xnum - 1)
            while xd >= 0:
                if diff[xd, yd] >= ave * borderT:
                    break
                xd -= 1
            if xd < 0:
                xd = min(sxd + yd, xnum - 1)
            histo[xd] += 1
        sxd_new = int(np.argmax(histo))
        out.append((sxd_new + xl) * P / SR)
    return out

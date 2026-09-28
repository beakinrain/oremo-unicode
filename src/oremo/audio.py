"""Audio engine (replaces Snack's sound objects and the external
oremo-recorder.exe / oremo-player.exe PortAudio helpers).

PortAudio is used through the ``sounddevice`` module.  Audio callbacks run
in PortAudio threads; everything that has to touch Tk is posted to
``ui_queue`` and executed by the application's main loop.
"""

import queue
import threading

import numpy as np

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - allows running the UI without audio
    sd = None

from . import wavio

ui_queue = queue.Queue()


def post(fn, *args):
    """Run fn(*args) in the Tk thread."""
    ui_queue.put((fn, args))


class AudioError(Exception):
    pass


def available():
    return sd is not None


# --------------------------------------------------------------------------
# Sound object (Snack "sound")


class Sound:
    def __init__(self, rate=44100, channels=1, encoding="Lin16"):
        self.rate = int(rate)
        self.channels = int(channels)
        self.encoding = encoding
        self.data = np.zeros((0, self.channels))
        self.filename = ""

    # snack: snd length
    def length(self):
        return self.data.shape[0]

    def length_sec(self):
        return self.data.shape[0] / float(self.rate) if self.rate else 0.0

    def flush(self):
        self.data = np.zeros((0, self.channels))

    def configure(self, rate=None, channels=None, encoding=None):
        if rate is not None:
            self.rate = int(rate)
        if channels is not None and int(channels) != self.channels:
            self.channels = int(channels)
            if self.data.shape[0] == 0:
                self.data = np.zeros((0, self.channels))
        if encoding is not None:
            self.encoding = encoding

    def read(self, path):
        a, rate, enc = wavio.read_wav(path)
        self.data = a
        self.rate = rate
        self.channels = a.shape[1]
        self.encoding = enc
        self.filename = path

    def write(self, path):
        wavio.write_wav(path, self.data, self.rate, self.encoding)

    def set_data(self, a, rate=None, encoding=None):
        a = np.asarray(a, dtype=np.float64)
        if a.ndim == 1:
            a = a.reshape(-1, 1)
        self.data = a
        self.channels = a.shape[1]
        if rate is not None:
            self.rate = int(rate)
        if encoding is not None:
            self.encoding = encoding

    def copy(self):
        s = Sound(self.rate, self.channels, self.encoding)
        s.data = self.data.copy()
        s.filename = self.filename
        return s

    def mono(self):
        if self.data.shape[1] == 1:
            return self.data[:, 0]
        return self.data.mean(axis=1)

    def max(self):
        if self.length() == 0:
            return 0
        return int(np.round(np.max(self.data)))

    def min(self):
        if self.length() == 0:
            return 0
        return int(np.round(np.min(self.data)))


# --------------------------------------------------------------------------
# Devices


def hostapi_name(idx):
    try:
        return sd.query_hostapis(idx)["name"]
    except Exception:
        return "?"


def list_devices(kind):
    """kind='input'/'output'. Returns list of (index, name, hostapi)."""
    if sd is None:
        return []
    out = []
    try:
        devs = sd.query_devices()
    except Exception:
        return []
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    for i, d in enumerate(devs):
        if d[key] > 0:
            out.append((i, d["name"], hostapi_name(d["hostapi"])))
    return out


def mme_devices(kind):
    """Devices of the MME host API (what Snack used on Windows)."""
    devs = list_devices(kind)
    mme = [d for d in devs if d[2] == "MME"]
    if mme:
        return mme
    # other systems (macOS CoreAudio): system default device first
    dflt = default_device(kind)
    devs.sort(key=lambda d: 0 if d[0] == dflt else 1)
    return devs


def system_api_label():
    """Label of the 'Snack' section in the audio I/O window."""
    import sys
    if sys.platform == "win32":
        return "Snack (MME)"
    if sys.platform == "darwin":
        return "Snack (CoreAudio)"
    return "Snack"


def pa_device_label(d):
    """Same format as oremo-recorder.exe 'list' output."""
    return "%d: %s, API=%s" % (d[0], d[1], d[2])


def default_device(kind):
    if sd is None:
        return None
    try:
        dflt = sd.default.device
        idx = dflt[0] if kind == "input" else dflt[1]
        if idx is None or idx < 0:
            return None
        return int(idx)
    except Exception:
        return None


def check_settings(kind, device, rate, channels, dtype):
    """Return '' when the settings are usable, else an error text."""
    if sd is None:
        return "sounddevice (PortAudio) is not available"
    try:
        if kind == "input":
            sd.check_input_settings(device=device, samplerate=rate, channels=channels, dtype=dtype)
        else:
            sd.check_output_settings(device=device, samplerate=rate, channels=channels, dtype=dtype)
    except Exception as e:
        return str(e)
    return ""


FORMAT_DTYPE = {"Int16": "int16", "Int24": "int32", "Int32": "int32", "Float32": "float32"}
FORMAT_ENC = {"Int16": "Lin16", "Int24": "Lin24", "Int32": "Lin32", "Float32": "Float"}


def _to16scale(block, dtype):
    b = block.astype(np.float64)
    if dtype == "int16":
        return b
    if dtype == "int32":
        return b / 65536.0
    return b * 32768.0  # float32


# --------------------------------------------------------------------------
# Output


class Player:
    """Plays a range of a buffer. Only one play at a time per Player."""

    def __init__(self, name):
        self.name = name
        self.stream = None
        self.lock = threading.RLock()
        self.pos = 0
        self.start_pos = 0
        self.end_pos = 0
        self.buf = None
        self.rate = 44100
        self.on_done = None
        self.token = 0
        self.volume = 1.0   # live volume factor (can change while playing)

    def active(self):
        return self.stream is not None

    def play(self, data, rate, start=0, end=-1, device=None, gain=1.0,
             on_done=None, latency=None, blocksize=0):
        """data: [n, ch] float 16-bit scale."""
        self.stop()
        if sd is None:
            raise AudioError("audio is not available")
        data = np.asarray(data, dtype=np.float64)
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        n = data.shape[0]
        if end is None or end < 0 or end > n:
            end = n
        start = max(0, min(int(start), n))
        end = int(end)
        if end <= start:
            if on_done:
                post(on_done)
            return
        buf = np.clip(data * (gain / 32768.0), -1.0, 1.0).astype(np.float32)
        with self.lock:
            self.buf = buf
            self.pos = start
            self.start_pos = start
            self.end_pos = end
            self.rate = int(rate)
            self.on_done = on_done
            self.token += 1
            token = self.token
        ch = buf.shape[1]

        def callback(outdata, frames, time, status):
            with self.lock:
                if token != self.token:
                    outdata.fill(0)
                    raise sd.CallbackStop
                p = self.pos
                m = min(frames, self.end_pos - p)
                if m > 0:
                    seg = self.buf[p:p + m]
                    vol = self.volume
                    outdata[:m] = seg if vol == 1.0 else np.clip(seg * vol, -1.0, 1.0)
                if m < frames:
                    outdata[max(m, 0):] = 0
                self.pos = p + max(m, 0)
                if self.pos >= self.end_pos:
                    raise sd.CallbackStop

        def finished():
            with self.lock:
                if token != self.token:
                    return
                cb = self.on_done
                self.on_done = None
            post(self._finished, token, cb)

        kw = {}
        if latency is not None:
            kw["latency"] = latency
        try:
            self.stream = sd.OutputStream(samplerate=self.rate, channels=ch, dtype="float32",
                                          device=device, callback=callback,
                                          finished_callback=finished, blocksize=blocksize, **kw)
            self.stream.start()
        except Exception as e:
            self.stream = None
            raise AudioError(str(e))

    def _finished(self, token, cb):
        if token != self.token:
            return
        self._close()
        if cb:
            cb()

    def _close(self):
        st = self.stream
        self.stream = None
        if st is not None:
            try:
                st.close()
            except Exception:
                pass

    def stop(self):
        """Stop without calling on_done (like 'snd stop')."""
        with self.lock:
            self.token += 1
            self.on_done = None
        self._close()

    def position_sec(self):
        with self.lock:
            return self.pos / float(self.rate) if self.rate else 0.0


class LoopPlayer:
    """Plays buf[0:period] over and over (metronome)."""

    def __init__(self):
        self.stream = None

    def active(self):
        return self.stream is not None

    def play(self, data, rate, period, device=None, gain=1.0):
        self.stop()
        data = np.asarray(data, dtype=np.float64)
        if data.ndim == 2:
            data = data.mean(axis=1)
        period = max(1, int(period))
        loop = np.zeros(period, dtype=np.float32)
        m = min(period, len(data))
        loop[:m] = np.clip(data[:m] * (gain / 32768.0), -1, 1)
        state = {"p": 0}

        def callback(outdata, frames, time, status):
            p = state["p"]
            idx = (p + np.arange(frames)) % period
            outdata[:, 0] = loop[idx]
            state["p"] = (p + frames) % period

        try:
            self.stream = sd.OutputStream(samplerate=int(rate), channels=1, dtype="float32",
                                          device=device, callback=callback)
            self.stream.start()
        except Exception as e:
            self.stream = None
            raise AudioError(str(e))

    def stop(self):
        st = self.stream
        self.stream = None
        if st is not None:
            try:
                st.stop()
                st.close()
            except Exception:
                pass


class SynthPlayer:
    """Plays samples produced by a generator object with a next(n) method."""

    def __init__(self):
        self.stream = None
        self.token = 0

    def active(self):
        return self.stream is not None

    def play(self, synth, rate, device=None, gain=1.0, on_done=None):
        self.stop()
        self.token += 1
        token = self.token

        def callback(outdata, frames, time, status):
            x = synth.next(frames)
            if x is None:
                outdata.fill(0)
                raise sd.CallbackStop
            m = len(x)
            outdata[:m, 0] = np.clip(x * (gain / 32768.0), -1, 1)
            if m < frames:
                outdata[m:] = 0
                raise sd.CallbackStop

        def finished():
            post(self._finished, token, on_done)

        try:
            self.stream = sd.OutputStream(samplerate=int(rate), channels=1, dtype="float32",
                                          device=device, callback=callback,
                                          finished_callback=finished)
            self.stream.start()
        except Exception as e:
            self.stream = None
            raise AudioError(str(e))

    def _finished(self, token, cb):
        if token != self.token:
            return
        st = self.stream
        self.stream = None
        if st is not None:
            try:
                st.close()
            except Exception:
                pass
        if cb:
            cb()

    def stop(self):
        self.token += 1
        st = self.stream
        self.stream = None
        if st is not None:
            try:
                st.stop()
                st.close()
            except Exception:
                pass


# --------------------------------------------------------------------------
# Input


class Recorder:
    """Input stream with explicit capture on/off (take buffers)."""

    def __init__(self):
        self.stream = None
        self.lock = threading.Lock()
        self.capturing = False
        self.blocks = []
        self.dtype = "int16"
        self.rate = 44100
        self.channels = 1
        self.gain = 1.0

    def is_open(self):
        return self.stream is not None

    def open(self, device, rate, channels, dtype, blocksize=0, gain=1.0):
        self.close()
        if sd is None:
            raise AudioError("audio is not available")
        self.dtype = dtype
        self.rate = int(rate)
        self.channels = int(channels)
        self.gain = gain

        def callback(indata, frames, time, status):
            if self.capturing:
                with self.lock:
                    if self.capturing:
                        self.blocks.append(indata.copy())

        try:
            self.stream = sd.InputStream(samplerate=self.rate, channels=self.channels,
                                         dtype=dtype, device=device, callback=callback,
                                         blocksize=blocksize)
            self.stream.start()
        except Exception as e:
            self.stream = None
            raise AudioError(str(e))

    def begin(self):
        with self.lock:
            self.blocks = []
            self.capturing = True
        self._peek_n = 0
        self._peek_data = np.zeros((0, self.channels))

    def peek(self):
        """Data captured so far (float64 16-bit scale) without stopping.
        Only the blocks added since the previous call are converted."""
        with self.lock:
            new = self.blocks[getattr(self, "_peek_n", 0):]
            self._peek_n = len(self.blocks)
        prev = getattr(self, "_peek_data", None)
        if prev is None:
            prev = np.zeros((0, self.channels))
        if new:
            a = _to16scale(np.concatenate(new, axis=0), self.dtype)
            if self.gain != 1.0:
                a = a * self.gain
            prev = np.concatenate([prev, a], axis=0)
            self._peek_data = prev
        return prev

    def end(self):
        """Stop capturing, return float64 [n, ch] 16-bit scale data."""
        with self.lock:
            self.capturing = False
            blocks = self.blocks
            self.blocks = []
        if blocks:
            a = np.concatenate(blocks, axis=0)
        else:
            a = np.zeros((0, self.channels), dtype=self.dtype)
        a = _to16scale(a, self.dtype)
        if self.gain != 1.0:
            a = a * self.gain
        return a

    def close(self):
        st = self.stream
        self.stream = None
        self.capturing = False
        if st is not None:
            try:
                st.stop()
                st.close()
            except Exception:
                pass


# --------------------------------------------------------------------------
# Guide BGM automatic recording


class AutoRecEngine:
    """Plays the guide BGM and fires the events of the BGM setting file.

    rows: dict seq -> dict(pStart, pStop, rStart, rStop, nextRec, repeat, msg)
    The logic is the one of OREMO's recursive ``autoRec`` procedure:
      entering row *seq* (at sample pStart):
        - if repeat != 0: in mode 3 jump to row *repeat* after the row's
          actions, otherwise stop the automatic recording
        - rStart -> start capturing, rStop -> stop capturing
        - nextRec -> (mode 3 and not last) move to next entry, else stop
        - show msg
    Capture on/off is done inside the audio callback so it is sample
    accurate relative to the BGM.  Everything else is posted to the UI.
    """

    def __init__(self, recorder):
        self.recorder = recorder
        self.stream = None
        self.lock = threading.Lock()
        self.token = 0
        self.volume = 1.0   # guide BGM volume (can change while playing)
        self.handler = None
        self.pos = 0

    def active(self):
        return self.stream is not None

    def start(self, bgm_data, rate, rows, mode, handler, can_next, device=None, gain=1.0):
        """handler(event, seq) is called in the UI thread with events
        'row' (actions for row seq), 'stop'.  can_next() is evaluated in the
        audio thread and must be cheap (returns True if nextRec is allowed)."""
        self.stop()
        data = np.asarray(bgm_data, dtype=np.float64)
        if data.ndim == 2:
            data = data.mean(axis=1)
        buf = np.clip(data * (gain / 32768.0), -1, 1).astype(np.float32)
        self.token += 1
        token = self.token
        self.handler = handler
        st = {"seq": 1, "pos": rows[1]["pStart"], "stopped": False}

        def enter(seq):
            """Executed in audio thread when a row begins. Returns next action."""
            r = rows[seq]
            if r["repeat"] != 0 and mode != 3:
                return "stop_before"      # autoRecStop before the row's actions
            if r["rStart"] != 0:
                self.recorder.begin()
            if r["rStop"] != 0 and self.recorder.capturing:
                self.recorder.capturing = False
            if r["nextRec"] != 0:
                if not (mode == 3 and can_next()):
                    return "stop_after"   # rec start/stop done, then autoRecStop
            return "ok"

        def fire(seq):
            act = enter(seq)
            if act != "ok":
                st["stopped"] = True
                post(self._ui_event, token, act, seq)
                return False
            post(self._ui_event, token, "row", seq)
            return True

        # execute row 1 immediately
        if not fire(1):
            return

        def callback(outdata, frames, time, status):
            if st["stopped"] or token != self.token:
                outdata.fill(0)
                raise sd.CallbackStop
            done = 0
            while done < frames:
                seq = st["seq"]
                r = rows[seq]
                p = st["pos"]
                stop_at = r["pStop"]
                if p >= stop_at:
                    # move to the next row
                    nxt = r["repeat"] if r["repeat"] != 0 else seq + 1
                    if nxt not in rows:
                        st["stopped"] = True
                        post(self._ui_event, token, "stop_before", seq)
                        break
                    st["seq"] = nxt
                    st["pos"] = rows[nxt]["pStart"]
                    if not fire(nxt):
                        break
                    continue
                m = min(frames - done, stop_at - p)
                seg = buf[max(0, p):max(0, p + m)] if p < len(buf) else buf[0:0]
                k = len(seg)
                if k:
                    vol = self.volume
                    outdata[done:done + k, 0] = seg if vol == 1.0 else np.clip(seg * vol, -1.0, 1.0)
                if k < m:
                    outdata[done + k:done + m, 0] = 0
                done += m
                st["pos"] = p + m
            if done < frames:
                outdata[done:] = 0
            if st["stopped"]:
                raise sd.CallbackStop
            self.pos = st["pos"]

        try:
            self.stream = sd.OutputStream(samplerate=int(rate), channels=1, dtype="float32",
                                          device=device, callback=callback)
            self.stream.start()
        except Exception as e:
            self.stream = None
            raise AudioError(str(e))

    def _ui_event(self, token, ev, seq):
        if token != self.token:
            return
        if self.handler:
            self.handler(ev, seq)

    def stop(self):
        self.token += 1
        st = self.stream
        self.stream = None
        if st is not None:
            try:
                st.stop()
                st.close()
            except Exception:
                pass

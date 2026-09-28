"""Fake 'sounddevice' module for tests: streams run in threads (optionally
faster than real time); the input delivers a sung-like tone.  Nothing is
played or recorded on real hardware."""

import threading
import time

import numpy as np


class CallbackStop(Exception):
    pass


class FakeStream:
    SPEED = 1.0   # 1.0 = real time

    def __init__(self, samplerate=44100, channels=1, dtype="float32", device=None, callback=None,
                 finished_callback=None, blocksize=0, latency=None, kind="out"):
        self.rate, self.ch, self.dtype = samplerate, channels, dtype
        self.cb, self.fin = callback, finished_callback
        self.bs = blocksize or 1024
        self.kind = kind
        self.running = False
        self.peak = 0.0          # largest |sample| handed to an output stream
        FakeSD.last[kind] = self

    def start(self):
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        n = 0
        while self.running:
            try:
                if self.kind == "out":
                    buf = np.zeros((self.bs, self.ch), dtype=np.float32)
                    self.cb(buf, self.bs, None, None)
                    self.peak = max(self.peak, float(np.max(np.abs(buf))))
                else:
                    t = (n + np.arange(self.bs)) / self.rate
                    ph = 2 * np.pi * 220 * t
                    sig = sum(np.sin(k * ph) / k for k in range(1, 8))
                    amp = 6000 if self.dtype == "int16" else 6000 * 65536
                    data = (sig * amp).astype(self.dtype).reshape(-1, 1)
                    self.cb(np.repeat(data, self.ch, axis=1), self.bs, None, None)
                n += self.bs
            except CallbackStop:
                break
            time.sleep(self.bs / self.rate / self.SPEED)
        self.running = False
        if self.fin:
            self.fin()

    def stop(self):
        self.running = False

    def close(self):
        self.running = False


class FakeSD:
    CallbackStop = CallbackStop
    last = {}

    def OutputStream(self, **kw):
        return FakeStream(kind="out", **kw)

    def InputStream(self, **kw):
        return FakeStream(kind="in", **kw)

    def query_devices(self):
        return [{"name": "Fake In", "hostapi": 0, "max_input_channels": 2, "max_output_channels": 0},
                {"name": "Fake Out", "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2}]

    def query_hostapis(self, i=None):
        d = {"name": "Core Audio"}
        return d if i is not None else [d]

    class default:
        device = (0, 1)

    def check_input_settings(self, **k):
        pass

    def check_output_settings(self, **k):
        pass

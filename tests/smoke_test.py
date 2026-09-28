"""End-to-end smoke test (Windows and macOS).

    python tests/smoke_test.py [lang]

Uses a fake audio device (tests/fakesd.py) and a temporary copy of res/, so
no sound is played or recorded and no user settings are touched.
Exits with status 1 if any check fails or any Tk callback raised.
"""

import faulthandler
import os
import shutil
import sys
import tempfile

# if anything blocks (e.g. a modal dialog), print where every thread is and exit
faulthandler.dump_traceback_later(float(os.environ.get("OREMO_TEST_TIMEOUT", "240")), exit=True)
import time
import traceback
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402
import tkinter.filedialog as fd  # noqa: E402
import tkinter.messagebox as mb  # noqa: E402

import fakesd  # noqa: E402
from oremo import audio, plat, wavio  # noqa: E402

LANG = sys.argv[1] if len(sys.argv) > 1 else "zh_CN"
audio.sd = fakesd.FakeSD()
tmp = tempfile.mkdtemp(prefix="oremo_test_")
top = os.path.join(tmp, "res")
shutil.copytree(os.path.join(ROOT, "res"), top)
with open(os.path.join(top, "oremo-setting.ini"), "a", encoding="utf-8") as fp:
    fp.write("lang=%s\n" % LANG)
# keep everything inside the temp folder (macOS would use ~/Library, ~/Documents)
plat.user_dir = lambda topdir: topdir
plat.default_save_dir = lambda topdir: os.path.join(topdir, "result")
result = os.path.join(top, "result")
os.makedirs(result, exist_ok=True)

sr = 44100
t = np.arange(int(sr * 1.5)) / sr
ph = 2 * np.pi * 220 * t
x = 6000 * sum(np.sin(k * ph) / k for k in range(1, 12)) * ((t > 0.3) & (t < 1.3))
wavio.write_wav(os.path.join(result, "あ.wav"), x, sr, "Lin16")
wavio.write_wav(os.path.join(result, "い.wav"), x, sr, "Lin24")
# decomposed (NFD) file name as macOS / zip tools may produce: "が"
wavio.write_wav(os.path.join(result, unicodedata.normalize("NFD", "が") + ".wav"), x, sr, "Lin16")

msgs = []
for n in ("showinfo", "showwarning", "showerror"):
    setattr(mb, n, lambda *a, _n=n, **k: msgs.append((_n, a)))
fd.asksaveasfilename = lambda **k: os.path.join(result, "oto.ini")
fd.askopenfilename = lambda **k: ""

from oremo.app import OremoApp  # noqa: E402

print("creating app", flush=True)
app = OremoApp(top, [])
print("app created", flush=True)
errors = []
app.root.report_callback_exception = lambda e, v, tb: errors.append("".join(traceback.format_exception(e, v, tb)))
root, v = app.root, app.v
checks = {}


def check(name, cond, info=""):
    checks[name] = bool(cond)
    print("%-28s %s %s" % (name, "OK " if cond else "NG ", info))


def step(name, fn):
    print("  step:", name, flush=True)
    try:
        fn()
        root.update()
    except Exception:
        errors.append(name + ":\n" + traceback.format_exc())


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.005)


print("platform", sys.platform, "lang", LANG, "scale", app.S, "Tk", root.tk.call("info", "patchlevel"))
check("reclist loaded", len(app.recList()) > 100, "%d items" % len(app.recList()))
for key, fn in (("showSpec", app.toggleSpec), ("showpow", app.togglePow), ("showf0", app.toggleF0)):
    v[key] = 1
    step(key, fn)
step("redraw", lambda: app.Redraw("all"))
check("wave drawn", app.snd.length() > 0 and app.c.find_withtag("wave"))
step("next", app.nextRec)
check("navigation", v["recLab"] == "い" and app.snd.encoding == "Lin24")
step("prev", app.prevRec)

# every sub window opens
for name, fn in (("settings", app.settings), ("io", app.ioSettings), ("bgm", app.bgmGuide),
                 ("tempo", app.tempoGuide), ("pitch", app.pitchGuide), ("bind", app.setBind),
                 ("font", app.setFontSize), ("search", app.searchComment), ("enc", app.encodingSettings),
                 ("fix", app.fixSettings), ("conv", app.converterWindow), ("genParam", app.genParam),
                 ("estimate", app.estimateParam)):
    step("open " + name, fn)
before = len(errors)


# advanced settings: every menu entry, slider end, and bad input in every field
def walk(wd):
    yield wd
    for c in wd.winfo_children():
        yield from walk(c)
w = root.nametowidget(".settings")
apply_btn = [b for b in walk(w) if isinstance(b, tk.Button) and b.cget("text") == app.tt(".confm.apply")][0]
n = 0
for wd in list(walk(w)):
    if isinstance(wd, tk.Menubutton):
        menu = wd.nametowidget(wd.cget("menu"))
        for i in range((menu.index("end") or 0) + 1):
            step("menu", lambda: (menu.invoke(i), apply_btn.invoke()))
            n += 1
    elif isinstance(wd, tk.Scale):
        for val in (wd.cget("from"), wd.cget("to")):
            step("scale", lambda: (wd.set(val), root.update(), apply_btn.invoke()))
            n += 1
    elif isinstance(wd, tk.Entry):
        orig = wd.get()
        for val in ("", "abc", "-5", "0", "99999", "0.5"):
            step("entry", lambda: (wd.delete(0, "end"), wd.insert(0, val), apply_btn.invoke()))
            n += 1
        step("entry", lambda: (wd.delete(0, "end"), wd.insert(0, orig), apply_btn.invoke()))
check("settings exhaustive", len(errors) == before, "%d actions" % n)
# the sweep leaves the last menu entries selected (F0 range B5..B5): restore defaults
for k, val in (("showMinTone", "C"), ("showMinOctave", 2), ("showMaxTone", "B"), ("showMaxOctave", 5),
               ("unit", "semitone"), ("fixShowRange", 1), ("method", "ESPS")):
    app.f0[k] = val
step("apply defaults", apply_btn.invoke)
for p in (".settings", ".iosettings", ".converter", ".fixSettings", ".encSettings"):
    try:
        root.nametowidget(p).destroy()
    except KeyError:
        pass


# oto.ini generation
def tandoku():
    app.makeRecListFromDir(0, 0)
    app.doEstimateParam("all")
    app.saveParamFile(os.path.join(result, "oto.ini"))
step("tandoku", tandoku)
oto = open(os.path.join(result, "oto.ini"), "rb").read().decode("cp932")
check("oto.ini single (sjis)", "あ.wav=" in oto and "が.wav=" in oto, oto.splitlines()[0] if oto else "")
check("NFD file name -> NFC", "が" in app.makeRecListFromDir(0, 0))
step("renzoku", lambda: (app.initGenParam(), app.doGenParamForOREMO(),
                         app.saveParamFile(os.path.join(result, "oto-ren.ini"))))
check("oto.ini continuous", os.path.getsize(os.path.join(result, "oto-ren.ini")) > 0)

# reload the reclist and go back to the start
step("reclist", lambda: (app.readRecList(v["recListFile"]), app.resetDisplay()))

# manual recording with live display
calls = []
orig_redraw = app.Redraw
app.Redraw = lambda opt: (calls.append(opt), orig_redraw(opt))
v["rec"] = 1
step("recStart", app.recStart)
pump(1.5)
live = calls.count("live")
check("live display", live >= 5 and app.c.find_withtag("f0"), "%d live redraws" % live)
step("recStop", app.recStop)
check("take recorded", app.snd.length() > sr // 2 and v.i("recStatus") == 1, "%d samples" % app.snd.length())
step("save by next", app.nextRec)
check("take saved", os.path.exists(os.path.join(result, "あ.wav")))
app.Redraw = orig_redraw

# automatic recording, mode 3 (BGM 20x faster than real time)
fakesd.FakeStream.SPEED = 8.0
v["rec"] = 3
seq0 = v.i("recSeq")
step("autoRec", app.recStart)
# wait for two automatic moves (slow CI machines may run the fake device slowly)
end = time.time() + 90
while time.time() < end and v.i("recSeq") < seq0 + 2:
    pump(0.2)
step("autoRecStop", app.autoRecStop)
check("auto recording mode 3", v.i("recSeq") >= seq0 + 2, "moved %d items" % (v.i("recSeq") - seq0))
fakesd.FakeStream.SPEED = 1.0

# fonts: a simplified Chinese list must get a font that has all its glyphs
open(os.path.join(top, "zh.txt"), "wb").write("萨迪克进化\n三等奖\n山东科技\nあいう\n".encode("gbk"))
step("zh reclist", lambda: (app.readRecList(os.path.join(top, "zh.txt")), app.resetDisplay()))
fam = app._fonts["kfont"].cget("family")
miss = app._font_missing_chars(fam, app._list_text())
check("list font covers text", miss == "", "%s missing=%r" % (fam, miss))

print("messages:", msgs[:3])
print("ERRORS:", len(errors))
for e in errors[:5]:
    print(e)
ok = all(checks.values()) and not errors
print("RESULT:", "PASS" if ok else "FAIL")
try:
    app.recorder.close()
    root.destroy()
except Exception:
    pass
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(0 if ok else 1)

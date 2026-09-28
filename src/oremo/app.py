"""OREMO main program (port of oremo.tcl / proc.tcl / globalVar.tcl)."""

import math
import os
import re
import subprocess
import sys
import traceback
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.font as tkfont
import tkinter.messagebox as messagebox
import webbrowser

import numpy as np

from . import audio, dsp, fixes, snackui, tclfmt, textenc
from .audio import Sound
from .dialogs import DialogsMixin
from .genparam import GenParamMixin
from .state import TclArray, TVar
from .tools import ToolsMixin

APPNAME = "OREMO"
VERSION = "3.0-b190106-U1"

TONE_LIST = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

LANGS = [("ja", "日本語"), ("zh_CN", "简体中文"), ("en", "English")]


def _fwd(p):
    """Tcl style path (forward slashes)."""
    return p.replace("\\", "/") if p else p


# v() keys that hold sizes in screen pixels (scaled for high DPI screens)
GEOM_KEYS = ["yaxisw", "timeh", "waveh", "wavehbackup", "wavehmin", "spech", "spechbackup", "spechmin",
             "powh", "powhmin", "powhbackup", "f0h", "f0hmin", "f0hbackup", "cWidth", "cWidthMin",
             "winWidth", "winWidthMin", "winHeight", "winHeightMin"]

UI_SCALES = ["auto", "1.0", "1.25", "1.5", "1.75", "2.0", "2.5", "3.0"]


def _peek_sysini(path):
    """Read oremo-setting.ini before Tk exists (for DPI settings)."""
    out = {}
    try:
        text, _ = textenc.read_text(path)
    except OSError:
        return out
    for line in text.split("\n"):
        m = re.match(r"^([^=]+)=(.*)$", line.strip("\r"))
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def enable_dpi_awareness():
    """Render at the real screen resolution instead of letting Windows
    stretch a 96 dpi bitmap (which makes the window blurry on 4K)."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # system DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def setup_scaling(root, ui_scale, dpi_aware):
    """Return the pixel scale factor S (1.0 = 96 dpi) and make Tk fonts follow it."""
    sys_scale = root.winfo_fpixels("1i") / 96.0 if dpi_aware else 1.0
    try:
        S = float(ui_scale) if ui_scale not in ("", "auto") else sys_scale
    except ValueError:
        S = sys_scale
    S = max(0.5, min(S, 4.0))
    # point sized fonts follow 'tk scaling' (pixels per point)
    root.tk.call("tk", "scaling", S * 96.0 / 72.0)
    # the default fonts are defined in pixels on Windows: convert them to points
    for name in ("TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont", "TkHeadingFont",
                 "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
        try:
            f = tkfont.nametofont(name, root=root)
        except tk.TclError:
            continue
        size = int(f.cget("size"))
        if size < 0:
            px96 = -size / sys_scale if sys_scale else -size
            f.configure(size=max(6, int(round(px96 * 72.0 / 96.0))))
    try:
        from tkinter import ttk
        st = ttk.Style(root)
        st.configure("Treeview", rowheight=int(round(20 * S)))
    except Exception:
        pass
    return S


class OremoApp(DialogsMixin, GenParamMixin, ToolsMixin):

    # ------------------------------------------------------------------
    # initialisation (globalVar.tcl + main of oremo.tcl)

    def __init__(self, topdir, argv):
        self.topdir = _fwd(os.path.abspath(topdir))
        pre = _peek_sysini(os.path.join(self.topdir, "oremo-setting.ini"))
        dpi_aware = pre.get("dpiAware", "1") != "0"
        if dpi_aware:
            enable_dpi_awareness()
        self.root = tk.Tk(className="Oremo")
        self.root.withdraw()
        self.S = setup_scaling(self.root, pre.get("uiScale", "auto"), dpi_aware)
        snackui.SCALE = self.S
        self.root.report_callback_exception = self._bgerror
        tkapp = self.root.tk
        self.tk = tkapp
        self.v = TclArray(tkapp, "v")
        self.f0 = TclArray(tkapp, "f0")
        self.power = TclArray(tkapp, "power")
        self.startup = TclArray(tkapp, "startup")
        self.dev = TclArray(tkapp, "dev")
        self.uttTiming = TclArray(tkapp, "uttTiming")
        self.genParamA = TclArray(tkapp, "genParam")
        self.estimate = TclArray(tkapp, "estimate")
        self.keys = TclArray(tkapp, "keys")
        self.bgmParam = TclArray(tkapp, "bgmParam")
        self.paDev = TclArray(tkapp, "paDev")
        self.t = TclArray(tkapp, "t")
        self.arrays = {
            "v": self.v, "f0": self.f0, "power": self.power, "startup": self.startup,
            "dev": self.dev, "uttTiming": self.uttTiming, "genParam": self.genParamA,
            "estimate": self.estimate, "keys": self.keys, "bgmParam": self.bgmParam,
        }
        self.debug = 0
        self.comments = {}          # v(recComment,<name>) of the original
        self.paramU = {}
        self.paramS = {}
        self.paramUsize = 1
        self.unknown_init = []      # (array, key, value) kept for round trip
        self.custom_binds = []      # sequences bound by doSetBind
        self.console_win = None
        self.log_lines = []
        self.bgm_rows = {}
        self.pa_rec_on = False      # "oremo-recorder.exe is running"
        self.pa_play_on = False     # "oremo-player.exe is running"
        self.read_encoding = {}     # file -> encoding detected when read
        self.scrollWidget = ""
        self.conState = 0
        self._rec_seq_cache = 0
        self._rec_len_cache = 0

        # sounds and players (snack::sound snd / onsa / metro / bgm)
        self.snd = Sound(44100, 1, "Lin16")
        self.bgm = Sound(44100, 1, "Lin16")
        self.metro = Sound(44100, 1, "Lin16")
        self.player = audio.Player("snd")
        self.bgm_player = audio.Player("bgm")
        self.onsa_player = audio.SynthPlayer()
        self.sin_player = audio.SynthPlayer()
        self.metro_player = audio.LoopPlayer()
        self.recorder = audio.Recorder()
        self.auto_engine = audio.AutoRecEngine(self.recorder)

        self.sysini = {}
        self._set_defaults()
        for k in GEOM_KEYS:
            self.v[k] = int(round(self.v.i(k) * self.S))
        self._parse_args(argv)
        self.readSysIniFile(early=True)
        self._load_messages()

        # read the startup file (pixel sizes are converted from the scale they were saved at)
        if os.path.exists(self.startup["initFile"]):
            try:
                saved = float(pre.get("pxScale", "1.0"))
            except ValueError:
                saved = 1.0
            self.doReadInitFile(self.startup["initFile"], px_factor=self.S / saved if saved > 0 else 1.0)
        if self.fix("F08"):
            self.bgmParam["autoRecStatus"] = 0

        self.audioSettings()
        self.fontSetting()
        if self.startup.i("readRecList"):
            self.readRecList(self.v["recListFile"])
        if self.startup.i("readTypeList"):
            self.readTypeList(self.v["typeListFile"])
        if self.startup.i("readCommentList"):
            self.readCommentList("%s/%s-comment.txt" % (self.v["saveDir"], self.v["appname"]))
        if self.startup.i("choosesaveDir"):
            self.choosesaveDir()
        if self.startup.i("makeRecListFromDir"):
            self.makeRecListFromDir()
        self.setSinScale()

        self._build_menus()
        self._build_main_window()
        self._bind_keys()

        self.f0["showMax"] = self.tone2freq(self.f0["showMaxTone"] + self.f0["showMaxOctave"])
        self.f0["showMin"] = self.tone2freq(self.f0["showMinTone"] + self.f0["showMinOctave"])
        self.f0["tgtFreq"] = self.tone2freq(self.f0["tgtTone"] + self.f0["tgtOctave"])
        self.f0["guideFreqTmp"] = self.tone2freq(self.f0["guideTone"] + self.f0["guideOctave"])
        self.readSysIniFile()
        if self.fix("F09"):
            self._restore_audio_settings()
        self.resetDisplay()

        self.root.protocol("WM_DELETE_WINDOW", self.Exit)
        self.root.title("%s %s" % (self.v["appname"], self.v["version"]))
        self.root.resizable(1, 1)
        self._set_icon()
        self.root.deiconify()
        self.root.update()
        v = self.v
        v["winWidthMin"] = self.root.nametowidget(".fig").winfo_x() + v.i("cWidthMin")
        v["winHeightMin"] = (self.root.nametowidget(".fig").winfo_y() + v.i("wavehmin") + v.i("timeh")
                             + (v.i("spechmin") if v.i("spech") else 0)
                             + (v.i("powhmin") if v.i("powh") else 0)
                             + (v.i("f0hmin") if v.i("f0h") else 0)
                             + self.root.nametowidget(".saveDir").winfo_height()
                             + self.root.nametowidget(".msg").winfo_height())
        self.root.minsize(v.i("winWidthMin"), v.i("winHeightMin"))
        v["winWidth"] = self.root.winfo_width()
        v["winHeight"] = self.root.winfo_height()
        self.root.after(1000, lambda: self.root.bind("<Configure>", lambda e: self.changeWindowBorder()))
        self.root.after(20, self._poll_audio_queue)

    def run(self):
        self.root.mainloop()

    # ------------------------------------------------------------------

    def _set_defaults(self):
        topdir = self.topdir
        v, f0, power = self.v, self.f0, self.power
        v["appname"] = APPNAME
        v["version"] = VERSION
        v["recListFile"] = topdir + "/reclist.txt"
        v["typeListFile"] = topdir + "/typelist.txt"
        v["saveDir"] = topdir + "/result"
        v["paramFile"] = v["saveDir"] + "/oto.ini"
        v["yaxisw"] = 40
        v["timeh"] = 20
        v["showWave"] = 1
        v["waveh"] = 100
        v["wavehbackup"] = 100
        v["wavehmin"] = 50
        v["wavepps"] = 200
        v["waveScale"] = 32768
        v["sfont"] = ("Helvetica", 8, "bold")
        v["bg"] = self.root.cget("bg")
        v["fg"] = "black"
        v["wavColor"] = "black"
        v["recStatus"] = 0
        v["playStatus"] = 0
        v["playOnsaStatus"] = 0
        v["recList"] = []
        v["recSeq"] = 0
        v["recLab"] = ""
        v["typeList"] = [""]
        v["typeLab"] = ""
        v["typeSeq"] = 0
        v["bigFontSize"] = 24
        v["fontSize"] = 18
        v["smallFontSize"] = 14
        v["commFontSize"] = 18
        v["msg"] = ""
        v["rec"] = 1
        v["recNow"] = 0
        v["ext"] = "wav"
        v["autoSaveInitFile"] = 1
        v["skipChangeWindowBorder"] = 0

        v["showSpec"] = 0
        v["spech"] = 0
        v["spechbackup"] = 140
        v["spechmin"] = 50
        v["topfr"] = 8000
        v["cmap"] = "grey"
        v["contrast"] = 0
        v["brightness"] = 0
        v["fftlen"] = 512
        v["winlen"] = 128
        v["window"] = "Hamming"
        v["preemph"] = 0.97

        v["showpow"] = 0
        v["powh"] = 0
        v["powhmin"] = 50
        v["powhbackup"] = 100
        power["frameLength"] = 0.02
        power["window"] = "Hanning"
        power["preemphasis"] = 0.97
        power["windowLength"] = 0.01
        power["power"] = []
        power["powerMax"] = 0
        power["powerMin"] = 0
        v["powcolor"] = "blue"

        power["uttLow"] = 28
        power["uttHigh"] = 28
        power["uttKeep"] = 5
        power["vLow"] = 40
        power["uttLengthSec"] = 0.1
        power["uttLength"] = self.sec2samp(power["uttLengthSec"], power["frameLength"])
        power["silLengthSec"] = 0.0
        power["silLength"] = self.sec2samp(power["silLengthSec"], power["frameLength"])
        power["fid"] = ""

        v["toneList"] = TONE_LIST
        v["sinScaleMin"] = 2
        v["sinScaleMax"] = 5
        v["sinScale"] = []
        v["sinNote"] = []
        f0["checkVol"] = 4000
        f0["guideVol"] = 4000
        f0["tgtTone"] = TONE_LIST[0]
        f0["tgtOctave"] = 2
        f0["tgtFreq"] = 0
        f0["showToneLine"] = 1
        f0["showTgtLine"] = 0
        f0["fid"] = ""
        f0["extractedMin"] = 0
        f0["extractedMax"] = 0

        v["showf0"] = 0
        v["f0h"] = 0
        v["f0hmin"] = 50
        v["f0hbackup"] = 100
        f0["method"] = "ESPS"
        f0["frameLength"] = 0.01
        f0["windowLength"] = 0.01
        f0["max"] = 800
        f0["min"] = 60
        f0["showMax"] = 400
        f0["showMin"] = 200
        f0["showMinTone"] = TONE_LIST[0]
        f0["showMinOctave"] = 2
        f0["showMaxTone"] = TONE_LIST[-1]
        f0["showMaxOctave"] = 5
        f0["guideTone"] = "C"
        f0["guideOctave"] = 3
        f0["guideFreqTmp"] = 131
        f0["f0"] = []
        v["f0color"] = "blue"
        v["tgtf0color"] = "red"
        f0["fixShowRange"] = 1
        f0["unit"] = "semitone"

        v["removeDC"] = 0
        v["showParam"] = 1

        v["cWidth"] = 500
        v["cWidthMin"] = v.i("yaxisw") + 100
        v["cHeight"] = v.i("waveh") + v.i("spech") + v.i("powh") + v.i("f0h") + v.i("timeh")
        v["winWidth"] = 640
        v["winWidthMax"] = self.root.maxsize()[0]
        v["winHeight"] = 0
        v["winWidthMin"] = 400
        v["winHeightMin"] = 100

        v["sampleRate"] = 44100
        v["paramChanged"] = 0
        v["sdirection"] = 1
        v["sMatch"] = "full"
        v["keyword"] = ""
        v["recComment"] = ""

        v["grey"] = " "
        v["color1"] = ("#000 #004 #006 #00A #00F #02F #04F #06F #08F #0AF #0CF #0FF #0FE "
                       "#0FC #0FA #0F8 #0F6 #0F4 #0F2 #0F0 #2F0 #4F0 #6F0 #8F0 #AF0 #CF0 #FE0 "
                       "#FC0 #FA0 #F80 #F60 #F40 #F20 #F00").split()
        v["color2"] = ("#FFF #BBF #77F #33F #00F #07F #0BF #0FF #0FB #0F7 #0F0 #3F0 #7F0 "
                       "#BF0 #FF0 #FB0 #F70 #F30 #F00").split()

        s = self.startup
        s["arrayForInitFile"] = ["bgmParam", "v", "f0", "power", "startup", "dev",
                                 "uttTiming", "genParam", "estimate", "keys"]
        s["exclusionKeysForInitFile,aName"] = ["startup", "v", "power", "f0", "estimate"]
        s["exclusionKeysForInitFile,startup"] = [
            "arrayForInitFile", "choosesaveDir", "exclusionKeysForInitFile,aName",
            "exclusionKeysForInitFile,startup", "exclusionKeysForInitFile,v",
            "exclusionKeysForInitFile,power", "exclusionKeysForInitFile,f0",
            "exclusionKeysForInitFile,estimate", "autoReadParamFile"]
        s["exclusionKeysForInitFile,v"] = [
            "paramChanged", "msg", "ext", "appname", "version", "sndLength",
            "recList", "recLab", "recSeq", "typeList", "typeLab", "typeSeq", "listSeq",
            "recStatus", "playStatus", "playOnsaStatus", "playMetroStatus"]
        s["exclusionKeysForInitFile,power"] = ["power", "fid"]
        s["exclusionKeysForInitFile,f0"] = ["f0", "extractedMin", "extractedMax", "fid"]
        s["exclusionKeysForInitFile,estimate"] = []
        s["readRecList"] = 1
        s["readTypeList"] = 1
        s["readCommentList"] = 1
        s["makeRecListFromDir"] = 0
        s["choosesaveDir"] = 0
        s["initFile"] = topdir + "/oremo-init.tcl"
        s["sysIniFile"] = topdir + "/oremo-setting.ini"
        s["textFile"] = topdir + "/message/oremo-text.tcl"
        s["procTextFile"] = topdir + "/message/proc-text.tcl"

        v["tempo"] = 120
        v["tempoMSec"] = 60000.0 / v.i("tempo")
        v["playMetroStatus"] = 0
        v["clickWav"] = topdir + "/guideBGM/click.wav"
        v["bgmFile"] = topdir + "/guideBGM/F4-100bpm.wav"
        v["bgmParamFile"] = topdir + "/guideBGM/F4-100bpm.txt"
        v["setE"] = 1

        self.bgmParam["autoRecStatus"] = 0

        u = self.uttTiming
        u["clickWav"] = topdir + "/guideBGM/click.wav"
        u["tempo"] = 100
        u["preCount"] = 3
        u["mix"] = 0.5

        g = self.genParamA
        g["bpm"] = 100
        g["bpmU"] = "bpm"
        g["S"] = 0
        g["SU"] = "msec"
        g["O"] = 0
        g["OU"] = "msec"
        g["P"] = 0
        g["PU"] = "msec"
        g["C"] = 0
        g["CU"] = "msec"
        g["E"] = 0
        g["EU"] = "msec"
        g["autoAdjustRen"] = 1
        g["vLow"] = 5
        g["sRange"] = 300
        g["avePPrev"] = 0
        g["autoAdjustRen2"] = 1
        g["autoAdjustRen2Opt"] = "-s1 200 -s2 10 -l 2048 -p 128 -m 30 -t 1.0 -d tools"
        g["autoAdjustRen2Pattern"] = "あ い う え お ん"

        e = self.estimate
        e["S"] = 1
        e["E"] = 1
        e["C"] = 1
        e["P"] = 1
        e["O"] = 1
        e["minC"] = 0.001

        p = self.paDev
        p["devList"] = ["none"]
        p["outdevList"] = ["none"]
        p["in"] = "none"
        p["out"] = "none"
        p["useRequestRec"] = 0
        p["useRequestPlay"] = 0
        p["useRec"] = 0
        p["usePlay"] = 0
        p["sampleRate"] = 44100
        p["sampleFormat"] = "Int16"
        p["channel"] = 1
        p["bufferSize"] = 2048

    # ------------------------------------------------------------------
    # command line (-saveDir / -script / folder dropped on the icon)

    def _parse_args(self, argv):
        i = 0
        while i < len(argv):
            opt = argv[i]
            if opt == "-saveDir":
                i += 1
                if i < len(argv):
                    self.v["saveDir"] = _fwd(argv[i])
            elif opt == "-script":
                i += 1
                if i < len(argv):
                    self.startup["initFile"] = _fwd(argv[i])
            else:
                p = os.path.normpath(os.path.abspath(opt))
                if os.path.isdir(p):
                    self.v["saveDir"] = _fwd(p)
                    self.startup["choosesaveDir"] = 0
                elif os.path.isdir(os.path.dirname(p)):
                    self.v["saveDir"] = _fwd(os.path.dirname(p))
                    self.startup["choosesaveDir"] = 0
                else:
                    print("error: invalid option: %s" % opt)
                    self.usage()
            i += 1

    def usage(self):
        print("usage: oremo [-saveDir saveDir] [-script initScript] [folder]")

    # ------------------------------------------------------------------
    # oremo-setting.ini (sys ini) - also holds the Unicode extension settings

    def readSysIniFile(self, early=False):
        fn = self.startup["sysIniFile"]
        try:
            text, _ = textenc.read_text(fn)
        except OSError:
            return
        for line in text.split("\n"):
            line = line.strip("\r")
            m = re.match(r"^([^=]+)=(.*)$", line)
            if not m:
                continue
            key, val = m.group(1).strip(), m.group(2).strip()
            self.sysini[key] = val
            if key == "autoSaveInitFile" and not early:
                self.v["autoSaveInitFile"] = val

    def writeSysIniFile(self):
        fn = self.startup["sysIniFile"]
        order = ["autoSaveInitFile"]
        lines = []
        existing = []
        try:
            text, _ = textenc.read_text(fn)
            existing = text.split("\n")
        except OSError:
            pass
        written = set()
        for line in existing:
            line = line.rstrip("\r")
            m = re.match(r"^([^=]+)=(.*)$", line)
            if m and m.group(1).strip() in self.sysini:
                k = m.group(1).strip()
                lines.append("%s=%s" % (k, self.sysini[k]))
                written.add(k)
            elif line.strip() != "" or lines:
                lines.append(line)
        for k in order + sorted(self.sysini.keys()):
            if k not in written:
                lines.append("%s=%s" % (k, self.sysini[k]))
                written.add(k)
        while lines and lines[-1] == "":
            lines.pop()
        try:
            textenc.write_text(fn, "\n".join(lines) + "\n", "utf-8", None)
        except OSError:
            pass

    def ini(self, key, default=""):
        return self.sysini.get(key, default)

    def set_ini(self, key, value):
        self.sysini[key] = str(value)
        self.writeSysIniFile()

    def fix(self, fid):
        val = self.sysini.get("fix." + fid)
        if val is None:
            return fixes.DEFAULTS.get(fid, False)
        return val.strip() in ("1", "true", "yes", "on")

    # encodings -----------------------------------------------------------

    def enc_read(self):
        return self.ini("enc.read", textenc.AUTO)

    def enc_out(self, kind):
        dflt = {"oto": "cp932", "comment": "cp932", "reclist": "same", "init": "cp932"}
        return self.ini("enc." + kind, dflt.get(kind, "cp932"))

    def enc_fallback(self):
        fb = self.ini("enc.fallback", "utf-8-sig")
        return None if fb in ("", "none") else fb

    def read_textfile(self, path, enc=None):
        text, used = textenc.read_text(path, enc or self.enc_read())
        self.read_encoding[os.path.normcase(os.path.abspath(path))] = used
        return text

    def write_textfile(self, path, text, kind, same_as=None):
        enc = self.enc_out(kind)
        if enc == "same":
            enc = self.read_encoding.get(os.path.normcase(os.path.abspath(same_as or path)),
                                         "cp932")
            if enc in ("ascii",):
                enc = "cp932"
        used = textenc.write_text(path, text, enc, self.enc_fallback())
        return used

    # ------------------------------------------------------------------
    # messages

    def _load_messages(self):
        lang = self.ini("lang", "")
        if not lang:
            lang = self._guess_lang()
        self.lang = lang
        base = self.topdir + "/message"
        files = []
        for lg in ["ja", lang] if lang != "ja" else ["ja"]:
            if lg == "custom":
                files += [base + "/oremo-text.tcl", base + "/proc-text.tcl"]
                continue
            for name in ("oremo-text.tcl", "proc-text.tcl", "oremo-ext-text.tcl"):
                files.append("%s/%s/%s" % (base, lg, name))
        found = False
        for fn in files:
            if os.path.exists(fn):
                found = True
                try:
                    text, _ = textenc.read_text(fn)
                except OSError:
                    continue
                for arr, key, value in tclfmt.parse_set_file(text):
                    if arr == "t" and key is not None:
                        self.t[key] = value
        if not found:
            messagebox.showerror("Error", "can not find textFile (%s)" % files[0])
            sys.exit(1)

    def _guess_lang(self):
        try:
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
            if lid == 0x04:
                return "zh_CN"
            if lid == 0x11:
                return "ja"
        except Exception:
            pass
        import locale
        loc = (locale.getdefaultlocale()[0] or "").lower()
        if loc.startswith("zh"):
            return "zh_CN"
        if loc.startswith("ja"):
            return "ja"
        return "en"

    def tt(self, key, default=None):
        if self.t.exists(key):
            return self.t[key]
        return default if default is not None else key

    def msg(self, key, **ctx):
        """eval format $t(key) replacement."""
        s = tclfmt.strip_outer_quotes(self.tt(key))
        c = dict(self.arrays)
        c["t"] = self.t
        c["paDev"] = self.paDev
        c.update(ctx)
        return tclfmt.substitute(s, c)

    # ------------------------------------------------------------------
    # error reporting (Tcl bgerror)

    def _bgerror(self, exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        self.log(text)
        try:
            messagebox.showerror("Error", "%s\n\n%s" % (val, text[-1500:]), parent=self.root)
        except Exception:
            pass

    def log(self, text):
        self.log_lines.append(text)
        del self.log_lines[:-500]
        try:
            sys.stderr.write(text + "\n")
        except Exception:
            pass
        if self.console_win is not None and self.console_win.winfo_exists():
            self.console_win.text.insert("end", text + "\n")
            self.console_win.text.see("end")

    def _poll_audio_queue(self):
        try:
            while True:
                fn, args = audio.ui_queue.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    self._bgerror(*sys.exc_info())
        except Exception:
            pass
        self.root.after(15, self._poll_audio_queue)

    def _set_icon(self):
        ico = os.path.join(self.topdir, "oremo.ico")
        if os.path.exists(ico):
            try:
                self.root.iconbitmap(default=ico)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # widgets

    def w(self, path):
        return self.root.nametowidget(path)

    def _build_menus(self):
        t = self.tt
        mb = tk.Menu(self.root, name="menubar")
        self.root.configure(menu=mb)
        self.menubar = mb

        def pane(label):
            m = tk.Menu(mb, tearoff=0)
            mb.add_cascade(label=label, menu=m)
            return m

        m = pane(t("file"))
        m.add_command(label=t("file,choosesaveDir"), command=lambda: (self.choosesaveDir(), self.resetDisplay()))
        m.add_command(label=t("file,readRecList"), command=lambda: (self.readRecList(), self.resetDisplay()))
        m.add_command(label=t("file,saveRecList"), command=self.saveRecList)
        m.add_command(label=t("file,readTypeList"), command=lambda: (self.readTypeList(), self.resetDisplay()))
        m.add_command(label=t("file,readCommentList"), command=lambda: self.readCommentList())

        def mk():
            self.makeRecListFromDir()
            self.resetDisplay()
            self.v["msg"] = t("file,makeRecList,msg")
        m.add_command(label=t("file,makeRecList"), command=mk)

        def mku():
            self.makeRecListFromUst()
            self.resetDisplay()
            self.v["msg"] = t("file,makeRecListFromUst,msg")
        m.add_command(label=t("file,makeRecListFromUst"), command=mku)
        m.add_command(label=t("file,saveSettings"), command=lambda: self.saveSettings())
        m.add_command(label=t("file,Exit"), command=self.Exit)

        m = pane(t("show"))
        m.add_checkbutton(label=t("show,showWave"), variable="v(showWave)", command=self.toggleWave)
        m.add_checkbutton(label=t("show,showSpec"), variable="v(showSpec)", command=self.toggleSpec)
        m.add_checkbutton(label=t("show,showpow"), variable="v(showpow)", command=self.togglePow)
        m.add_checkbutton(label=t("show,showf0"), variable="v(showf0)", command=self.toggleF0)
        m.add_command(label=t("show,pitchGuide"), command=self.pitchGuide)
        m.add_command(label=t("show,tempoGuide"), command=self.tempoGuide)

        m = pane(t("option"))
        m.add_checkbutton(label=t("option,removeDC"), variable="v(removeDC)")
        m.add_command(label=t("option,bgmGuide"), command=self.bgmGuide)
        m.add_command(label=t("option,ioSettings"), command=self.ioSettings)
        m.add_command(label=t("option,setBind"), command=self.setBind)
        m.add_command(label=t("option,setFontSize"), command=self.setFontSize)
        m.add_command(label=t("option,settings"), command=self.settings)

        m = pane(t("oto"))
        sub = tk.Menu(m, tearoff=0)
        m.add_cascade(label=t("oto,auto"), menu=sub)
        sub.add_command(label=t("oto,auto,tandoku"),
                        command=lambda: self.checkWavForOREMO() is not False and self.estimateParam())
        sub.add_command(label=t("oto,auto,renzoku"),
                        command=lambda: self.checkWavForOREMO() is not False and self.genParam())

        # --- added in the Unicode edition -------------------------------
        m = pane(t("tool", "Tools"))
        self.build_tools_menu(m)

        m = pane(t("help"))
        m.add_command(label=t("help,onlineHelp"),
                      command=lambda: self.execExternal("http://nwp8861.web.fc2.com/soft/oremo/manual/tutorial.html"))
        m.add_command(label=t("help,Version"), command=self.Version)
        m.add_command(label=t("help,official1"),
                      command=lambda: self.execExternal("http://nwp8861.web.fc2.com/soft/oremo/"))
        m.add_command(label=t("help,official2"),
                      command=lambda: self.execExternal("http://osdn.jp/users/nwp8861/pf/OREMO/files/"))
        self.rclickMenu = tk.Menu(self.root, name="popmenu", tearoff=0)

    def _build_main_window(self):
        root = self.root
        v = self.v
        self.icons = snackui.create_icons(root, self.S)
        rseq = 0

        # 0. current item
        fr = tk.Frame(root, name="recinfo")
        fr.grid(row=rseq, columnspan=2, sticky="new")
        sc = tk.Frame(fr, name="showCurrent")
        sc.grid(sticky="nw")
        lr = tk.Label(sc, name="lr", textvariable="v(recLab)", font="bigkfont", fg="black", bg="white")
        lt = tk.Label(sc, name="lt", textvariable="v(typeLab)", font="bigkfont", fg="black", bg="white")
        lr.pack(side="left", fill="x", expand=1, anchor="center")
        lt.pack(side="left", fill="x", expand=1, anchor="center")

        # comment
        rseq += 1
        fc = tk.Frame(root, name="recComment")
        fc.grid(row=rseq, columnspan=2, sticky="new")
        ce = tk.Entry(fc, name="l", textvariable="v(recComment)", font="commkfont", fg="black",
                      bg=root.cget("bg"))
        cb = tk.Button(fc, name="b", text=self.tt(".recComment.midashi"), command=self.searchComment)
        ce.pack(side="left", fill="both", expand=1, anchor="center", ipady=0)
        cb.pack(side="left", anchor="center", ipady=0)
        self.commentEntry = ce

        def edit_comment(e):
            ce.insert("insert", e.char)
            return "break"
        ce.bind("<<EditComment>>", edit_comment)

        # 1. list boxes
        rseq += 1
        fs = tk.Frame(root, name="s")
        fs.grid(row=rseq, column=0, sticky="nw")
        fl = tk.Frame(fs, name="listboxes")
        fl.grid(sticky="nw")
        self.rec = tk.Listbox(fl, name="rec", listvariable="v(recList)", height=10, width=5,
                              bg=v["bg"], fg=v["fg"], font="kfont", selectmode="single",
                              exportselection=0)
        self.srec = tk.Scrollbar(fl, name="srec", command=self.rec.yview)
        self.rec.configure(yscrollcommand=self.srec.set)
        self.rec.pack(side="left", fill="both", expand=1)
        self.srec.pack(side="left", fill="both", expand=1)
        self.rec.selection_set(v.i("recSeq"))
        self.type = tk.Listbox(fl, name="type", listvariable="v(typeList)", height=10, width=4,
                               bg=v["bg"], fg=v["fg"], font="kfont", selectmode="single",
                               exportselection=0)
        self.stype = tk.Scrollbar(fl, name="stype", command=self.type.yview)
        self.type.configure(yscrollcommand=self.stype.set)
        self.type.pack(side="left", fill="both", expand=1)
        self.stype.pack(side="left", fill="both", expand=1)
        self.type.selection_set(v.i("typeSeq"))

        # 2. figures
        ffig = tk.Frame(root, name="fig")
        ffig.grid(row=rseq, column=1, sticky="nw")
        root.update()
        v["cWidth"] = v.i("winWidth") - fs.winfo_width() - v.i("yaxisw") - 8
        if v.i("cWidth") < v.i("cWidthMin"):
            v["cWidth"] = v.i("cWidthMin")
        v["cHeight"] = v.i("waveh") + v.i("spech") + v.i("powh") + v.i("f0h") + v.i("timeh")
        self.c = tk.Canvas(ffig, name="c", width=v.i("cWidth"), height=v.i("cHeight"), bg=v["bg"])
        self.cYaxis = tk.Canvas(ffig, name="cYaxis", width=v.i("yaxisw"), height=v.i("cHeight"), bg=v["bg"])
        self.c.grid(row=0, column=1, sticky="nw")
        self.cYaxis.grid(row=0, column=0, sticky="nw")

        # 3. save folder
        rseq += 1
        fd = tk.Frame(root, name="saveDir")
        fd.grid(row=rseq, columnspan=2, sticky="new")
        tk.Label(fd, name="midashi", text=self.tt(".saveDir.midashi"), fg=v["fg"], bg=v["bg"]).pack(side="left")
        # width=1: a long path must not widen the window (it would push the canvas right)
        tk.Button(fd, name="dir", textvariable="v(saveDir)", fg=v["fg"], bg=v["bg"], relief="solid", width=1,
                  command=lambda: (self.choosesaveDir(), self.resetDisplay())).pack(side="left", fill="x", expand=1)
        tk.Button(fd, name="sel", image=self.icons["snackOpen"], highlightthickness=0, bg=v["bg"],
                  command=lambda: (self.choosesaveDir(), self.resetDisplay())).pack(side="left")

        # 4. message
        rseq += 1
        fm = tk.Frame(root, name="msg")
        fm.grid(row=rseq, columnspan=2, sticky="new")
        self.msgLabel = tk.Label(fm, name="msg", textvariable="v(msg)", relief="sunken", anchor="nw", width=1)
        self.msgLabel.pack(fill="x")

        # windows
        self.swindow = ".settings"
        self.cmwindow = ".changeMode"
        self.epwindow = ".epwindow"
        self.entpwindow = ".entpwindow"
        self.genWindow = ".genParam"
        self.prgWindow = ".progress"
        self.searchWindow = ".search"
        self.bindWindow = ".bindWindow"
        self.fontWindow = ".fontWindow"
        self.ioswindow = ".iosettings"

    # ------------------------------------------------------------------
    # key / mouse bindings

    def nextRec0(self, *a):
        self.nextRec(0)

    def prevRec0(self, *a):
        self.prevRec(0)

    def nextType0(self, *a):
        self.nextType(0)

    def prevType0(self, *a):
        self.prevType(0)

    def waveReload(self, *a):
        self.readWavFile()
        self.Redraw("all")

    def waveShrink(self, *a):
        self.changeWidth(0)

    def waveExpand(self, *a):
        self.changeWidth(1)

    def _bind(self, seq, func):
        self.root.bind(seq, lambda e: func())

    def setDefaultKeyBind(self):
        b = self._bind
        b("<KeyPress-r>", self.recStart)
        b("<KeyPress-0>", self.recStart)
        b("<KeyPress-R>", self.autoRecStop)
        b("<KeyRelease-r>", self.recStop)
        b("<KeyRelease-0>", self.recStop)
        b("<KeyPress-2>", self.nextRec)
        b("<KeyPress-8>", self.prevRec)
        b("<KeyPress-6>", self.nextType)
        b("<KeyPress-4>", self.prevType)
        b("<Control-KeyPress-2>", self.nextRec0)
        b("<Control-KeyPress-8>", self.prevRec0)
        b("<Control-KeyPress-6>", self.nextType0)
        b("<Control-KeyPress-4>", self.prevType0)
        b("<space>", self.togglePlay)
        b("<Control-p>", self.togglePlay)
        b("<KeyPress-5>", self.togglePlay)
        b("<KeyPress-o>", self.toggleOnsaPlay)
        b("<KeyPress-O>", self.toggleOnsaPlay)
        b("<KeyPress-c>", self.waveReload)
        b("<KeyPress-m>", self.toggleMetroPlay)
        b("<KeyPress-M>", self.toggleMetroPlay)
        b("<KeyPress-F6>", self.nextRec)
        b("<KeyPress-F7>", self.prevRec)
        b("<Control-KeyPress-F6>", self.nextRec0)
        b("<Control-KeyPress-F7>", self.prevRec0)
        b("<Alt-F4>", self.Exit)
        b("<F11>", self.waveShrink)
        b("<F12>", self.waveExpand)
        b("<Control-f>", self.searchComment)
        b("<Control-Alt-d>", self.toggleConsole)

        ce = ".recComment.l"

        def guard(func):
            def h(e):
                if str(e.widget) != ce:
                    func()
            return h
        self.root.bind("<Down>", guard(self.nextRec))
        self.root.bind("<Up>", guard(self.prevRec))
        self.root.bind("<Right>", guard(self.nextType))
        self.root.bind("<Left>", guard(self.prevType))
        self.root.bind("<Control-Down>", guard(self.nextRec0))
        self.root.bind("<Control-Up>", guard(self.prevRec0))
        self.root.bind("<Control-Right>", guard(self.nextType0))
        self.root.bind("<Control-Left>", guard(self.prevType0))

    def _bind_keys(self):
        root = self.root
        self.setDefaultKeyBind()
        root.event_add("<<EditComment>>", "<KeyPress-r>", "<KeyPress-0>", "<KeyPress-R>")
        root.event_add("<<EditComment>>", "<KeyPress-2>", "<KeyPress-4>", "<KeyPress-6>", "<KeyPress-8>")
        root.event_add("<<EditComment>>", "<Control-KeyPress-2>", "<Control-KeyPress-4>",
                       "<Control-KeyPress-6>", "<Control-KeyPress-8>")
        root.event_add("<<EditComment>>", "<space>", "<KeyPress-5>")
        root.event_add("<<EditComment>>", "<KeyPress-o>", "<KeyPress-O>", "<KeyPress-c>",
                       "<KeyPress-m>", "<KeyPress-M>")

        rec, typ = self.rec, self.type
        rec.bind("<<ListboxSelect>>", lambda e: self._list_select(rec, self.jumpRec))
        typ.bind("<<ListboxSelect>>", lambda e: self._list_select(typ, self.jumpType))
        rec.bind("<Control-1>", lambda e: self.jumpRec(rec.nearest(e.y), 0))
        typ.bind("<Control-1>", lambda e: self.jumpType(typ.nearest(e.y), 0))

        root.bind("<Button-1>", lambda e: self._focus(e.widget))

        def setsw(val):
            def h(e):
                self.scrollWidget = val(e)
            return h
        rec.bind("<Enter>", setsw(lambda e: str(e.widget)), add="+")
        rec.bind("<Leave>", setsw(lambda e: ""), add="+")
        self.srec.bind("<Enter>", setsw(lambda e: str(rec)), add="+")
        self.srec.bind("<Leave>", setsw(lambda e: ""), add="+")
        typ.bind("<Enter>", setsw(lambda e: str(e.widget)), add="+")
        typ.bind("<Leave>", setsw(lambda e: ""), add="+")
        self.stype.bind("<Enter>", setsw(lambda e: str(typ)), add="+")
        self.stype.bind("<Leave>", setsw(lambda e: ""), add="+")
        root.bind("<MouseWheel>", lambda e: self.listboxScroll(self.scrollWidget, e.delta))

        root.bind("<Control-MouseWheel>", self._ctrl_wheel)
        rec.bind("<Control-MouseWheel>", self._rec_ctrl_wheel)
        typ.bind("<Control-MouseWheel>", self._type_ctrl_wheel)
        root.bind("<Shift-MouseWheel>", self._shift_wheel)
        self.c.bind("<Button-3>", lambda e: self.PopUpMenu(e.x_root, e.y_root, e.x, e.y))
        self._bind_panel_drag()
        self._bind_list_drag()

        self.doSetBind()

    # ------------------------------------------------------------------
    # free width of the reclist / type list: drag the right edge of a list
    # (added in the Unicode edition; the original only offered Ctrl+wheel)

    def _bind_list_drag(self):
        self._ldrag = None
        self._ldrag_pending = False
        for lb in (self.rec, self.type):
            lb.bind("<Motion>", lambda e, lb=lb: self._list_motion(lb, e), add="+")
            lb.bind("<Leave>", lambda e, lb=lb: None if self._ldrag else lb.configure(cursor=""), add="+")
            lb.bind("<ButtonPress-1>", lambda e, lb=lb: self._list_press(lb, e))
            lb.bind("<B1-Motion>", lambda e, lb=lb: self._list_drag(lb, e))
            lb.bind("<ButtonRelease-1>", lambda e, lb=lb: self._list_release(lb, e))

    def _on_list_edge(self, lb, x):
        return x >= lb.winfo_width() - max(5, int(round(6 * self.S)))

    def _list_motion(self, lb, e):
        if self._ldrag is None:
            lb.configure(cursor="sb_h_double_arrow" if self._on_list_edge(lb, e.x) else "")

    def _list_press(self, lb, e):
        if self._on_list_edge(lb, e.x):
            px = max(1, self._fonts["kfont"].measure("0"))
            self._ldrag = (lb, e.x_root, int(lb.cget("width")), px)
            return "break"          # do not select an item
        return None

    def _list_drag(self, lb, e):
        if self._ldrag is None:
            return None
        lbw, x0, w0, px = self._ldrag
        new = max(2, w0 + int(round((e.x_root - x0) / float(px))))
        if new != int(lbw.cget("width")):
            lbw.configure(width=new)
            if not self._ldrag_pending:
                self._ldrag_pending = True
                self.root.after(40, self._list_apply)
        return "break"

    def _list_release(self, lb, e):
        if self._ldrag is None:
            return None
        self._ldrag = None
        self._list_apply()
        lb.configure(cursor="")
        return "break"

    def _list_apply(self):
        """Same window handling as changeRecListWidth (Ctrl+wheel)."""
        self._ldrag_pending = False
        v = self.v
        v["skipChangeWindowBorder"] = 1
        self.root.update_idletasks()
        v["skipChangeWindowBorder"] = 0
        fig = self.w(".fig")
        w = self.w(".s").winfo_reqwidth() + fig.winfo_width()
        self.root.geometry("%dx%d" % (w, v.i("winHeight")))
        self.changeWindowBorder()
        v["winWidthMin"] = self.w(".s").winfo_reqwidth() + v.i("cWidthMin")
        self.root.minsize(v.i("winWidthMin"), v.i("winHeightMin"))

    # ------------------------------------------------------------------
    # independent panel sizes: drag the bottom border of the waveform /
    # spectrogram / power / F0 panel (added in the Unicode edition; the
    # original only offered Shift+wheel)

    PANELS = (("waveh", "wavehmin"), ("spech", "spechmin"), ("powh", "powhmin"), ("f0h", "f0hmin"))

    def _panel_border_at(self, cy):
        y = 0
        for key, mn in self.PANELS:
            h = self.v.i(key)
            if h <= 0:
                continue
            y += h
            if abs(cy - y) <= 4 * self.S:
                return key, mn
        return None

    def _bind_panel_drag(self):
        self._drag = None
        self._drag_pending = False
        for cv in (self.c, self.cYaxis):
            cv.bind("<Motion>", lambda e, cv=cv: self._panel_motion(cv, e), add="+")
            cv.bind("<Leave>", lambda e, cv=cv: None if self._drag else cv.configure(cursor=""), add="+")
            cv.bind("<ButtonPress-1>", lambda e, cv=cv: self._panel_press(cv, e), add="+")
            cv.bind("<B1-Motion>", lambda e, cv=cv: self._panel_drag(cv, e), add="+")
            cv.bind("<ButtonRelease-1>", lambda e, cv=cv: self._panel_release(cv, e), add="+")

    def _panel_motion(self, cv, e):
        if self._drag:
            return
        hit = self._panel_border_at(cv.canvasy(e.y))
        cv.configure(cursor="sb_v_double_arrow" if hit else "")

    def _panel_press(self, cv, e):
        hit = self._panel_border_at(cv.canvasy(e.y))
        if hit:
            self._drag = (hit[0], hit[1], e.y_root, self.v.i(hit[0]))

    def _panel_drag(self, cv, e):
        if not self._drag:
            return
        key, mn, y0, h0 = self._drag
        new = max(h0 + (e.y_root - y0), self.v.i(mn))
        if new != self.v.i(key):
            self.v[key] = new
            if not self._drag_pending:
                self._drag_pending = True
                self.root.after(30, self._panel_apply)

    def _panel_release(self, cv, e):
        if self._drag:
            self._drag = None
            self._panel_apply()
            cv.configure(cursor="")

    def _panel_apply(self):
        """Redraw and grow/shrink the window so the other panels keep their size."""
        self._drag_pending = False
        v = self.v
        self.Redraw("scale")
        h = lambda p: self.w(p).winfo_height()
        hh = (self.w(".fig").winfo_y() + v.i("waveh") + v.i("spech") + v.i("powh") + v.i("f0h")
              + v.i("timeh") + h(".saveDir") + h(".msg") + 4)
        self.root.geometry("%dx%d" % (v.i("winWidth"), hh))

    def _focus(self, widget):
        try:
            widget.focus_set()
        except Exception:
            pass

    def _list_select(self, lb, jump):
        sel = lb.curselection()
        if sel:
            jump(int(sel[0]))
        elif not self.fix("F01"):
            # original: "jumpRec {}" -> Tcl error
            raise ValueError('expected integer but got ""')

    def _ctrl_wheel(self, e):
        root = self.root
        x = e.x + e.widget.winfo_rootx() - root.winfo_rootx()
        y = e.y + e.widget.winfo_rooty() - root.winfo_rooty()
        s = self.w(".s")
        if y > s.winfo_y():
            if x > s.winfo_width():
                self.changeWidth(0 if e.delta > 0 else 1)
            elif x <= self.rec.winfo_width():
                self.changeRecListWidth(0 if e.delta > 0 else 1)
            else:
                self.changeTypeListWidth(0 if e.delta > 0 else 1)

    def _rec_ctrl_wheel(self, e):
        if e.y > self.w(".recinfo").winfo_height() + self.w(".recComment").winfo_height():
            if e.x <= self.rec.winfo_width():
                self.changeRecListWidth(0 if e.delta > 0 else 1)

    def _type_ctrl_wheel(self, e):
        if e.y > self.w(".recinfo").winfo_height() + self.w(".recComment").winfo_height():
            if self.rec.winfo_width() < e.x <= self.type.winfo_width():
                self.changeTypeListWidth(0 if e.delta > 0 else 1)

    def _shift_wheel(self, e):
        v = self.v
        W = str(e.widget)
        h = lambda p: self.w(p).winfo_height()
        wd = lambda p: self.w(p).winfo_width()
        if W == ".":
            mx, my = e.x, e.y - h(".recinfo") - h(".recComment")
        elif W.startswith(".recinfo"):
            mx, my = e.x, e.y - h(".recinfo") - h(".recComment")
        elif W.startswith(".recComment"):
            mx, my = e.x, e.y - h(".recComment")
        elif W.startswith(".fig.cYaxis"):
            mx, my = e.x + wd(".s"), e.y
        elif W.startswith(".fig.c"):
            mx, my = e.x + wd(".s") + wd(".fig.cYaxis"), e.y
        elif W == ".s.listboxes.rec":
            mx, my = e.x, e.y
        elif W == ".s.listboxes.srec":
            mx, my = e.x + wd(".s.listboxes.rec"), e.y
        elif W == ".s.listboxes.type":
            mx, my = e.x + wd(".s.listboxes.rec") + wd(".s.listboxes.srec"), e.y
        elif W.startswith(".s."):
            mx = e.x + wd(".s.listboxes.rec") + wd(".s.listboxes.srec") + wd(".s.listboxes.type")
            my = e.y
        elif W.startswith(".saveDir"):
            mx, my = e.x, e.y + h(".fig")
        elif W.startswith(".msg"):
            mx, my = e.x, e.y + h(".fig") + h(".saveDir")
        else:
            return
        if my < 0:
            return
        if mx > wd(".s"):
            step = int(round(20 * self.S))
            inc = -step if e.delta > 0 else step
            if my <= v.i("waveh"):
                v["waveh"] = max(v.i("waveh") + inc, v.i("wavehmin"))
            elif my <= v.i("waveh") + v.i("spech"):
                v["spech"] = max(v.i("spech") + inc, v.i("spechmin"))
            elif my <= v.i("waveh") + v.i("spech") + v.i("powh"):
                v["powh"] = max(v.i("powh") + inc, v.i("powhmin"))
            elif my <= v.i("waveh") + v.i("spech") + v.i("powh") + v.i("f0h"):
                v["f0h"] = max(v.i("f0h") + inc, v.i("f0hmin"))
            self.Redraw("scale")
            hh = (self.w(".fig").winfo_y() + v.i("waveh") + v.i("spech") + v.i("powh") + v.i("f0h")
                  + v.i("timeh") + h(".saveDir") + h(".msg") + 4)
            self.root.geometry("%dx%d" % (v.i("winWidth"), hh))

    # ------------------------------------------------------------------
    # display reset

    def recList(self):
        return self.v.lst("recList")

    def typeList(self):
        return self.v.lst("typeList")

    def _sync_cache(self):
        self._rec_seq_cache = self.v.i("recSeq")
        self._rec_len_cache = len(self.recList())

    def _comment_key(self):
        return self.v["recLab"] + self.v["typeLab"]

    def _load_current_comment(self):
        self.v["recComment"] = self.comments.get(self._comment_key(), "")

    def resetDisplay(self):
        v = self.v
        v["recSeq"] = 0
        v["typeSeq"] = 0
        v["listSeq"] = 1
        rl, tl = self.recList(), self.typeList()
        v["recLab"] = rl[0] if rl else ""
        v["typeLab"] = tl[0] if tl else ""
        self._load_current_comment()
        self.updateFontFamily()
        if hasattr(self, "rec"):
            self.rec.selection_clear(0, "end")
            self.type.selection_clear(0, "end")
            self.rec.selection_set(0)
            self.type.selection_set(0)
            self.rec.activate(0)
            self.type.activate(0)
        self._sync_cache()
        self.readWavFile()
        if hasattr(self, "c"):
            self.Redraw("all")

    # ------------------------------------------------------------------
    # lists

    def makeRecListFromDir(self, readParam=0, overWriteRecList=1):
        v = self.v
        recList = []
        d = v["saveDir"]
        ext = "." + v["ext"].lower()
        try:
            names = os.listdir(d)
        except OSError:
            names = []
        for fn in names:
            if not fn.lower().endswith(ext):
                continue
            if not os.path.isfile(os.path.join(d, fn)):
                continue
            base = fn[:-len(ext)]
            if base == "":
                continue
            recList.append(base)
        if overWriteRecList:
            v["recList"] = recList
            v["typeList"] = [""]
        self.initParamS()
        self.initParamU(0, recList)
        if readParam:
            pass  # setParam only
        return recList

    def saveRecList(self):
        v = self.v
        fn = filedialog.asksaveasfilename(initialfile=os.path.basename(v["recListFile"]),
                                          initialdir=os.path.dirname(v["recListFile"]),
                                          title=self.tt("saveRecList,title"), defaultextension="txt")
        if not fn:
            return
        old = v["recListFile"]
        v["recListFile"] = _fwd(fn)
        try:
            text = "".join(sn + "\n" for sn in self.recList())
            used = self.write_textfile(fn, text, "reclist", same_as=old)
            self.read_encoding[os.path.normcase(os.path.abspath(fn))] = used
        except OSError:
            messagebox.showwarning(self.tt(".confm.fioErr"), self.msg("saveRecList,errMsg"))
        v["msg"] = self.msg("saveRecList,doneMsg")

    def saveCommentList(self):
        v = self.v
        if not os.path.exists(v["saveDir"]):
            return
        self.comments[self._comment_key()] = v["recComment"]
        fn = "%s/%s-comment.txt" % (v["saveDir"], v["appname"])
        lines = []
        for sn in self.recList():
            for tn in self.typeList():
                c = self.comments.get(sn + tn)
                if c is None or re.match(r"^\s*$", c):
                    continue
                lines.append("%s\t%s\n" % (sn + tn, c))
        if not lines:
            if os.path.exists(fn):
                try:
                    os.remove(fn)
                except OSError:
                    pass
            return
        try:
            self.write_textfile(fn, "".join(lines), "comment")
        except OSError:
            messagebox.showwarning(self.tt(".confm.fioErr"), self.msg("saveCommentList,errMsg"))

    def readCommentList(self, fname=""):
        v = self.v
        if not self.fix("F14") or fname != "":
            self.comments = {}
        if fname == "":
            fname = filedialog.askopenfilename(title=self.tt("file,readCommentList"),
                                               defaultextension="txt",
                                               filetypes=[("txt file", ".txt"), ("All Files", "*")])
            if not fname:
                return
            if self.fix("F14"):
                self.comments = {}
        if not os.path.exists(fname):
            return
        v["recComment"] = ""
        try:
            data = self.read_textfile(fname)
        except OSError:
            messagebox.showwarning(self.tt(".confm.fioErr"), self.msg("readCommentList,errMsg"))
            return
        commNum = 0
        ignoreNum = 0
        lines = data.split("\n")
        keyList = self.isSetparamComment(fname, len(lines))
        if keyList:
            for i, comm in enumerate(lines):
                comm = comm.rstrip("\r")
                key = keyList[i] if i < len(keyList) else ""
                if key != "" and comm != "":
                    if key in self.comments:
                        ignoreNum += 1
                    self.comments[key] = comm
                    commNum += 1
        else:
            for line in lines:
                line = line.rstrip("\r")
                if line != "" and not re.match(r"^ *#", line):
                    line = re.sub(r"^\s+", "", line)
                    m = re.match(r"^([^\s:]+)[\s:](.+)$", line)
                    if m:
                        key, comm = m.group(1), m.group(2)
                        if key in self.comments:
                            ignoreNum += 1
                        self.comments[key] = comm
                        commNum += 1
        if self._comment_key() in self.comments:
            v["recComment"] = self.comments[self._comment_key()]
        if ignoreNum > 0:
            v["msg"] = self.msg("readCommentList,doneMsg2", commNum=commNum, ignoreNum=ignoreNum)
        else:
            v["msg"] = self.msg("readCommentList,doneMsg", commNum=commNum, ignoreNum=ignoreNum)

    def isSetparamComment(self, fname, lineNum):
        iniFile = re.sub(r"(?i)-comment\.txt$", ".ini", fname)
        if iniFile == fname or not os.path.exists(iniFile):
            return []
        try:
            iniData = self.read_textfile(iniFile)
        except OSError:
            return []
        if len(iniData.split("\n")) != lineNum:
            return []
        act = self.tk_dialog(".confm", self.tt(".confm"),
                             self.msg("isSetparamComment,q", iniFile=os.path.basename(iniFile)),
                             "question", 1, self.tt(".confm.r"), self.tt(".confm.nr"))
        if act != 0:
            return []
        keyList = []
        ext = "." + self.v["ext"]
        for line in iniData.split("\n"):
            p = re.split(r"[=,]", line.rstrip("\r"))
            if len(p) == 7:
                wav = p[0]
                idx = wav.find(ext)
                keyList.append(wav[:idx] if idx >= 0 else wav[:-1])
            else:
                keyList.append("")
        return keyList

    def _split_list_text(self, data):
        return [x for x in re.split(r"\s", data) if x != ""]

    def readRecList(self, fn=None):
        v = self.v
        if fn is None or not os.path.exists(v["recListFile"]):
            fn = filedialog.askopenfilename(initialfile=os.path.basename(v["recListFile"]),
                                            initialdir=os.path.dirname(v["recListFile"]),
                                            title=self.tt("readRecList,title1"), defaultextension="txt",
                                            filetypes=[("reclist file", ".txt"), ("All Files", "*")])
        if not fn:
            return
        v["recListFile"] = _fwd(fn)
        try:
            data = self.read_textfile(fn)
        except OSError:
            messagebox.showwarning(self.tt(".confm.fioErr"), self.msg("readRecList,errMsg"))
        else:
            v["recList"] = self._split_list_text(data)
            commentFile, n = re.subn(r"(?i)\.txt$", "-comment.txt", v["recListFile"])
            if n > 0:
                saveDirCommentFile = "%s/%s-comment.txt" % (v["saveDir"], v["appname"])
                if os.path.exists(commentFile):
                    if not os.path.exists(saveDirCommentFile):
                        self.readCommentList(commentFile)
                    else:
                        act = self.tk_dialog(".confm", self.tt(".confm"), self.tt("readRecList,overwrite"),
                                             "question", 1, self.tt(".confm.r"), self.tt(".confm.nr"))
                        if act == 0:
                            self.readCommentList(commentFile)
        v["recSeq"] = 0
        rl = self.recList()
        v["recLab"] = rl[0] if rl else ""
        self._load_current_comment()
        v["msg"] = self.msg("readRecList,doneMsg")
        self._sync_cache()

    def readTypeList(self, fn=None):
        v = self.v
        if fn is None or not os.path.exists(v["typeListFile"]):
            fn = filedialog.askopenfilename(initialfile=os.path.basename(v["typeListFile"]),
                                            initialdir=os.path.dirname(v["typeListFile"]),
                                            title=self.tt("readTypeList,title"), defaultextension="txt",
                                            filetypes=[("typelist file", ".txt"), ("All Files", "*")])
        if not fn:
            return
        v["typeListFile"] = _fwd(fn)
        tl = [""]
        try:
            data = self.read_textfile(fn)
        except OSError:
            messagebox.showwarning(self.tt(".confm.fioErr"), self.msg("readTypeList,errMsg"))
        else:
            tl += self._split_list_text(data)
        v["typeList"] = tl
        v["typeSeq"] = 0
        v["typeLab"] = tl[0]
        self._load_current_comment()
        v["msg"] = self.msg("readTypeList,doneMsg")

    def makeRecListFromUst(self, fn=None):
        v = self.v
        if fn is None or not os.path.exists(v["recListFile"]):
            fn = filedialog.askopenfilename(initialdir=os.path.dirname(v["recListFile"]),
                                            title=self.tt("makeRecListFromUst,title1"),
                                            defaultextension="ust",
                                            filetypes=[("reclist file", ".ust"), ("All Files", "*")])
        if not fn:
            return
        v["recListFile"] = _fwd(os.path.splitext(fn)[0] + ".txt")
        try:
            data = self.read_textfile(fn)
        except OSError:
            messagebox.showwarning(self.tt(".confm.fioErr"), self.msg("makeRecListFromUst,errMsg"))
        else:
            rl = []
            for line in data.split("\n"):
                d = line.rstrip("\r").split("=")
                if len(d) > 1 and d[0] == "Lyric":
                    val = d[1]
                    if self.fix("F10") and (val.strip() == "" or val.strip() in ("R", "r")):
                        continue
                    if val not in rl:
                        rl.append(val)
            v["recList"] = rl
        v["recSeq"] = 0
        rl = self.recList()
        v["recLab"] = rl[0] if rl else ""
        self._load_current_comment()
        v["msg"] = self.msg("makeRecListFromUst,doneMsg")
        v["typeList"] = [""]
        self._sync_cache()

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # font selection
    #
    # Tk lists fonts under their localized names on Windows (e.g. "微软雅黑"
    # for "Microsoft YaHei"), and Japanese fonts such as MS Gothic have no
    # simplified Chinese glyphs: Windows then borrows missing characters from
    # other fonts one by one, which gives a mixed look.  The family is
    # therefore chosen by what Tk really resolves and by checking with GDI
    # that the font contains every character of the lists.

    FONT_CANDIDATES = {
        "zh_CN": ["Microsoft YaHei", "Microsoft YaHei UI", "DengXian", "SimHei", "SimSun", "宋体",
                  "Meiryo", "Yu Gothic", "MS Gothic", "Arial Unicode MS"],
        "ja": ["MS Gothic", "Meiryo", "Yu Gothic", "MS UI Gothic", "Microsoft YaHei",
               "Microsoft YaHei UI", "SimSun", "宋体", "Arial Unicode MS"],
    }

    def _font_resolve(self, name):
        """Family Tk actually uses for *name*, or None if it is not installed."""
        if not hasattr(self, "_font_cache"):
            self._font_cache = {}
            fams = set(tkfont.families(self.root))
            self._font_fams = fams
            self._font_missing = tkfont.Font(self.root, family="__no_such_font__").actual("family")
        if name in self._font_cache:
            return self._font_cache[name]
        actual = tkfont.Font(self.root, family=name).actual("family")
        ok = name in self._font_fams or (actual in self._font_fams and actual != self._font_missing)
        res = actual if ok else None
        self._font_cache[name] = res
        return res

    @staticmethod
    def _font_missing_chars(family, text):
        """Characters of *text* that the font does not contain (Windows GDI)."""
        chars = "".join(sorted(set(c for c in text if ord(c) > 0x7f and not c.isspace())))
        if not chars or sys.platform != "win32":
            return ""
        try:
            import ctypes
            from ctypes import wintypes
            gdi = ctypes.WinDLL("gdi32")    # private instance: own argtypes
            gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
            gdi.CreateCompatibleDC.restype = wintypes.HDC
            gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wintypes.DWORD] * 8 + [wintypes.LPCWSTR]
            gdi.CreateFontW.restype = wintypes.HFONT
            gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
            gdi.SelectObject.restype = wintypes.HGDIOBJ
            gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
            gdi.DeleteDC.argtypes = [wintypes.HDC]
            gdi.GetGlyphIndicesW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
                                             ctypes.POINTER(wintypes.WORD), wintypes.DWORD]
            gdi.GetGlyphIndicesW.restype = wintypes.DWORD
            chars = "".join(c for c in chars if ord(c) < 0x10000)   # BMP only (1 unit per char)
            n = len(chars)
            if n == 0:
                return ""
            hdc = gdi.CreateCompatibleDC(None)
            hf = gdi.CreateFontW(-20, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, family)
            old = gdi.SelectObject(hdc, hf)
            missing = ""
            try:
                buf = (wintypes.WORD * n)()
                if gdi.GetGlyphIndicesW(hdc, chars, n, buf, 1) != 0xFFFFFFFF:  # GGI_MARK_NONEXISTING_GLYPHS
                    missing = "".join(chars[i] for i in range(n) if buf[i] == 0xFFFF)
            finally:
                gdi.SelectObject(hdc, old)
                gdi.DeleteObject(hf)
                gdi.DeleteDC(hdc)
            return missing
        except Exception:
            return ""   # cannot check: assume the font is fine

    def font_choices(self):
        """Installed candidate families (display names as Tk resolves them)."""
        out = []
        for name in [self.tt("fontName", "")] + self.FONT_CANDIDATES["zh_CN"] + self.FONT_CANDIDATES["ja"]:
            r = self._font_resolve(name) if name else None
            if r and r not in out:
                out.append(r)
        return out

    def _list_text(self):
        v = self.v
        parts = self.v.lst("recList") + self.v.lst("typeList") + [v.get("recLab", ""), v.get("typeLab", "")]
        parts += list(self.comments.values())[:2000]
        return "".join(parts)

    def choose_font_family(self, text=""):
        override = self.ini("fontFamily", "")
        if override:
            r = self._font_resolve(override)
            if r:
                return r
        order = [self.tt("fontName", "")] + self.FONT_CANDIDATES.get(self.lang, self.FONT_CANDIDATES["ja"])
        first = None
        for name in order:
            r = self._font_resolve(name) if name else None
            if not r:
                continue
            if first is None:
                first = r
            if not self._font_missing_chars(r, text):
                return r
        return first or "TkDefaultFont"

    def updateFontFamily(self, force=False):
        """Re-check the list font when the lists change; switch if glyphs are missing."""
        if not getattr(self, "_fonts", None):
            return
        text = self._list_text()
        key = (hash(text), self.ini("fontFamily", ""))
        if not force and key == getattr(self, "_font_key", None):
            return
        self._font_key = key
        fam = self.choose_font_family(text)
        for f in self._fonts.values():
            if f.cget("family") != fam:
                f.configure(family=fam)

    def fontSetting(self):
        v = self.v
        family = self.choose_font_family(self._list_text())
        # keep references: a tkinter Font object deletes its named font when collected
        self._fonts = {}
        for name, key in (("bigkfont", "bigFontSize"), ("kfont", "fontSize"),
                          ("smallkfont", "smallFontSize"), ("commkfont", "commFontSize")):
            try:
                self._fonts[name] = tkfont.Font(self.root, name=name, family=family, size=v.i(key),
                                                weight="normal", slant="roman", exists=False)
            except tk.TclError:
                f = tkfont.Font(self.root, name=name, exists=True)
                f.configure(family=family, size=v.i(key))
                self._fonts[name] = f

    def execExternal(self, url):
        try:
            webbrowser.open(url)
        except Exception:
            try:
                os.startfile(url)
            except Exception:
                pass

    def choosesaveDir(self, readParam=0):
        v = self.v
        d = filedialog.askdirectory(initialdir=v["saveDir"], title=self.tt("choosesaveDir,title"))
        if d:
            self.saveCommentList()
            v["saveDir"] = _fwd(d)
            self.readCommentList("%s/%s-comment.txt" % (v["saveDir"], v["appname"]))
            v["msg"] = self.msg("choosesaveDir,doneMsg")
            self.resetDisplay()
            return 1
        return 0

    # ------------------------------------------------------------------
    # wav file I/O

    def current_wav_path(self):
        v = self.v
        return "%s/%s%s.wav" % (v["saveDir"], v["recLab"], v["typeLab"])

    def saveWavFile(self):
        v = self.v
        if v.i("recStatus"):
            if self.snd.length() > 0:
                if not os.path.exists(v["saveDir"]):
                    os.makedirs(v["saveDir"], exist_ok=True)
                fn = self.current_wav_path()
                name = v["recLab"] + v["typeLab"]
                bad = textenc.invalid_filename_chars(name)
                try:
                    if bad:
                        raise OSError('invalid character(s) %s in file name "%s.wav"' % (" ".join(bad), name))
                    self.snd.write(fn)
                except OSError as e:
                    messagebox.showwarning(self.tt(".confm.fioErr"), "%s\n%s" % (fn, e))
                    return
                v["msg"] = self.msg("saveWavFile,doneMsg")
                v["recStatus"] = 0

    def readWavFile(self):
        self.playStopAll()
        self.snd.flush()
        fn = self.current_wav_path()
        if os.path.isfile(fn) and os.access(fn, os.R_OK):
            try:
                self.snd.read(fn)
            except Exception as e:
                self.v["msg"] = "%s: %s" % (os.path.basename(fn), e)
                self.snd.flush()

    def playStopAll(self):
        if self.v.i("playStatus"):
            self.player.stop()
            self.v["playStatus"] = 0
            if self.paDev.i("usePlay"):
                self.v["msg"] = self.tt("togglePlay,stopMsg")
            self.showPlayBar(-1)

    # ------------------------------------------------------------------
    # tones

    def setSinScale(self):
        v = self.v
        scale, note = [], []
        for octv in range(v.i("sinScaleMin"), v.i("sinScaleMax") + 1):
            for i in range(12):
                scale.append(int(27.5 * math.pow(2, octv + (i - 9.0) / 12.0) + 0.5))
                note.append("%s%d" % (TONE_LIST[i], octv))
        v["sinScale"] = scale
        v["sinNote"] = note
        self._sinScale = scale
        self._sinNote = note

    def tone2freq(self, tone):
        notes = self._sinNote
        for i, n in enumerate(notes):
            if n == tone:
                return self._sinScale[i]
        return ""

    @staticmethod
    def hz2semitone(hz):
        return math.log(hz) / math.log(2) * 12.0

    def changeTone(self, chg):
        f0, v = self.f0, self.v
        tl = TONE_LIST
        cur = tl.index(f0["guideTone"]) if f0["guideTone"] in tl else 0
        nxt = cur + chg
        if nxt < 0:
            if f0.i("guideOctave") > v.i("sinScaleMin"):
                nxt += len(tl)
                f0["guideOctave"] = f0.i("guideOctave") - 1
            else:
                nxt = cur
        elif nxt >= len(tl):
            if f0.i("guideOctave") < v.i("sinScaleMax"):
                nxt %= len(tl)
                f0["guideOctave"] = f0.i("guideOctave") + 1
            else:
                nxt = cur
        f0["guideTone"] = tl[nxt]
        if v.i("playOnsaStatus"):
            self.toggleOnsaPlay()
            self.toggleOnsaPlay()

    # ------------------------------------------------------------------
    # output device helpers

    def _snack_device(self, kind):
        name = self.dev.get("in" if kind == "input" else "out", "")
        for d in audio.mme_devices(kind):
            if d[1] == name:
                return d[0]
        return None

    def _pa_device(self, kind):
        s = self.paDev.get("in" if kind == "input" else "out", "")
        m = re.match(r"^([0-9]+)", s)
        return int(m.group(1)) if m else None

    def out_device(self):
        if self.paDev.i("usePlay"):
            return self._pa_device("output"), 1.0, None, self.paDev.i("bufferSize") or 0
        gain = self.dev.f("outgain", 100.0) / 100.0
        lat = self.dev.f("latency", 0)
        return self._snack_device("output"), gain, (lat / 1000.0 if lat > 0 else None), 0

    def audio_busy(self):
        return (self.player.active() or self.bgm_player.active() or self.onsa_player.active()
                or self.sin_player.active() or self.metro_player.active() or self.auto_engine.active())

    def _play_error(self, e):
        messagebox.showwarning(self.tt(".confm.errTitle"), "%s\n%s" % (self.tt("setIODevice,errPa"), e))

    # ------------------------------------------------------------------
    # sin wave / tuning fork

    def playSin(self, freq, vol, length):
        v = self.v
        try:
            freq = float(freq)
            vol = float(vol)
        except (TypeError, ValueError):
            return
        if not self.fix("F11") and self.audio_busy():
            return
        if freq > 10 and vol > 0:
            dev, gain, _lat, _bs = self.out_device()
            rate = v.i("sampleRate")
            synth = dsp.OnsaSynth(freq, vol, rate, int(length))
            p = self.onsa_player if int(length) < 0 else self.sin_player
            try:
                p.play(synth, rate, device=dev, gain=gain)
            except audio.AudioError as e:
                self._play_error(e)

    def toggleOnsaPlay(self):
        v, f0 = self.v, self.f0
        if v.i("playOnsaStatus"):
            v["msg"] = self.tt("toggleOnsaPlay,stopMsg")
            self.onsa_player.stop()
            v["playOnsaStatus"] = 0
        else:
            v["msg"] = self.tt("toggleOnsaPlay,playMsg")
            v["playOnsaStatus"] = 1
            self.playSin(self.tone2freq(f0["guideTone"] + f0["guideOctave"]), f0["guideVol"], -1)

    # ------------------------------------------------------------------
    # navigation

    def prevRec(self, save=1):
        v = self.v
        n = len(self.recList())
        if n == 0 and self.fix("F01"):
            return
        tmp = v.i("recSeq") - 2
        if tmp >= 0:
            self.rec.see(tmp)
        if v.i("recSeq") > 0:
            seq = v.i("recSeq") - 1
        else:
            seq = n - 1
            self.rec.see(seq)
        self.jumpRec(seq, save)

    def nextRec(self, save=1):
        v = self.v
        n = len(self.recList())
        if n == 0:
            if self.fix("F01"):
                return
            raise ZeroDivisionError("can't use empty string as operand of \"%\"")
        tmp = v.i("recSeq") + 2
        if tmp < n:
            self.rec.see(tmp)
        self.jumpRec((v.i("recSeq") + 1) % n, save)

    def jumpRec(self, index, save=1):
        v = self.v
        index = int(index)
        if v.i("recSeq") == index:
            return
        v["msg"] = ""
        if save:
            self.saveWavFile()
        self.rec.focus_set()
        self.rec.selection_clear(v.i("recSeq"))
        v["recSeq"] = index
        self.rec.see(index)
        self.rec.selection_set(index)
        self.rec.activate(index)
        self.comments[self._comment_key()] = v["recComment"]
        rl = self.recList()
        v["recLab"] = rl[index] if 0 <= index < len(rl) else ""
        self._load_current_comment()
        v["recStatus"] = 0
        self._sync_cache()
        self.readWavFile()
        self.Redraw("all")

    def prevType(self, save=1):
        v = self.v
        n = len(self.typeList())
        if v.i("typeSeq") > 0:
            seq = v.i("typeSeq") - 1
        else:
            seq = n - 1
        self.jumpType(seq, save)

    def nextType(self, save=1):
        v = self.v
        n = len(self.typeList())
        if n == 0:
            if self.fix("F01"):
                return
            raise ZeroDivisionError("empty type list")
        self.jumpType((v.i("typeSeq") + 1) % n, save)

    def jumpType(self, index, save=1):
        v = self.v
        index = int(index)
        if v.i("typeSeq") == index:
            return
        v["msg"] = ""
        if save:
            self.saveWavFile()
        self.type.focus_set()
        self.type.selection_clear(v.i("typeSeq"))
        v["typeSeq"] = index
        self.type.see(index)
        self.type.selection_set(index)
        self.type.activate(index)
        self.comments[self._comment_key()] = v["recComment"]
        tl = self.typeList()
        v["typeLab"] = tl[index] if 0 <= index < len(tl) else ""
        self._load_current_comment()
        v["recStatus"] = 0
        self.readWavFile()
        self.Redraw("all")

    # ------------------------------------------------------------------

    def removeDC(self):
        self.snd.data = dsp.remove_dc(self.snd.data)

    def changeWidth(self, mode):
        v = self.v
        if mode:
            v["cWidth"] = v.i("cWidth") + int(round(40 * self.S))
        elif v.i("cWidth") <= v.i("cWidthMin"):
            v["cWidth"] = v.i("cWidthMin")
        else:
            v["cWidth"] = v.i("cWidth") - int(round(40 * self.S))
        self.Redraw("scale")
        v["skipChangeWindowBorder"] = 1
        self.root.update()
        v["skipChangeWindowBorder"] = 0
        fig = self.w(".fig")
        w = fig.winfo_x() + fig.winfo_width()
        self.root.geometry("%dx%d" % (w, v.i("winHeight")))
        self.changeWindowBorder()

    def _change_list_width(self, lb, mode):
        v = self.v
        width = int(lb.cget("width"))
        if mode:
            lb.configure(width=width + 1)
        elif width > 5:
            lb.configure(width=width - 1)
        v["skipChangeWindowBorder"] = 1
        self.root.update()
        v["skipChangeWindowBorder"] = 0
        fig = self.w(".fig")
        w = fig.winfo_x() + fig.winfo_width()
        self.root.geometry("%dx%d" % (w, v.i("winHeight")))
        self.changeWindowBorder()
        v["winWidthMin"] = fig.winfo_x() + v.i("cWidthMin")
        self.root.minsize(v.i("winWidthMin"), v.i("winHeightMin"))

    def changeRecListWidth(self, mode):
        self._change_list_width(self.rec, mode)

    def changeTypeListWidth(self, mode):
        self._change_list_width(self.type, mode)

    # ------------------------------------------------------------------
    # recording (manual)

    def _rec_params(self):
        """Returns dict(device, rate, channels, dtype, enc, blocksize, gain)."""
        if self.paDev.i("useRec"):
            fmt = self.paDev.get("sampleFormat", "Int16")
            return dict(device=self._pa_device("input"), rate=self.paDev.i("sampleRate") or 44100,
                        channels=max(1, self.paDev.i("channel") or 1),
                        dtype=audio.FORMAT_DTYPE.get(fmt, "int16"),
                        enc=audio.FORMAT_ENC.get(fmt, "Lin16"),
                        blocksize=self.paDev.i("bufferSize") or 0, gain=1.0)
        return dict(device=self._snack_device("input"), rate=self.v.i("sampleRate") or 44100,
                    channels=1, dtype="int16", enc="Lin16", blocksize=0,
                    gain=self.dev.f("ingain", 100.0) / 100.0)

    def _open_recorder(self):
        p = self._rec_params()
        self.recorder.open(p["device"], p["rate"], p["channels"], p["dtype"],
                           blocksize=p["blocksize"], gain=p["gain"])
        self._take_params = p

    def recStart(self):
        v = self.v
        if v.i("rec") == 0 or v.i("recNow"):
            return
        if v.i("rec") >= 2:
            if self.bgmParam.i("autoRecStatus") == 0:
                self.autoRecStart()
            else:
                self.autoRecStop()
        else:
            v["msg"] = self.tt("recStart,msg")
            try:
                self._open_recorder()
                self.recorder.begin()
            except audio.AudioError as e:
                messagebox.showwarning(self.tt(".confm.errTitle"), "%s\n%s" % (self.tt("recStart,errPa"), e))
                return
            v["recStatus"] = 1
            v["recNow"] = 1
            self._live_start()

    # ------------------------------------------------------------------
    # live display while recording (Snack updated the waveform and the
    # spectrogram items while recording; here all four panels follow)

    LIVE_INTERVAL = 60   # msec

    def _live_start(self):
        self._live_stop()
        self._live_f0_hz = []
        self._live_job = self.root.after(self.LIVE_INTERVAL, self._live_tick)

    def _live_stop(self):
        job = getattr(self, "_live_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self._live_job = None

    def _live_tick(self):
        import time as _time
        self._live_job = None
        if not self.v.i("recNow"):
            return
        cost = 0.0
        data = self.recorder.peek()
        if len(data):
            p = getattr(self, "_take_params", None) or self._rec_params()
            self.snd.set_data(data, p["rate"], p["enc"])
            t0 = _time.time()
            self.Redraw("live")
            cost = _time.time() - t0
        # never use more than ~40% of the time for drawing
        delay = max(self.LIVE_INTERVAL, int(cost * 1000 * 1.5))
        self._live_job = self.root.after(delay, self._live_tick)

    def _store_take(self, data):
        p = getattr(self, "_take_params", None) or self._rec_params()
        self.snd.set_data(data, p["rate"], p["enc"])
        self.snd.filename = ""

    def recStop(self):
        v = self.v
        if v.i("rec") != 1 or v.i("recNow") == 0:
            return
        v["msg"] = self.tt("recStop,msg")
        self._live_stop()
        data = self.recorder.end()
        self.recorder.close()
        self._store_take(data)
        if v.i("removeDC"):
            self.removeDC()
        v["recNow"] = 0
        self.Redraw("all")

    # ------------------------------------------------------------------
    # automatic recording with the guide BGM

    def val2samp(self, val, unit, sr):
        val = float(val)
        if unit in ("MSEC", "msec"):
            return int(val / 1000.0 * sr)
        if unit in ("SEC", "sec"):
            return int(val * sr)
        if self.fix("F07"):
            return int(val)
        # original: "return int($val);" returns the string "int(...)" which
        # later breaks "bgm play -start ..."
        raise ValueError('expected integer but got "int(%s)"' % tclfmt.format_list([str(val)]))

    def autoRecStart(self):
        v, t = self.v, self.tt
        if self.audio_busy() and not self.fix("F11"):
            return
        if v.i("rec") == 0:
            return
        if not os.path.exists(v["bgmFile"]):
            messagebox.showerror(t(".confm.fioErr"), self.msg("autoRecStart,errMsg"))
            return
        try:
            self.bgm.read(v["bgmFile"])
        except Exception as e:
            messagebox.showerror(t(".confm.fioErr"), "%s\n%s" % (self.msg("autoRecStart,errMsg"), e))
            return
        v["bgmParamFile"] = _fwd(os.path.splitext(v["bgmFile"])[0] + ".txt")
        try:
            text = self.read_textfile(v["bgmParamFile"])
        except OSError:
            messagebox.showerror(t(".confm.fioErr"), self.msg("autoRecStart,errMsg2"))
            return
        lines = text.split("\n")
        unit = re.sub(",", "", lines[0].strip()) if lines else ""
        if not re.match(r"^(sec|SEC|msec|MSEC|sample)$", unit):
            messagebox.showwarning("", "%s (%s=%s)" % (self.msg("autoRecStart,errMsg3"),
                                                       t("autoRecStart,unit"), unit))
            return
        self.bgmParam.unset_all()
        self.bgmParam["autoRecStatus"] = 0
        sr = self.bgm.rate
        rows = {}
        seq = None
        try:
            for l in lines[1:]:
                l = l.rstrip("\r")
                if re.match(r"^\s*#", l):
                    continue
                p = l.split(",")
                if len(p) >= 6:
                    seq = int(p[0].strip())
                    r = dict(pStart=self.val2samp(p[1].strip(), unit, sr),
                             rStart=int(float(p[2].strip() or 0)), rStop=int(float(p[3].strip() or 0)),
                             nextRec=int(float(p[4].strip() or 0)), repeat=int(float(p[5].strip() or 0)),
                             msg=p[6].strip() if len(p) >= 7 else "")
                    rows[seq] = r
                    if seq > 1 and (seq - 1) in rows:
                        old = rows[seq - 1]
                        old["pStop"] = old["pStart"] if old["repeat"] != 0 else r["pStart"] - 1
        except ValueError:
            if not self.fix("F01"):
                raise
            messagebox.showerror(t(".confm.fioErr"), self.msg("autoRecStart,errMsg4"))
            return
        if seq is None or 1 not in rows:
            if not self.fix("F01"):
                raise KeyError('can\'t read "seq": no such variable')
            messagebox.showerror(t(".confm.fioErr"), self.msg("autoRecStart,errMsg4"))
            return
        if rows[seq]["repeat"] != 0:
            rows[seq]["pStop"] = rows[seq]["pStart"]
        else:
            messagebox.showerror("", self.msg("autoRecStart,errMsg4"))
            return
        for s, r in rows.items():
            if "pStop" not in r:
                r["pStop"] = r["pStart"]
            for k in ("pStart", "rStart", "rStop", "nextRec", "repeat", "msg", "pStop"):
                self.bgmParam["%d,%s" % (s, k)] = r[k]
            self.bgmParam["%d,after" % s] = int((r["pStop"] - r["pStart"]) * 1000.0 / sr + 0.5)
        self.bgm_rows = rows

        if not self.paDev.i("usePlay"):
            self.snd.configure(channels=1, rate=v.i("sampleRate"), encoding="Lin16")
        try:
            self._open_recorder()
        except audio.AudioError as e:
            messagebox.showwarning(t(".confm.errTitle"), "%s\n%s" % (t("aRecStart,errPa"), e))
            return
        self.bgmParam["autoRecStatus"] = 1
        v["recStatus"] = 1
        self.msgLabel.configure(fg="blue")
        dev, gain, _lat, _bs = self.out_device()
        self._sync_cache()
        mode = v.i("rec")

        def can_next():
            return self._rec_seq_cache < self._rec_len_cache - 1

        try:
            self.auto_engine.start(self.bgm.data, self.bgm.rate, rows, mode, self._autoRecEvent,
                                   can_next, device=dev, gain=gain)
        except audio.AudioError as e:
            self.bgmParam["autoRecStatus"] = 0
            self.recorder.close()
            messagebox.showwarning(t(".confm.errTitle"), "%s\n%s" % (t("aRecStart,errPa"), e))

    def _autoRecEvent(self, ev, seq):
        if not self.bgmParam.i("autoRecStatus"):
            return
        r = self.bgm_rows.get(seq)
        if r is None:
            return
        if ev == "stop_before":
            self.autoRecStop()
            return
        if r["rStart"] != 0:
            self.msgLabel.configure(fg="red")
            self.aRecStart()
        if r["rStop"] != 0:
            self.msgLabel.configure(fg="blue")
            self.aRecStop()
        if r["nextRec"] != 0:
            if ev == "stop_after":
                self.autoRecStop()
                return
            self.msgLabel.configure(fg="blue")
            self.nextRec()
            self._sync_cache()
        if ev == "stop_after":
            self.autoRecStop()
            return
        self.v["msg"] = r["msg"]

    def aRecStart(self):
        v = self.v
        if v.i("rec") == 0 or v.i("recNow") or self.bgmParam.i("autoRecStatus") == 0:
            return
        if not self.recorder.capturing:
            self.recorder.begin()
        v["recNow"] = 1
        v["recStatus"] = 1
        self._live_start()

    def aRecStop(self):
        v = self.v
        if v.i("rec") == 0 or v.i("recNow") == 0:
            return
        self._live_stop()
        data = self.recorder.end()
        self._store_take(data)
        if v.i("removeDC"):
            self.removeDC()
        v["recNow"] = 0
        self.Redraw("all")   # final, exact analysis of the finished take

    def autoRecStop(self):
        v = self.v
        self.bgmParam["autoRecStatus"] = 0
        self.auto_engine.stop()
        self.msgLabel.configure(fg="black")
        v["msg"] = self.msg("autoRecStop,doneMsg")
        self.aRecStop()
        self.recorder.close()
        self.Redraw("all")

    # ------------------------------------------------------------------
    # metronome

    def toggleMetroPlay(self):
        v = self.v
        if v.i("playMetroStatus"):
            v["msg"] = self.tt("toggleMetroPlay,stopMsg")
            self.metro_player.stop()
            v["playMetroStatus"] = 0
        else:
            try:
                tempo = float(v["tempo"])
            except ValueError:
                tempo = 0
            if tempo < 50 or tempo > 200:
                messagebox.showerror(self.tt("toggleMetroPlay,errTitle"), self.msg("toggleMetroPlay,errMsg"))
                return
            if not os.path.exists(v["clickWav"]):
                messagebox.showerror(self.tt("toggleMetroPlay,errTitle"), self.msg("toggleMetroPlay,errMsg2"))
                return
            try:
                self.metro.read(v["clickWav"])
            except Exception as e:
                messagebox.showerror(self.tt("toggleMetroPlay,errTitle"), str(e))
                return
            v["playMetroStatus"] = 1
            dev, gain, _lat, _bs = self.out_device()
            period = int(v.f("tempoMSec") / 1000.0 * self.metro.rate)
            try:
                self.metro_player.play(self.metro.data, self.metro.rate, period, device=dev, gain=gain)
            except audio.AudioError as e:
                v["playMetroStatus"] = 0
                messagebox.showwarning(self.tt(".confm.errTitle"),
                                       "%s\n%s" % (self.tt("toggleMetroPlay,errPa"), e))
                return
            v["msg"] = self.tt("toggleMetroPlay,playMsg")

    # ------------------------------------------------------------------
    # playback

    def showPlayBar(self, t0):
        v = self.v
        self.c.delete("playBar")
        if v.i("playStatus") == 0:
            return
        x = self.player.position_sec() * v.f("wavepps")
        self.c.create_line(x, 0, x, v.i("cHeight"), fill="#FFA000", tags="playBar")
        self.root.after(50, lambda: self.showPlayBar(t0))

    def togglePlay(self, start=0, end=-1):
        v = self.v
        if self.snd.length() <= 0:
            return
        if v.i("playStatus"):
            self.player.stop()
            v["playStatus"] = 0
            v["msg"] = self.tt("togglePlay,stopMsg")
        else:
            v["msg"] = self.tt("togglePlay,playMsg")
            v["playStatus"] = 1

            def done():
                v["playStatus"] = 0
                v["msg"] = self.tt("togglePlay,stopMsg")
            dev, gain, lat, bs = self.out_device()
            try:
                self.player.play(self.snd.data, self.snd.rate, start, end, device=dev, gain=gain,
                                 on_done=done, latency=lat, blocksize=bs)
            except audio.AudioError as e:
                v["playStatus"] = 0
                self._play_error(e)
                return
            self.showPlayBar(start / float(self.snd.rate))

    # ------------------------------------------------------------------
    # layout

    def resizeListbox(self):
        v = self.v
        rh = self.rec.winfo_reqheight()
        lines = int(self.rec.cget("height")) or 1
        h = float(rh) / lines
        lh = int(v.i("cHeight") / h) if h > 0 else lines
        lh = max(lh, 1)
        self.rec.configure(height=lh)
        self.type.configure(height=lh)
        self.root.update()
        self.rec.see(v.i("recSeq"))
        self.type.see(v.i("typeSeq"))

    def _toggle_panel(self, show, h, hmin, hbackup, redraw):
        v = self.v
        if v.i(show):
            v[h] = v.i(hbackup)
            hh = v.i("winHeight") + v.i(h)
            v["winHeightMin"] = v.i("winHeightMin") + v.i(hmin)
        else:
            hh = v.i("winHeight") - v.i(h)
            v["winHeightMin"] = v.i("winHeightMin") - v.i(hmin)
            v[hbackup] = v.i(h)
            v[h] = 0
        self.root.geometry("%dx%d" % (v.i("winWidth"), hh))
        self.root.minsize(v.i("winWidthMin"), max(1, v.i("winHeightMin")))
        self.Redraw(redraw)

    def toggleWave(self):
        self._toggle_panel("showWave", "waveh", "wavehmin", "wavehbackup", "wave")

    def toggleSpec(self):
        self._toggle_panel("showSpec", "spech", "spechmin", "spechbackup", "spec")

    def togglePow(self):
        self._toggle_panel("showpow", "powh", "powhmin", "powhbackup", "pow")

    def toggleF0(self):
        self._toggle_panel("showf0", "f0h", "f0hmin", "f0hbackup", "f0")

    def myAxis(self, canvas, x, y, width, height, tags="snack_y_axis", font=("Helvetica", 8),
               max_=1000.0, fill="black", draw0=0, min_=0.0, unit="Hz"):
        if height <= 0:
            return
        max_, min_ = float(max_), float(min_)
        if max_ <= min_:
            return
        f = tkfont.Font(font=font)
        max_min = max_ - min_
        if unit == "semitone":
            ylow = height + y
            ppd = float(height) / max_min
            kokken = int(ppd / 2)
            kokkenHH = kokken if kokken < 10 else 10
            kokkenW = width / 2
            first = 0
            smin = self.v.i("sinScaleMin")
            for i, hz in enumerate(self._sinScale):
                tgt = self.hz2semitone(hz)
                y1 = ylow - (tgt - min_) * ppd
                if y1 <= ylow - height:
                    break
                if y1 <= ylow:
                    tt = i % 12
                    if tt in (1, 3, 6, 8, 10):
                        yt = y1 - kokkenHH
                        yb = y1 + kokkenHH + 1
                        canvas.create_line(kokkenW, y1, width, y1, tags=tags, fill="black")
                        canvas.create_rectangle(0, yt, kokkenW, yb, tags=tags, fill="#d0d0d0")
                    elif tt in (4, 11):
                        yw = y1 - kokken
                        canvas.create_line(0, yw, width, yw, tags=tags, fill="black")
                    elif tt == 0:
                        canvas.create_text(kokkenW, y1, text="C%d" % (i // 12 + smin), fill=fill,
                                           font=font, anchor="w", tags=tags)
                    if first == 0:
                        if tt != 0:
                            key = TONE_LIST[tt]
                            canvas.create_line(kokkenW, y1, width, y1, tags=tags, fill="white")
                            canvas.create_text(kokkenW, y1, text="%s%d" % (key, i // 12 + smin),
                                               fill=fill, font=font, anchor="w", tags=tags)
                        first = 1
            return
        ticklist = [0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500]
        linespace = f.metrics("linespace")
        ascent = f.metrics("ascent")
        npt = ticklist[-1]
        dy = 0
        for elem in ticklist:
            npt = elem
            dy = float(height * npt) / max_min
            if dy >= linespace:
                break
        hztext = "st" if unit == "semitone" else unit
        if draw0:
            i0, j0 = 0, 0
        else:
            i0, j0 = dy, 1
        if min_ != 0:
            j0 = int(min_ / npt) + 1
        yzure = float(min_ - (j0 - 1) * npt) * height / max_min
        yc = height + y + yzure - i0
        j = j0
        guard = 0
        while yc > y and guard < 10000:
            guard += 1
            tm = j * npt if npt < 1000 else j * npt / 1000.0
            tms = snackui._fmt_num(tm)
            if yc > 8 + y:
                if (yc - ascent) > (y + linespace) or f.measure(hztext) < (width - 8 * self.S - f.measure(tms)):
                    canvas.create_text(x + width - 8 * self.S, yc - 2, text=tms, fill=fill, font=font,
                                       anchor="e", tags=tags)
                canvas.create_line(x + width - 5 * self.S, yc, x + width, yc, tags=tags, fill=fill)
            yc -= dy
            j += 1
        canvas.create_text(x + 2, y + 1, text=hztext, font=font, anchor="nw", tags=tags, fill=fill)
        return npt

    # ------------------------------------------------------------------
    # canvas redraw

    def _calc_rate(self, snd_rate):
        """Sample rate used for window lengths (F06 selects the real one)."""
        return snd_rate if self.fix("F06") else self.v.i("sampleRate")

    def Redraw(self, opt):
        v, c, cY = self.v, self.c, self.cYaxis
        power, f0 = self.power, self.f0
        v["cHeight"] = v.i("waveh") + v.i("spech") + v.i("powh") + v.i("f0h") + v.i("timeh")
        cW = v.i("cWidth")
        cH = v.i("cHeight")
        c.delete("obj")
        c.delete("axis")
        c.configure(height=cH, width=cW)
        c.create_line(0, 0, cW, 0, tags="axis", fill=v["fg"])
        cY.delete("axis")
        cY.configure(height=cH)
        yw = v.i("yaxisw")
        cY.create_line(0, 2, yw, 2, tags="axis", fill=v["fg"])
        cY.create_line(yw, 0, yw, cH, tags="axis", fill=v["fg"])
        sndLen = self.snd.length_sec()
        if sndLen > 0:
            v["wavepps"] = float(cW) / sndLen
        else:
            v["wavepps"] = 1.0 / cW if cW else 1.0
        pps = v.f("wavepps")
        sfont = tuple(self.v.lst("sfont")) or ("Helvetica", 8, "bold")
        mono = self.snd.mono() if self.snd.length() else np.zeros(0)
        waveh = v.i("waveh")

        if v.i("showWave"):
            snackui.draw_waveform(c, 0, 0, mono, cW, waveh, v.i("waveScale"), v["wavColor"], ("obj", "wave"))
            c.tag_lower("wave")
            if v.i("waveScale") > 0:
                cY.create_text(yw, 4, text=v["waveScale"], font=sfont, anchor="ne", tags="axis", fill="#0000b0")
                cY.create_text(yw, waveh * 0.5, text=str(self.snd.max()), font=sfont, anchor="se",
                               tags="axis", fill=v["fg"])
                cY.create_text(yw, waveh * 0.5 + 14, text=str(self.snd.min()), font=sfont, anchor="se",
                               tags="axis", fill=v["fg"])
            else:
                cY.create_text(yw, 4, text=str(self.snd.max()), font=sfont, anchor="ne", tags="axis", fill=v["fg"])
                cY.create_text(yw, waveh, text=str(self.snd.min()), font=sfont, anchor="se", tags="axis",
                               fill=v["fg"])
            c.create_line(0, waveh, cW, waveh, tags="axis", fill=v["fg"])
            cY.create_line(0, waveh, yw, waveh, tags="axis", fill=v["fg"])

        if v.i("showSpec"):
            if v.i("winlen") > v.i("fftlen"):
                v["winlen"] = v["fftlen"]
            spech = v.i("spech")
            cmapname = v["cmap"]
            cmap = dsp.parse_colormap(v.lst(cmapname)) if cmapname != "grey" else None
            ppm = dsp.spectrogram_ppm(mono, self.snd.rate, cW, spech, pps, v.i("fftlen"), v.i("winlen"),
                                      v["window"], v.f("preemph"), v.f("topfr"), v.f("contrast"),
                                      v.f("brightness"), cmap)
            self._spec_img = tk.PhotoImage(master=self.root, data=ppm, format="ppm")
            c.create_image(0, waveh, image=self._spec_img, anchor="nw", tags=("obj", "spec"))
            c.tag_lower("spec")
            snackui.frequency_axis(cY, 0, waveh, yw, spech, topfr=v.f("topfr"), tags="axis", font=sfont)
            ylow = spech + waveh
            c.create_line(0, ylow, cW, ylow, tags="axis")
            cY.create_line(0, ylow, yw, ylow, tags="axis", fill=v["fg"])

        if v.i("showpow"):
            ytop = waveh + v.i("spech")
            ylow = ytop + v.i("powh")
            if opt in ("all", "pow", "live"):
                rate = self.snd.rate
                pw = dsp.power(mono, rate, power.f("frameLength"), power["window"], power.f("preemphasis"),
                               int(power.f("windowLength") * self._calc_rate(rate)))
                self._power = list(pw)
                if len(pw):
                    power["powerMax"] = float(np.max(pw))
                    power["powerMin"] = float(np.min(pw))
            pwl = getattr(self, "_power", [])
            if len(pwl) > 0:
                pmax, pmin = power.f("powerMax"), power.f("powerMin")
                ppd = float(v.i("powh")) / (pmax - pmin) if pmax - pmin > 0 else 0
                a = dsp._clampf(power.f("frameLength"), 0.001, 1.0, 0.01) * pps
                coords = []
                for i, p in enumerate(pwl):
                    coords.extend((i * a, ylow - (p - pmin) * ppd))
                if len(coords) >= 4:
                    c.create_line(*coords, tags=("obj", "pow"), fill=v["powcolor"])
                self.myAxis(cY, 0, ytop, yw, v.i("powh"), max_=pmax, tags="axis", fill=v["fg"],
                            font=sfont, min_=pmin, unit="dB")
            c.create_line(0, ylow, cW, ylow, tags="axis")
            cY.create_line(0, ylow, yw, ylow, tags="axis", fill=v["fg"])
            if power["fid"] != v["recLab"]:
                power["fid"] = v["recLab"]

        if v.i("showf0"):
            ytop = waveh + v.i("spech") + v.i("powh")
            f0h = v.i("f0h")
            ylow = ytop + f0h
            if opt in ("all", "f0", "live"):
                x = mono
                if len(x):
                    amp = float(np.max(x) - np.min(x))
                    if amp > 0:
                        x = x * (65535.0 / amp)
                kw = dict(frame_length=f0.f("frameLength"), window_length=f0.f("windowLength"),
                          maxpitch=f0.f("max"), minpitch=f0.f("min"))
                try:
                    if opt == "live":
                        # while recording: only analyse the new frames (+ a few before them)
                        step = max(1, int(round(dsp._clampf(f0.f("frameLength"), 0.001, 0.5, 0.01) * self.snd.rate)))
                        have = self._live_f0_hz
                        k0 = max(0, len(have) - 5)
                        seg = dsp.pitch(x[k0 * step:], self.snd.rate, f0["method"], **kw) \
                            if len(x) > k0 * step + 16 else []
                        self._live_f0_hz = have[:k0] + [float(s) for s in seg]
                        series = self._live_f0_hz
                    else:
                        series = dsp.pitch(x, self.snd.rate, f0["method"], **kw) if len(x) else []
                except Exception as e:
                    self.log("error: %s" % e)
                    series = []
                vals = []
                for val in series:
                    if f0["unit"] == "semitone" and val > 0:
                        val = self.hz2semitone(val)
                    vals.append(float(val))
                self._f0 = vals
                if vals:
                    emax = vals[0]
                    emin = vals[0]
                    for val in vals[1:]:
                        if emax < val:
                            emax = val
                        if (emin > val and val > 0) or emin <= 0:
                            emin = val
                    f0["extractedMax"] = emax
                    f0["extractedMin"] = emin
            vals = getattr(self, "_f0", [])
            if vals:
                if f0.i("fixShowRange"):
                    emax, emin = f0.f("showMax"), f0.f("showMin")
                    if f0["unit"] == "semitone":
                        if emax > 0:
                            emax = self.hz2semitone(emax)
                        if emin > 0:
                            emin = self.hz2semitone(emin)
                    f0["extractedMax"] = emax
                    f0["extractedMin"] = emin
                emax, emin = f0.f("extractedMax"), f0.f("extractedMin")
                if emax > emin and emin >= 0:
                    ppd = float(f0h) / (emax - emin)
                    if f0.i("showToneLine"):
                        for i, hz in enumerate(self._sinScale):
                            tgt = self.hz2semitone(hz) if f0["unit"] == "semitone" else hz
                            y1 = ylow - (tgt - emin) * ppd
                            if y1 <= ylow - f0h:
                                break
                            if y1 < ylow:
                                if i % 12 in (1, 3, 6, 8, 10):
                                    c.create_line(0, y1, cW, y1, tags="axis", fill="#50c0f0", stipple="gray50")
                                else:
                                    c.create_line(0, y1, cW, y1, tags="axis", fill="#f0c0a0")
                    if f0.i("showTgtLine"):
                        tf = f0.f("tgtFreq")
                        if tf > 0:
                            tgt = self.hz2semitone(tf) if f0["unit"] == "semitone" else tf
                            y1 = ylow - (tgt - emin) * ppd
                            if ylow - f0h <= y1 <= ylow:
                                c.create_text(2, y1, text=f0["tgtTone"] + f0["tgtOctave"], fill=v["tgtf0color"],
                                              font="smallkfont", anchor="w", tags=("axis", "tgtName"))
                                bb = c.bbox("tgtName")
                                c.create_line(bb[2] if bb else 0, y1, cW, y1, tags="axis", fill=v["tgtf0color"])
                    a = dsp._clampf(f0.f("frameLength"), 0.001, 0.5, 0.01) * pps
                    a2 = ylow - f0h
                    dot = max(3, int(round(3 * self.S)))
                    for i, val in enumerate(vals):
                        if val > 0:
                            x1 = i * a - dot / 2.0
                            y1 = ylow - (val - emin) * ppd - dot / 2.0
                            if a2 <= y1 <= ylow:
                                c.create_oval(x1, y1, x1 + dot, y1 + dot, tags=("obj", "f0"), fill=v["f0color"])
                self.myAxis(cY, 0, ytop, yw, f0h, tags="axis", fill=v["fg"], font=sfont,
                            max_=f0.f("extractedMax"), min_=f0.f("extractedMin"), unit=f0["unit"])
            c.create_line(0, ylow, cW, ylow, tags="axis")
            if f0["fid"] != v["recLab"]:
                f0["fid"] = v["recLab"]

        if v.i("showWave") or v.i("showSpec") or v.i("showpow") or v.i("showf0"):
            ytop = waveh + v.i("spech") + v.i("powh") + v.i("f0h")
            ylow = ytop + v.i("timeh")
            snackui.time_axis(c, 0, ytop, cW, v.i("timeh"), pps, tags="axis", fill=v["fg"])
            c.create_line(0, ylow, cW, ylow, tags="axis")

    def changeWindowBorder(self, w=None, h=None):
        v = self.v
        if v.i("skipChangeWindowBorder"):
            return
        self.root.update()
        aw = w if w is not None else self.root.winfo_width()
        ah = h if h is not None else self.root.winfo_height()
        if v.i("winWidth") == aw and v.i("winHeight") == ah:
            return
        v["winWidth"] = aw
        v["winHeight"] = ah
        v["cWidth"] = max(1, aw - self.w(".s").winfo_width() - v.i("yaxisw") - 8)
        sndLength = self.snd.length_sec()
        if sndLength > 0:
            v["wavepps"] = v.i("cWidth") / sndLength
        cHeightNew = (ah - self.w(".fig").winfo_y() - self.w(".saveDir").winfo_height()
                      - self.w(".msg").winfo_height() - 4)
        diff = cHeightNew - v.i("cHeight")
        if diff > 0:
            for key in ("f0h", "powh", "spech", "waveh"):
                if v.i(key) > 0:
                    v[key] = v.i(key) + diff
                    break
        elif diff < 0:
            for key, mn in (("f0h", "f0hmin"), ("powh", "powhmin"), ("spech", "spechmin"), ("waveh", "wavehmin")):
                if diff < 0 and v.i(key) > 0:
                    old = v.i(key)
                    new = max(old + diff, v.i(mn))
                    v[key] = new
                    diff -= (new - old)
        self.Redraw("scale")
        self.resizeListbox()

    # ------------------------------------------------------------------
    # oto.ini parameter tables

    def initParamS(self):
        self.paramS = {}

    def initParamU(self, clean=0, recList=None):
        if not recList:
            recList = self.recList()
        self.paramU = {}
        for c in range(7):
            self.paramU[(0, c)] = self.tt("initParamU,%d" % c)
        self.paramUsize = 1
        if clean:
            return
        for i, fid in enumerate(recList):
            self.paramU[(self.paramUsize, 0)] = fid
            self.paramU[(self.paramUsize, "R")] = i
            self.paramUsize += 1

    # ------------------------------------------------------------------
    # settings file (oremo-init.tcl)

    def saveSettings(self, fn=""):
        s = self.startup
        if fn == "":
            fn = filedialog.asksaveasfilename(initialfile=os.path.basename(s["initFile"]),
                                              initialdir=os.path.dirname(s["initFile"]),
                                              title=self.tt("saveSettings,title"), defaultextension="tcl")
        if not fn:
            return
        topdir = self.topdir
        excl_arrays = s.lst("exclusionKeysForInitFile,aName")
        lines = []
        for aName in s.lst("arrayForInitFile"):
            arr = self.arrays.get(aName)
            if arr is None:
                continue
            excl = s.lst("exclusionKeysForInitFile,%s" % aName) if aName in excl_arrays else []
            for key, value in arr.items():
                if aName == "v" and key.startswith("recComment,"):
                    continue
                if key in excl:
                    continue
                if value.startswith(topdir):
                    value = "_OREMO_TOPDIR_" + value[len(topdir):]
                lines.append("set %s(%s)\t\t%s" % (aName, key, tclfmt.quote_braced(value)))
        for aName, key, value in self.unknown_init:
            lines.append("set %s(%s)\t\t%s" % (aName, key, tclfmt.quote_braced(value)))
        try:
            self.write_textfile(fn, "\n".join(lines) + "\n", "init")
        except OSError:
            messagebox.showwarning(self.tt(".confm.fioErr"), "error: can not open %s" % fn)
            return
        # remember the pixel scale the sizes were saved at (high DPI support)
        self.sysini["pxScale"] = "%.4g" % self.S
        self.writeSysIniFile()

    def readSettings(self):
        s = self.startup
        fn = filedialog.askopenfilename(initialfile=os.path.basename(s["initFile"]),
                                        initialdir=os.path.dirname(s["initFile"]),
                                        title=self.tt("readSettings,title", "read"), defaultextension="tcl",
                                        filetypes=[("tcl file", ".tcl"), ("All Files", "*")])
        if fn:
            self.doReadInitFile(fn)

    def doReadInitFile(self, initFile, px_factor=None):
        if not os.path.exists(initFile):
            return
        try:
            text = self.read_textfile(initFile)
        except OSError:
            if self.t.exists("doReadInitFile,errMsg"):
                messagebox.showwarning(self.tt(".confm.fioErr"), self.tt("doReadInitFile,errMsg"))
            else:
                messagebox.showwarning("File I/O Error", "can not read the file (%s)" % initFile)
            return
        if not self.fix("F08"):
            bad = tclfmt.unsafe_lines(text)
            if bad:
                l = bad[0]
                if self.t.exists("doReadInitFile,errMsg2"):
                    messagebox.showwarning(self.tt(".confm.fioErr"), self.tt("doReadInitFile,errMsg2"))
                else:
                    messagebox.showwarning(
                        "File I/O Error",
                        'Syntax error\nLine: %s\nFile: %s\nYou can use only "set variableName {value}" in that file.'
                        % (l, initFile))
                return
        topdir = self.topdir
        known = set(self.startup.lst("arrayForInitFile")) | {"paDev"}
        for arr, key, value in tclfmt.parse_set_file(text):
            if key is None:
                continue
            if self.fix("F08"):
                value = value.replace("\\[", "[")
            if value.startswith("_OREMO_TOPDIR_"):
                value = topdir + value[len("_OREMO_TOPDIR_"):]
            target = self.arrays.get(arr)
            if target is None or arr not in known:
                self.unknown_init.append((arr, key, value))
                continue
            if arr == "v" and key.startswith("recComment,"):
                continue
            if arr == "v" and key in GEOM_KEYS and px_factor and abs(px_factor - 1.0) > 1e-3:
                try:
                    value = int(round(float(value) * px_factor))
                except ValueError:
                    pass
            target[key] = value

    # ------------------------------------------------------------------
    # audio devices at start up (audioSettings)

    def audioSettings(self):
        dev = self.dev
        ins = audio.mme_devices("input")
        outs = audio.mme_devices("output")
        dev["in"] = ins[0][1] if ins else "none"
        dev["out"] = outs[0][1] if outs else "none"
        dev["ingain"] = 100
        dev["outgain"] = 100
        dev["latency"] = 0
        dev["sndBuffer"] = 200000
        dev["bgmBuffer"] = 200000

    def _restore_audio_settings(self):
        """F09: restore device settings saved in oremo-setting.ini."""
        for key in ("in", "out", "ingain", "outgain", "latency", "sndBuffer", "bgmBuffer"):
            val = self.ini("audio.dev." + key, None)
            if val is not None:
                self.dev[key] = val
        for key in ("in", "out", "sampleRate", "sampleFormat", "channel", "bufferSize",
                    "useRequestRec", "useRequestPlay"):
            val = self.ini("audio.paDev." + key, None)
            if val is not None:
                self.paDev[key] = val
        if self.paDev.i("useRequestRec"):
            if self.paRecRun(quiet=True) == 0:
                self.paDev["useRec"] = 1
        if self.paDev.i("useRequestPlay"):
            if self.paPlayRun(quiet=True) == 0:
                self.paDev["usePlay"] = 1

    def _save_audio_settings(self):
        for key in ("in", "out", "ingain", "outgain", "latency", "sndBuffer", "bgmBuffer"):
            self.sysini["audio.dev." + key] = self.dev.get(key, "")
        for key in ("in", "out", "sampleRate", "sampleFormat", "channel", "bufferSize"):
            self.sysini["audio.paDev." + key] = self.paDev.get(key, "")
        self.sysini["audio.paDev.useRequestRec"] = self.paDev.get("useRec", "0")
        self.sysini["audio.paDev.useRequestPlay"] = self.paDev.get("usePlay", "0")
        self.writeSysIniFile()

    # ------------------------------------------------------------------

    def tk_dialog(self, w, title, text, bitmap, default, *buttons):
        try:
            self.tk.call("destroy", w)
        except tk.TclError:
            pass
        return int(self.tk.call("tk_dialog", w, title, text, bitmap, default, *buttons))

    def isExist(self, w):
        try:
            win = self.root.nametowidget(w)
        except KeyError:
            return 0
        if win.winfo_exists():
            win.lift()
            win.focus_set()
            return 1
        return 0

    def Exit(self):
        v = self.v
        if v.i("recStatus"):
            act = self.tk_dialog(".confm", self.tt(".confm"), self.tt("Exit,q2"), "question", 2,
                                 self.tt("Exit,a1"), self.tt("Exit,a2"), self.tt("Exit,a3"))
            if act == 2:
                return
            elif act == 0:
                self.saveWavFile()
        self.saveCommentList()
        for p in (self.player, self.bgm_player, self.onsa_player, self.sin_player, self.metro_player,
                  self.auto_engine):
            try:
                p.stop()
            except Exception:
                pass
        self.recorder.close()
        if self.fix("F09"):
            self._save_audio_settings()
        if v.i("autoSaveInitFile"):
            self.saveSettings(self.startup["initFile"])
        self.root.destroy()

    def PopUpMenu(self, X, Y, x, y):
        m = self.rclickMenu
        t = self.tt
        m.delete(0, "end")
        m.add_checkbutton(variable="v(showWave)", label=t("PopUpMenu,showWave"), command=self.toggleWave)
        m.add_checkbutton(variable="v(showSpec)", label=t("PopUpMenu,showSpec"), command=self.toggleSpec)
        m.add_checkbutton(variable="v(showpow)", label=t("PopUpMenu,showPow"), command=self.togglePow)
        m.add_checkbutton(variable="v(showf0)", label=t("PopUpMenu,showF0"), command=self.toggleF0)
        m.add_command(label=t("PopUpMenu,pitchGuide"), command=self.pitchGuide)
        m.add_command(label=t("PopUpMenu,tempoGuide"), command=self.tempoGuide)
        m.add_command(label=t("PopUpMenu,settings"), command=self.settings)
        try:
            m.tk_popup(X, Y)
        finally:
            m.grab_release()

    def Version(self):
        v = self.v
        messagebox.showinfo(self.tt("Version,msg"),
                            "%s version %s\n\n%s" % (v["appname"], v["version"],
                                                     self.tt("Version,unicode", "")))

    def listboxScroll(self, w, d):
        if w:
            try:
                self.root.nametowidget(w).yview_scroll(int(-d / 120), "units")
            except (KeyError, tk.TclError):
                pass

    def toggleConsole(self):
        """Ctrl+Alt+d: the Tk console of the original is replaced by a log window."""
        if self.console_win is not None and self.console_win.winfo_exists():
            self.console_win.destroy()
            self.console_win = None
            self.conState = 0
            return
        w = tk.Toplevel(self.root)
        w.title("Console")
        txt = tk.Text(w, width=100, height=30)
        txt.pack(fill="both", expand=1)
        txt.insert("end", "\n".join(self.log_lines) + "\n")
        w.text = txt
        self.console_win = w
        self.conState = 1

    # ------------------------------------------------------------------
    # progress window (initProgressWindow etc.)

    def initProgressWindow(self, title="now processing..."):
        if self.isExist(self.prgWindow):
            return
        w = tk.Toplevel(self.root, name=self.prgWindow[1:])
        w.title(title)
        try:
            w.attributes("-toolwindow", 1)
            w.attributes("-topmost", 1)
        except tk.TclError:
            pass
        g = re.split(r"[x+]", self.root.geometry())
        try:
            x = int(g[2]) + int(g[0]) // 2 - 100
            y = int(g[3]) + int(g[1]) // 2 - 5
            w.geometry("+%d+%d" % (x, y))
        except (ValueError, IndexError):
            pass
        self.v["progress"] = 0
        from tkinter import ttk
        ttk.Progressbar(w, length=int(200 * self.S), variable="v(progress)", mode="determinate").pack()
        w.lift()
        w.focus_set()
        self.root.update()

    def updateProgressWindow(self, progress, title=""):
        try:
            w = self.root.nametowidget(self.prgWindow)
        except KeyError:
            return
        if title:
            w.title(title)
        self.v["progress"] = progress
        w.lift()
        self.root.update()

    def deleteProgressWindow(self):
        try:
            self.root.nametowidget(self.prgWindow).destroy()
        except KeyError:
            pass

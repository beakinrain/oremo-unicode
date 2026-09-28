"""Sub windows of OREMO (settings, audio I/O, guide BGM, metronome, tuning
fork, key bindings, font size, comment search)."""

import os
import re
import tkinter as tk
import tkinter.colorchooser as colorchooser
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

from . import audio
from .state import TVar

TONE_LIST = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

BIND_FUNCS = ["record", "recStop", "nextRec", "prevRec", "nextType", "prevType", "nextRec0",
              "prevRec0", "nextType0", "prevType0", "togglePlay", "toggleOnsaPlay",
              "toggleMetroPlay", "searchComment", "waveReload", "waveExpand", "waveShrink"]

KEYSYM = {"+": "plus", "*": "asterisk", "/": "slash", ";": "semicolon", ":": "colon", "@": "at",
          "!": "exclam", "#": "numbersign", "$": "dollar", "%": "percent", "&": "ampersand",
          "=": "equal", "~": "asciitilde", "?": "question", "_": "underscore", "<": "less",
          ">": "greater", ",": "comma", ".": "period"}

# keys edited in the settings window (used by fix F05)
SETTINGS_KEYS = {
    "v": ["wavColor", "waveScale", "sampleRate", "cmap", "topfr", "brightness", "contrast", "fftlen",
          "winlen", "preemph", "window", "powcolor", "f0color", "tgtf0color"],
    "power": ["frameLength", "preemphasis", "windowLength", "window"],
    "f0": ["method", "frameLength", "windowLength", "max", "min", "unit", "showToneLine",
           "fixShowRange", "showMaxTone", "showMaxOctave", "showMinTone", "showMinOctave",
           "showTgtLine", "tgtTone", "tgtOctave", "showMin", "showMax", "tgtFreq", "checkVol",
           "showMaxTmp", "showMinTmp", "tgtFreqTmp"],
}


class DialogsMixin:

    def _linked_entry(self, parent, var, **kw):
        """Entry for a variable that is also bound to a tk.Scale.

        Tk refuses non numeric values for scale variables, so typing into an
        entry sharing the variable raised an error on every keystroke (e.g.
        when the field was cleared).  The entry gets its own text variable;
        valid numbers are copied to *var*, slider moves are copied back.
        """
        txt = tk.StringVar(parent, value=self.tk.globalgetvar(var))
        busy = [False]

        def to_var(*a):
            if busy[0]:
                return
            s = txt.get().strip()
            try:
                float(s)
            except ValueError:
                return
            busy[0] = True
            try:
                self.tk.globalsetvar(var, s)
            except tk.TclError:
                pass
            finally:
                busy[0] = False

        def from_var(*a):
            if busy[0]:
                return
            busy[0] = True
            try:
                txt.set(str(self.tk.globalgetvar(var)))
            finally:
                busy[0] = False
        txt.trace_add("write", to_var)
        cmd = parent.register(from_var)
        self.tk.call("trace", "add", "variable", var, "write", cmd)
        e = tk.Entry(parent, textvariable=txt, **kw)
        e._linked = txt

        def cleanup(ev):
            if ev.widget is e:
                try:
                    self.tk.call("trace", "remove", "variable", var, "write", cmd)
                except tk.TclError:
                    pass
        e.bind("<Destroy>", cleanup, add="+")
        return e

    def _mkscale(self, parent, **kw):
        """tk.Scale with pixel sizes scaled for high DPI screens."""
        s = getattr(self, "S", 1.0)
        kw.setdefault("length", int(round(100 * s)))
        kw.setdefault("sliderlength", int(round(30 * s)))
        kw.setdefault("width", int(round(15 * s)))
        return tk.Scale(parent, **kw)

    def _vcmd(self, func):
        return (self.root.register(func), "%P")

    def _toplevel(self, path, title):
        w = tk.Toplevel(self.root, name=path.lstrip("."))
        w.title(title)
        return w

    # ------------------------------------------------------------------
    # font size

    def setFontSize(self):
        if self.isExist(self.fontWindow):
            return
        w = self._toplevel(self.fontWindow, self.tt("option,setFontSize"))
        w.bind("<Escape>", lambda e: w.destroy())
        sizes = [str(s) for s in range(8, 51, 2)]
        tk.Label(w, text=self.tt("fontWindow,attention")).grid(row=0, column=0, sticky="w", columnspan=2)
        tk.Label(w, text=self.tt("fontWindow,attention2")).grid(row=1, column=0, sticky="w", columnspan=2)
        for r, (lab, key) in enumerate((("fontWindow,lbfs", "bigFontSize"), ("fontWindow,lfs", "fontSize"),
                                        ("fontWindow,lcfs", "commFontSize")), start=2):
            tk.Label(w, text=self.tt(lab)).grid(row=r, column=0, sticky="e")
            tk.OptionMenu(w, TVar(w, "v(%s)" % key), *sizes).grid(row=r, column=1, sticky="w")
        # font family (Unicode edition): applied immediately
        auto = self.tt("fontWindow,auto", "Auto")
        cur = self.ini("fontFamily", "")
        fvar = tk.StringVar(w, value=cur if cur else auto)

        def set_family(val):
            self.set_ini("fontFamily", "" if val == auto else val)
            self.updateFontFamily(force=True)
            used = self._fonts["kfont"].cget("family")
            info.configure(text="→ %s" % used)
        tk.Label(w, text=self.tt("fontWindow,family", "Font")).grid(row=5, column=0, sticky="e")
        tk.OptionMenu(w, fvar, auto, *self.font_choices(), command=set_family).grid(row=5, column=1, sticky="w")
        info = tk.Label(w, text="→ %s" % self._fonts["kfont"].cget("family"), fg="#404040")
        info.grid(row=6, column=0, columnspan=2, sticky="w")
        tk.Label(w, text=self.tt("fontWindow,familyNote", ""), fg="#404040", justify="left").grid(
            row=7, column=0, columnspan=2, sticky="w")

    # ------------------------------------------------------------------
    # key binding customisation

    def setBind(self):
        if self.isExist(self.bindWindow):
            return
        w = self._toplevel(self.bindWindow, self.tt("option,setBind"))
        keys = self.keys
        backup = keys.snapshot()

        def cancel(*a):
            keys.unset_all()
            keys.restore(backup)
            w.destroy()
        w.protocol("WM_DELETE_WINDOW", cancel)
        w.bind("<Escape>", cancel)
        f = tk.Frame(w, name="f")
        f.pack()
        for r, func in enumerate(BIND_FUNCS):
            if not keys.exists(func):
                keys[func] = ""
            tk.Label(f, text=self.tt("bindWindow,%s" % func), pady=3).grid(row=r, column=0, sticky="e")
            tk.Entry(f, textvariable="keys(%s)" % func, width=30).grid(row=r, column=1, sticky="w")
        fex = tk.Frame(w, name="fex")
        for i, k in enumerate(("bindWindow,ex", "bindWindow,ex2", "bindWindow,ex3")):
            tk.Label(fex, text=self.tt(k), fg="red", anchor="nw").grid(row=i, sticky="w")
        fex.pack(anchor="w")
        fb = tk.Frame(w, name="fb")

        def ok():
            if self.doSetBind() == 0:
                backup.clear()
                backup.update(keys.snapshot())
                w.destroy()
            else:
                w.lift()
                w.focus_set()

        def apply():
            if self.doSetBind() == 0:
                backup.clear()
                backup.update(keys.snapshot())
            w.lift()
            w.focus_set()
        tk.Button(fb, text=self.tt(".confm.ok"), width=8, command=ok).pack(side="left")
        tk.Button(fb, text=self.tt(".confm.apply"), width=8, command=apply).pack(side="left")
        tk.Button(fb, text=self.tt(".confm.c"), width=8, command=cancel).pack(side="left")
        fb.pack(anchor="w")

    def _bind_func(self, func):
        table = {
            "recStop": self.autoRecStop if self.fix("F03") else self.recStop,
            "nextRec": self.nextRec, "prevRec": self.prevRec, "nextType": self.nextType,
            "prevType": self.prevType, "nextRec0": self.nextRec0, "prevRec0": self.prevRec0,
            "nextType0": self.nextType0, "prevType0": self.prevType0, "togglePlay": self.togglePlay,
            "toggleOnsaPlay": self.toggleOnsaPlay, "toggleMetroPlay": self.toggleMetroPlay,
            "searchComment": self.searchComment, "waveReload": self.waveReload,
            "waveExpand": self.waveExpand, "waveShrink": self.waveShrink,
        }
        return table.get(func)

    def doSetBind(self):
        keys = self.keys
        newBindList = []
        for func, value in keys.items():
            if re.match(r"^\s*$", value):
                continue
            data = value.strip().split("-")
            last = len(data) - 1
            modKey = ""
            for i in range(last):
                s = data[i]
                if not re.match(r"(?i)^(Ctrl|Control|Alt|Shift)$", s):
                    messagebox.showwarning(self.tt("bindWindow,errTitle"), self.msg("bindWindow,errMsg", value=value))
                    return 1
                s = re.sub("Ctrl", "Control", s)
                modKey += s + "-"
            key = data[last]
            if not re.match(r"(?i)^(space|F[0-9]+|[a-zA-Z0-9]|[+*/;:@!#$%&=~?_<>,.])$", key):
                messagebox.showwarning(self.tt("bindWindow,errTitle"), self.msg("bindWindow,errMsg", value=value))
                return 1
            if self.fix("F01") and key in KEYSYM:
                key = KEYSYM[key]
            newBindList.append(("%sKeyPress-%s" % (modKey, key), func))
        if self.fix("F04"):
            for seq in self.custom_binds:
                try:
                    self.root.unbind(seq)
                    self.root.event_delete("<<EditComment>>", seq)
                except tk.TclError:
                    pass
            self.custom_binds = []
            self.setDefaultKeyBind()
        for shortcut, func in newBindList:
            if func == "record":
                if self.fix("F12"):
                    shortcut2 = "KeyRelease-" + shortcut.split("KeyPress-")[-1]
                else:
                    shortcut2 = shortcut.replace("KeyPress", "KeyRelease")
                self.root.bind("<%s>" % shortcut, lambda e: self.recStart())
                self.root.bind("<%s>" % shortcut2, lambda e: self.recStop())
                self.root.event_add("<<EditComment>>", "<%s>" % shortcut)
                self.root.event_add("<<EditComment>>", "<%s>" % shortcut2)
                self.custom_binds += ["<%s>" % shortcut, "<%s>" % shortcut2]
                continue
            fn = self._bind_func(func)
            if fn is None:
                continue
            self.root.bind("<%s>" % shortcut, lambda e, fn=fn: fn())
            self.root.event_add("<<EditComment>>", "<%s>" % shortcut)
            self.custom_binds.append("<%s>" % shortcut)
        return 0

    # ------------------------------------------------------------------
    # comment search

    def searchComment(self):
        if self.isExist(self.searchWindow):
            try:
                e = self.root.nametowidget(self.searchWindow + ".f.e")
                e.lift()
                e.focus_set()
            except KeyError:
                pass
            return
        w = self._toplevel(self.searchWindow, self.tt("searchComment,title"))
        w.bind("<Escape>", lambda e: w.destroy())
        f = tk.Frame(w, name="f")
        e = tk.Entry(f, name="e", textvariable="v(keyword)", width=30)
        bs = tk.Button(f, text=self.tt("searchComment,search"),
                       command=lambda: self.doSearchParam(self.v.i("sdirection")))
        bc = tk.Button(f, text=self.tt(".confm.c"), command=w.destroy)
        f2 = tk.LabelFrame(w, relief="groove")
        tk.Radiobutton(f2, variable="v(sdirection)", value=0, text=self.tt("searchComment,rup")).pack(side="top", anchor="nw")
        tk.Radiobutton(f2, variable="v(sdirection)", value=1, text=self.tt("searchComment,rdown")).pack(side="top", anchor="nw")
        f3 = tk.LabelFrame(w, relief="groove")
        tk.Radiobutton(f3, variable="v(sMatch)", value="full", text=self.tt("searchComment,rMatch1")).pack(side="top", anchor="ne")
        tk.Radiobutton(f3, variable="v(sMatch)", value="sub", text=self.tt("searchComment,rMatch2")).pack(side="top", anchor="ne")
        for x in (e, bs, bc):
            x.pack(side="left", anchor="nw")
        f.pack(anchor="nw")
        f2.pack(anchor="nw", side="left")
        f3.pack(anchor="nw", side="left")
        w.bind("<Return>", lambda ev: self.doSearchParam(self.v.i("sdirection")))
        e.lift()
        e.focus_set()

    def doSearchParam(self, direction=1):
        if direction:
            self._doSearch(+1)
        else:
            self._doSearch(-1)

    def _search_match(self, rLab, tLab):
        v = self.v
        kw = v["keyword"]
        key = rLab + tLab
        target = self.comments[key] if key in self.comments else key
        if v["sMatch"] == "full":
            return kw == target
        return target.find(kw) >= 0

    def _doSearch(self, step):
        v = self.v
        rl, tl = self.recList(), self.typeList()
        nt = len(tl)
        rs0, ts0 = v.i("recSeq"), v.i("typeSeq")
        if step > 0:
            if ts0 < nt - 1:
                rStart, ts = rs0, ts0 + 1
            else:
                rStart, ts = rs0 + 1, 0
            rs = rStart
            while rs < len(rl):
                while ts < nt:
                    if self._search_match(rl[rs], tl[ts]):
                        self.jumpRec(rs)
                        self.jumpType(ts)
                        return
                    ts += 1
                ts = 0
                rs += 1
            for rs in range(0, min(rs0, len(rl) - 1) + 1):
                for ts in range(nt):
                    if self._search_match(rl[rs], tl[ts]):
                        self.jumpRec(rs)
                        self.jumpType(ts)
                        return
        else:
            if ts0 > 0:
                rStart, ts = rs0, ts0 - 1
            else:
                rStart, ts = rs0 - 1, nt - 1
            rs = rStart
            while rs >= 0:
                while ts >= 0:
                    if rs < len(rl) and self._search_match(rl[rs], tl[ts]):
                        self.jumpRec(rs)
                        self.jumpType(ts)
                        return
                    ts -= 1
                ts = nt - 1
                rs -= 1
            for rs in range(len(rl) - 1, rs0 - 1, -1):
                for ts in range(nt - 1, -1, -1):
                    if self._search_match(rl[rs], tl[ts]):
                        self.jumpRec(rs)
                        self.jumpType(ts)
                        return
        messagebox.showwarning(self.tt("searchComment,doneTitle"), self.msg("searchComment,doneMsg"))
        try:
            self.root.nametowidget(self.searchWindow + ".f.e").focus_set()
        except KeyError:
            pass

    # ------------------------------------------------------------------
    # guide BGM (recording mode) window

    def bgmGuide(self):
        v, t = self.v, self.tt
        if self.isExist(".bgmg"):
            return
        w = self._toplevel(".bgmg", t("bgmGuide,title"))
        w.bind("<Escape>", lambda e: w.destroy())
        stop = lambda: self.bgm_player.stop()
        tk.Label(w, text=t("bgmGuide,mode")).grid(row=0, column=0, sticky="e")
        for r, (val, key) in enumerate(((1, "bgmGuide,r1"), (2, "bgmGuide,r2"), (3, "bgmGuide,r3"),
                                        (0, "bgmGuide,r4"))):
            tk.Radiobutton(w, variable="v(rec)", value=val, command=stop, text=t(key)).grid(row=r, column=1, sticky="w")
        tk.Label(w, text=t("bgmGuide,bgm")).grid(row=4, column=0, sticky="e")
        fw = tk.Frame(w, name="fWav")

        def choose():
            fn = filedialog.askopenfilename(initialfile=os.path.basename(v["bgmFile"]),
                                            initialdir=os.path.dirname(v["bgmFile"]),
                                            title=t("bgmGuide,bTitle"), defaultextension="wav",
                                            filetypes=[("wav file", ".wav"), ("All Files", "*")], parent=w)
            if fn:
                v["bgmFile"] = fn.replace("\\", "/")
                stop()
        tk.Button(fw, textvariable="v(bgmFile)", relief="solid", command=choose).pack(side="left", fill="x", expand=1)
        tk.Button(fw, image=self.icons["snackOpen"], highlightthickness=0, bg=v["bg"], command=choose).pack(side="left")
        tk.Button(fw, image=self.icons["snackPlay"], command=lambda: self.testPlayBGM(v["bgmFile"])).pack(side="left")
        tk.Button(fw, image=self.icons["snackStop"], command=self.testStopBGM).pack(side="left")
        fw.grid(row=4, column=1, sticky="ewsn")
        fi = tk.Frame(w, name="fImg")
        tk.Label(fi, text=t("bgmGuide,tplay")).pack(side="left")

        def sample():
            root, ext = os.path.splitext(v["bgmFile"])
            self.testPlayBGM(root + "-sample" + ext)
        tk.Button(fi, image=self.icons["snackPlay"], command=sample).pack(side="left")
        tk.Button(fi, image=self.icons["snackStop"], command=self.testStopBGM).pack(side="left")
        fi.grid(row=5, column=1, sticky="ewsn")

    def testPlayBGM(self, fname):
        t = self.tt
        if not os.path.exists(fname):
            messagebox.showwarning(t("testPlayBGM,errTitle"),
                                   "%s (fname=%s)" % (self.msg("testPlayBGM,errMsg"), fname),
                                   parent=self.root.nametowidget(".bgmg") if self.isExist(".bgmg") else self.root)
            return
        if not self.paDev.i("usePlay") and not self.fix("F11") and self.audio_busy():
            return
        try:
            self.bgm.read(fname)
        except Exception as e:
            messagebox.showwarning(t("testPlayBGM,errTitle"), "%s\n%s" % (self.msg("testPlayBGM,errMsg"), e))
            return
        dev, gain, lat, bs = self.out_device()
        try:
            self.bgm_player.play(self.bgm.data, self.bgm.rate, device=dev, gain=gain)
        except audio.AudioError as e:
            self._play_error(e)

    def testStopBGM(self):
        self.bgm_player.stop()

    # ------------------------------------------------------------------
    # metronome window

    def tempoGuide(self):
        v, t = self.v, self.tt
        if self.isExist(".tg"):
            return
        w = self._toplevel(".tg", t("tempoGuide,title"))
        w.bind("<KeyPress-m>", lambda e: self.toggleMetroPlay())
        w.bind("<KeyPress-M>", lambda e: self.toggleMetroPlay())
        w.bind("<Escape>", lambda e: w.destroy())
        tk.Label(w, text=t("tempoGuide,click")).grid(row=0, column=0, sticky="e")

        def choose():
            fn = filedialog.askopenfilename(initialfile=os.path.basename(v["clickWav"]),
                                            initialdir=os.path.dirname(v["clickWav"]),
                                            title=t("tempoGuide,clickTitle"), defaultextension="wav",
                                            filetypes=[("wav file", ".wav"), ("All Files", "*")], parent=w)
            if fn:
                v["clickWav"] = fn.replace("\\", "/")
                self.metro_player.stop()
                v["playMetroStatus"] = 0
        tk.Button(w, textvariable="v(clickWav)", relief="solid", command=choose).grid(
            row=0, column=1, columnspan=4, sticky="nesw")
        tk.Label(w, text=t("tempoGuide,tempo")).grid(row=1, column=0, sticky="e")

        def validate(P):
            if P == "" or not re.match(r"^\s*[+-]?[0-9]+\s*$", P):
                return False
            if int(P) <= 0:
                return False
            v["tempoMSec"] = 60000.0 / float(int(P))
            self.metro_player.stop()
            v["playMetroStatus"] = 0
            return True
        tk.Entry(w, textvariable="v(tempo)", validate="key", validatecommand=self._vcmd(validate)).grid(
            row=1, column=1, sticky="nesw")
        tk.Label(w, text=t("tempoGuide,bpm")).grid(row=1, column=2, sticky="w")
        tk.Label(w, textvariable="v(tempoMSec)", fg="red").grid(row=1, column=3, sticky="e")
        tk.Label(w, text=t("tempoGuide,bpmUnit")).grid(row=1, column=4, sticky="w")
        tk.Label(w, text=t("tempoGuide,comment")).grid(row=2, columnspan=5)

    # ------------------------------------------------------------------
    # tuning fork window

    def pitchGuide(self):
        v, f0, t = self.v, self.f0, self.tt
        if self.isExist(".pg"):
            return
        w = self._toplevel(".pg", t("pitchGuide,title"))
        for seq, d in (("<KeyPress-Up>", 1), ("<KeyPress-8>", 1), ("<KeyPress-Down>", -1), ("<KeyPress-2>", -1),
                       ("<KeyPress-Left>", -12), ("<KeyPress-4>", -12), ("<KeyPress-Right>", 12),
                       ("<KeyPress-6>", 12)):
            w.bind(seq, lambda e, d=d: self.changeTone(d))
        w.bind("<KeyPress-o>", lambda e: self.toggleOnsaPlay())
        w.bind("<KeyPress-O>", lambda e: self.toggleOnsaPlay())
        w.bind("<Escape>", lambda e: w.destroy())
        self.packToneList(w, "tl", t("pitchGuide,sel"), "guideTone", "guideOctave", "guideFreqTmp", 10, "guideVol")
        vl = tk.Frame(w, name="vl")
        vl.pack(fill="x")
        tk.Label(vl, text=t("pitchGuide,vol")).pack(side="left", anchor="nw")
        self._mkscale(vl, from_=0, to=32768, showvalue=0, variable="f0(guideVol)", orient="horizontal").pack(
            side="left", anchor="nw", fill="x", expand=1)
        tk.Label(w, text=t("pitchGuide,comment")).pack(side="left", anchor="nw")
        f0["guideFreqTmp"] = self.tone2freq(f0["guideTone"] + f0["guideOctave"])

        def calc(name1, name2, op):
            if name2 in ("guideTone", "guideOctave"):
                f0["guideFreqTmp"] = self.tone2freq(f0["guideTone"] + f0["guideOctave"])
        cmd = self.root.register(calc)
        self.tk.call("trace", "add", "variable", "f0", "write", cmd)

        def remove(e):
            if str(e.widget) == ".pg":
                try:
                    self.tk.call("trace", "remove", "variable", "f0", "write", cmd)
                except tk.TclError:
                    pass
        w.bind("<Destroy>", remove)

    def packToneList(self, parent, name, text, toneKey, octaveKey, freqKey, width, vol):
        f0, v = self.f0, self.v
        w = tk.Frame(parent, name=name)
        w.pack(fill="x")
        tk.Label(w, text=text, width=width, anchor="w").pack(side="left")
        tk.OptionMenu(w, TVar(w, "f0(%s)" % toneKey), *TONE_LIST).pack(side="left")
        octs = [str(i) for i in range(v.i("sinScaleMin"), v.i("sinScaleMax") + 1)]
        tk.OptionMenu(w, TVar(w, "f0(%s)" % octaveKey), *octs).pack(side="left")
        tk.Button(w, image=self.icons["snackPlay"], text=self.tt("packToneList,play"),
                  command=lambda: self.playSin(self.tone2freq(f0[toneKey] + f0[octaveKey]), f0[vol],
                                               v.i("sampleRate"))).pack(side="left")
        tk.Button(w, text=self.tt("packToneList,repeat"), command=self.toggleOnsaPlay).pack(side="left")
        tk.Label(w, textvariable="f0(%s)" % freqKey, width=3, anchor="e").pack(side="left")
        tk.Label(w, text="Hz").pack(side="left")
        return w

    # ------------------------------------------------------------------
    # colours / small helpers of the settings window

    def chooseColor(self, w, key, initcolor):
        c = colorchooser.askcolor(color=initcolor, title=self.tt("chooseColor,title"))
        if c and c[1]:
            self.v[key] = c[1]
            w.configure(bg=c[1])

    def setColor(self, parent, key, msg):
        ic = self.v[key]
        fr = tk.Frame(parent, name=key.lower())
        fr.pack(anchor="nw")
        tk.Label(fr, text=msg, width=20, anchor="nw").pack(side="left")
        l2 = tk.Label(fr, textvariable="v(%s)" % key, width=7, anchor="nw", bg=self._safe_color(ic))
        l2.pack(side="left")
        tk.Button(fr, text=self.tt("setColor,selColor"),
                  command=lambda: self.chooseColor(l2, key, self._safe_color(ic))).pack(side="left")

    def _safe_color(self, c):
        try:
            self.root.winfo_rgb(c)
            return c
        except tk.TclError:
            return "black"

    def _pack_entry(self, parent, name, text, var):
        fr = tk.Frame(parent, name=name)
        fr.pack(anchor="w")
        tk.Label(fr, text=text, width=20, anchor="w").pack(side="left")
        tk.Entry(fr, textvariable=var, width=6).pack(side="left")

    def packEntryPower(self, parent, name, text, key):
        self._pack_entry(parent, name, text, "power(%s)" % key)

    def packEntryF0(self, parent, name, text, key):
        self._pack_entry(parent, name, text, "f0(%s)" % key)

    # ------------------------------------------------------------------
    # settings window

    def settings(self):
        v, f0, power, t = self.v, self.f0, self.power, self.tt
        if self.isExist(self.swindow):
            return
        w = self._toplevel(self.swindow, t("settings,title"))
        w.resizable(0, 0)
        w.bind("<Escape>", lambda e: w.destroy())
        if self.fix("F05"):
            bk = {"v": v.snapshot(SETTINGS_KEYS["v"]), "power": power.snapshot(SETTINGS_KEYS["power"]),
                  "f0": f0.snapshot(SETTINGS_KEYS["f0"])}
        else:
            bk = {"v": v.snapshot(), "power": power.snapshot(), "f0": f0.snapshot()}

        frame1 = tk.Frame(w, name="l")
        frame1.pack(side="left", anchor="n", fill="y", padx=2, pady=2)
        lf1 = tk.LabelFrame(frame1, name="lf1", text=t("settings,wave"), relief="groove", padx=5, pady=5)
        lf1.pack(anchor="w", fill="x")
        cw = tk.Frame(lf1, name="f4w")
        self.setColor(cw, "wavColor", t("settings,waveColor"))
        cw.pack(anchor="nw")

        digits = self._vcmd(lambda P: re.match(r"^[0-9]*$", P) is not None)
        fs = tk.Frame(lf1, name="fs")
        fs.pack(anchor="w")
        tk.Label(fs, text=t("settings,waveScale"), width=35, anchor="w").pack(side="left")
        tk.Entry(fs, textvariable="v(waveScale)", width=6, validate="key", validatecommand=digits).pack(side="left")
        f20 = tk.Frame(lf1, name="f20")
        f20.pack(anchor="w")
        tk.Label(f20, text=t("settings,sampleRate"), width=35, anchor="w").pack(side="left")
        tk.Entry(f20, textvariable="v(sampleRate)", width=6, validate="key", validatecommand=digits).pack(side="left")

        lf2 = tk.LabelFrame(frame1, name="lf2", text=t("settings,spec"), relief="groove", padx=5, pady=5)
        lf2.pack(anchor="w", fill="x")

        def row(parent, name):
            fr = tk.Frame(parent, name=name)
            fr.pack(anchor="w")
            return fr
        r = row(lf2, "f45")
        tk.Label(r, text=t("settings,specColor"), width=20, anchor="w").pack(side="left")
        tk.OptionMenu(r, TVar(r, "v(cmap)"), "grey", "color1", "color2").pack(side="left")
        r = row(lf2, "f20")
        tk.Label(r, text=t("settings,maxFreq"), width=20, anchor="w").pack(side="left")
        self._linked_entry(r, "v(topfr)", width=6).pack(side="left")
        self._mkscale(r, variable="v(topfr)", orient="horizontal", from_=0, to=v.i("sampleRate") / 2,
                 showvalue=0).pack(side="left")
        r = row(lf2, "f30")
        tk.Label(r, text=t("settings,brightness"), width=20, anchor="w").pack(side="left")
        self._linked_entry(r, "v(brightness)", width=6).pack(side="left")
        self._mkscale(r, variable="v(brightness)", orient="horizontal", from_=-100, to=100, resolution=0.1,
                 showvalue=0).pack(side="left")
        r = row(lf2, "f31")
        tk.Label(r, text=t("settings,contrast"), width=20, anchor="w").pack(side="left")
        self._linked_entry(r, "v(contrast)", width=6).pack(side="left")
        self._mkscale(r, variable="v(contrast)", orient="horizontal", from_=-100, to=100, resolution=0.1,
                 showvalue=0).pack(side="left")
        r = row(lf2, "f32")
        tk.Label(r, text=t("settings,fftLength"), width=20, anchor="w").pack(side="left")
        tk.OptionMenu(r, TVar(r, "v(fftlen)"), *[str(2 ** i) for i in range(3, 13)]).pack(side="left")
        r = row(lf2, "f33")
        tk.Label(r, text=t("settings,fftWinLength"), width=20, anchor="w").pack(side="left")
        self._linked_entry(r, "v(winlen)", width=6).pack(side="left")
        self._mkscale(r, variable="v(winlen)", orient="horizontal", from_=8, to=4096, showvalue=0).pack(side="left")
        r = row(lf2, "f34")
        tk.Label(r, text=t("settings,fftPreemph"), width=20, anchor="w").pack(side="left")
        tk.Entry(r, textvariable="v(preemph)", width=6).pack(side="left")
        r = row(lf2, "f35")
        tk.Label(r, text=t("settings,fftWinKind"), width=20, anchor="w").pack(side="left")
        tk.OptionMenu(r, TVar(r, "v(window)"), "Hamming", "Hanning", "Bartlett", "Blackman", "Rectangle").pack(side="left")

        lf3 = tk.LabelFrame(frame1, name="lf3", text=t("settings,pow"), relief="groove", padx=5, pady=5)
        lf3.pack(anchor="w", fill="x")
        cp = tk.Frame(lf3, name="f4p")
        self.setColor(cp, "powcolor", t("settings,powColor"))
        cp.pack(anchor="nw")
        self.packEntryPower(lf3, "ffl", t("settings,powLength"), "frameLength")
        self.packEntryPower(lf3, "fem", t("settings,powPreemph"), "preemphasis")
        self.packEntryPower(lf3, "fwl", t("settings,winLength"), "windowLength")
        r = row(lf3, "fwn")
        tk.Label(r, text=t("settings,powWinKind"), width=20, anchor="w").pack(side="left")
        tk.OptionMenu(r, TVar(r, "power(window)"), "Hamming", "Hanning", "Bartlett", "Blackman",
                      "Rectangle").pack(side="left")

        frame2 = tk.Frame(w, name="r")
        frame2.pack(side="left", anchor="n", fill="both", expand=True, padx=2, pady=2)
        lf4 = tk.LabelFrame(frame2, name="lf4", text=t("settings,f0"), relief="groove", padx=5, pady=5)
        lf4.pack(anchor="w", fill="x")
        cf = tk.Frame(lf4, name="f4f")
        self.setColor(cf, "f0color", t("settings,f0Color"))
        cf.pack(anchor="nw")
        r = row(lf4, "p1")
        tk.Label(r, text=t("settings,f0Argo"), width=20, anchor="w").pack(side="left")
        tk.OptionMenu(r, TVar(r, "f0(method)"), "ESPS", "AMDF").pack(side="left")
        self.packEntryF0(lf4, "p2", t("settings,f0Length"), "frameLength")
        self.packEntryF0(lf4, "p3", t("settings,f0WinLength"), "windowLength")
        self.packEntryF0(lf4, "p4", t("settings,f0Max"), "max")
        self.packEntryF0(lf4, "p5", t("settings,f0Min"), "min")
        r = row(lf4, "p6")
        tk.Label(r, text=t("settings,f0Unit"), width=20, anchor="w").pack(side="left")
        tk.OptionMenu(r, TVar(r, "f0(unit)"), "Hz", "semitone").pack(side="left")
        tk.Checkbutton(lf4, name="p8cb", text=t("settings,grid"), variable="f0(showToneLine)",
                       onvalue=1, offvalue=0, anchor="w").pack(anchor="w", fill="x")
        p7cb = tk.Checkbutton(lf4, name="p7cb", text=t("settings,f0FixRange"), variable="f0(fixShowRange)",
                              onvalue=1, offvalue=0, anchor="w")
        p7 = tk.LabelFrame(lf4, name="p7", labelwidget=p7cb, relief="ridge", padx=5, pady=5)
        p7.pack(anchor="w", fill="x")
        self.packToneList(p7, "tl1", t("settings,f0FixRange,h"), "showMaxTone", "showMaxOctave", "showMaxTmp", 10, "checkVol")
        self.packToneList(p7, "tl2", t("settings,f0FixRange,l"), "showMinTone", "showMinOctave", "showMinTmp", 10, "checkVol")
        p9cb = tk.Checkbutton(lf4, name="p9cb", text=t("settings,target"), variable="f0(showTgtLine)",
                              onvalue=1, offvalue=0, anchor="w")
        p9 = tk.LabelFrame(lf4, name="p9", labelwidget=p9cb, relief="ridge", padx=5, pady=5)
        p9.pack(anchor="w", fill="x")
        self.packToneList(p9, "tl", t("settings,targetTone"), "tgtTone", "tgtOctave", "tgtFreqTmp", 10, "checkVol")
        self.setColor(p9, "tgtf0color", t("settings,targetColor"))
        tk.Label(p9, text=t("settings,autoSetting"), anchor="nw").pack(side="left")
        tk.Button(p9, text=t(".confm.run"), command=self.autoF0Settings).pack(side="left")

        f0["showMaxTmp"] = self.tone2freq(f0["showMaxTone"] + f0["showMaxOctave"])
        f0["showMinTmp"] = self.tone2freq(f0["showMinTone"] + f0["showMinOctave"])
        f0["tgtFreqTmp"] = self.tone2freq(f0["tgtTone"] + f0["tgtOctave"])

        def calc(name1, name2, op):
            if name2 in ("showMaxTone", "showMaxOctave"):
                f0["showMaxTmp"] = self.tone2freq(f0["showMaxTone"] + f0["showMaxOctave"])
            elif name2 in ("showMinTone", "showMinOctave"):
                f0["showMinTmp"] = self.tone2freq(f0["showMinTone"] + f0["showMinOctave"])
            elif name2 in ("tgtTone", "tgtOctave"):
                f0["tgtFreqTmp"] = self.tone2freq(f0["tgtTone"] + f0["tgtOctave"])
        cmd = self.root.register(calc)
        self.tk.call("trace", "add", "variable", "f0", "write", cmd)

        def remove(e):
            if str(e.widget) == self.swindow:
                try:
                    self.tk.call("trace", "remove", "variable", "f0", "write", cmd)
                except tk.TclError:
                    pass
        w.bind("<Destroy>", remove)

        def apply_values():
            if not re.match(r"^[0-9]+$", v["waveScale"]):
                v["waveScale"] = bk["v"].get("waveScale", 32768)
            if not re.match(r"^[0-9]+$", v["sampleRate"]):
                v["sampleRate"] = bk["v"].get("sampleRate", 44100)
            if str(v["sampleRate"]) != str(bk["v"].get("sampleRate")):
                if not self.fix("F13"):
                    # Snack: 'snd configure -rate' relabels the current sound
                    self.snd.rate = v.i("sampleRate")
            f0["tgtFreq"] = self.tone2freq(f0["tgtTone"] + f0["tgtOctave"])
            if f0.i("fixShowRange"):
                f0["showMin"] = self.tone2freq(f0["showMinTone"] + f0["showMinOctave"])
                f0["showMax"] = self.tone2freq(f0["showMaxTone"] + f0["showMaxOctave"])
            self.Redraw("all")

        def cancel():
            v.restore(bk["v"])
            power.restore(bk["power"])
            f0.restore(bk["f0"])
            self.Redraw("all")
            w.destroy()

        def apply():
            apply_values()
            if self.fix("F05"):
                bk["v"] = v.snapshot(SETTINGS_KEYS["v"])
                bk["power"] = power.snapshot(SETTINGS_KEYS["power"])
                bk["f0"] = f0.snapshot(SETTINGS_KEYS["f0"])
            else:
                bk["v"] = v.snapshot()
                bk["power"] = power.snapshot()
                bk["f0"] = f0.snapshot()

        def ok():
            apply_values()
            w.destroy()
        fb = tk.Frame(frame2, name="f")
        fb.pack(anchor="e", side="bottom", padx=2, pady=2)
        tk.Button(fb, text=t(".confm.c"), command=cancel).pack(side="right")
        tk.Button(fb, text=t(".confm.apply"), command=apply).pack(side="right")
        tk.Button(fb, text=t(".confm.ok"), width=6, command=ok).pack(side="right")

    def autoF0Settings(self):
        v, f0 = self.v, self.f0
        tgtFreq = self.tone2freq(f0["tgtTone"] + f0["tgtOctave"])
        f0["max"] = int(tgtFreq * 2.1)
        f0["min"] = int(tgtFreq / 2.2) if tgtFreq >= 260 else 60
        f0["fixShowRange"] = 1
        tone, octv = self.calcTone(f0["tgtTone"], f0.i("tgtOctave"), 2)
        f0["showMaxTone"], f0["showMaxOctave"] = tone, octv
        if octv > v.i("sinScaleMax"):
            f0["showMaxOctave"] = v.i("sinScaleMax")
            f0["showMaxTone"] = TONE_LIST[-1]
        tone, octv = self.calcTone(f0["tgtTone"], f0.i("tgtOctave"), -2)
        f0["showMinTone"], f0["showMinOctave"] = tone, octv
        if octv < v.i("sinScaleMin"):
            f0["showMinOctave"] = v.i("sinScaleMin")
            f0["showMinTone"] = TONE_LIST[0]
        f0["showMin"] = self.tone2freq(f0["showMinTone"] + f0["showMinOctave"])
        f0["showMax"] = self.tone2freq(f0["showMaxTone"] + f0["showMaxOctave"])

    def calcTone(self, tone, octave, add):
        i = TONE_LIST.index(tone) if tone in TONE_LIST else len(TONE_LIST)
        seq = i + add
        while seq >= len(TONE_LIST):
            octave += 1
            seq -= 12
        while seq < 0:
            octave -= 1
            seq += 12
        return TONE_LIST[seq], octave

    # ------------------------------------------------------------------
    # audio I/O settings

    def paRecRun(self, quiet=False):
        if self.pa_rec_on:
            return 0
        devs = [audio.pa_device_label(d) for d in audio.list_devices("input")]
        self.paDev["devList"] = devs if devs else ["none"]
        menu = getattr(self, "_pa_in_menu", None)
        if menu is not None and menu.winfo_exists():
            menu.delete(0, "end")
            for d in (devs or ["none"]):
                menu.add_radiobutton(variable="paDev(in)", label=d, value=d)
        if not devs:
            if not quiet:
                messagebox.showwarning(self.tt(".confm.errTitle"), self.tt("paRecRun,errDev"))
            return 1
        if self.paDev["in"] == "none" or self.paDev["in"] not in devs:
            if self.paDev["in"] == "none":
                self.paDev["in"] = devs[0]
        self.pa_rec_on = True
        self.updateIoSettings()
        return 0

    def paPlayRun(self, quiet=False):
        if self.pa_play_on:
            return 0
        devs = [audio.pa_device_label(d) for d in audio.list_devices("output")]
        self.paDev["outdevList"] = devs if devs else ["none"]
        menu = getattr(self, "_pa_out_menu", None)
        if menu is not None and menu.winfo_exists():
            menu.delete(0, "end")
            for d in (devs or ["none"]):
                menu.add_radiobutton(variable="paDev(out)", label=d, value=d)
        if not devs:
            if not quiet:
                messagebox.showwarning(self.tt(".confm.errTitle"), self.tt("paPlayRun,errDev"))
            return 1
        if self.paDev["out"] == "none":
            self.paDev["out"] = devs[0]
        self.pa_play_on = True
        self.updateIoSettings()
        return 0

    def paRecTerminate(self):
        if self.pa_rec_on:
            self.pa_rec_on = False
            self.updateIoSettings()

    def paPlayTerminate(self):
        self.pa_play_on = False
        self.updateIoSettings()

    def updateIoSettings(self):
        if not self.isExist(self.ioswindow):
            return
        normal, black, disabled, gray = [], [], [], []
        if self.pa_rec_on:
            normal += ["pf.in", "pf.esr", "pf.fmt", "pf.ech", "pf.ebs"]
            black += ["pf.lin", "pf.lsr", "pf.lbt", "pf.lch", "pf.lbs"]
            disabled += ["sf.f1.in", "sf.f3.e", "sf.f3.s", "sf.f6.e"]
            gray += ["sf.f1.lin", "sf.f3.l", "sf.f6.l", "sf.f6.u"]
        else:
            disabled += ["pf.in", "pf.ech"]
            gray += ["pf.lin", "pf.lch"]
            normal += ["sf.f1.in", "sf.f3.e", "sf.f3.s", "sf.f5.e", "sf.f6.e"]
            black += ["sf.f1.lin", "sf.f3.l", "sf.f5.l", "sf.f5.u", "sf.f6.l", "sf.f6.u"]
        if self.pa_play_on:
            normal += ["pf.out", "pf.esr", "pf.fmt", "pf.ebs"]
            black += ["pf.lout", "pf.lsr", "pf.lbt", "pf.lbs"]
            disabled += ["sf.f2.out", "sf.f4.l", "sf.f4.e", "sf.f4.s", "sf.f7.e"]
            gray += ["sf.f2.l", "sf.f4.l", "sf.f6.u", "sf.f7.u", "sf.f7.l"]
        else:
            disabled += ["pf.out"]
            gray += ["pf.lout"]
            normal += ["sf.f2.out", "sf.f4.l", "sf.f4.e", "sf.f4.s", "sf.f5.e", "sf.f7.e"]
            black += ["sf.f2.l", "sf.f4.l", "sf.f5.l", "sf.f5.u", "sf.f6.u", "sf.f7.u", "sf.f7.l"]
        if not self.pa_rec_on and not self.pa_play_on:
            disabled += ["pf.esr", "pf.fmt", "pf.ech", "pf.ebs"]
            gray += ["pf.lsr", "pf.lbt", "pf.lch", "pf.lbs"]
        if self.pa_rec_on and self.pa_play_on:
            disabled += ["sf.f5.e"]
            gray += ["sf.f5.l", "sf.f5.u"]
        base = self.ioswindow

        def cfg(p, **kw):
            try:
                self.root.nametowidget("%s.%s" % (base, p)).configure(**kw)
            except (KeyError, tk.TclError):
                pass
        for p in black:
            cfg(p, fg="black")
        for p in normal:
            cfg(p, state="normal")
        for p in disabled:
            cfg(p, state="disabled")
        for p in gray:
            cfg(p, fg="#a0a0a0")
        self._update_io_alias()

    def setIODevice(self):
        t, pa, dev = self.tt, self.paDev, self.dev
        if pa.i("useRequestRec") and not self.pa_rec_on:
            if self.paRecRun():
                return 1
        elif not pa.i("useRequestRec") and self.pa_rec_on:
            self.paRecTerminate()
        if pa.i("useRequestPlay") and not self.pa_play_on:
            if self.paPlayRun():
                return 1
        elif not pa.i("useRequestPlay") and self.pa_play_on:
            self.paPlayTerminate()

        def check_common(err2):
            dID = self._pa_device("input" if err2 == "setIODevice,errPa2" else "output")
            if dID is None:
                messagebox.showwarning(t(".confm.errTitle"), t(err2))
                return None
            for key, err in (("channel", "setIODevice,errPa3"), ("sampleRate", "setIODevice,errPa4"),
                             ("bufferSize", "setIODevice,errPa5")):
                pa[key] = pa[key].strip()
                if not re.match(r"^[0-9]+$", pa[key]):
                    messagebox.showwarning(t(".confm.errTitle"), t(err))
                    return None
            return dID
        if pa.i("useRequestRec"):
            dID = check_common("setIODevice,errPa2")
            if dID is None:
                return 1
            fmt = pa.get("sampleFormat", "Int16")
            err = audio.check_settings("input", dID, pa.i("sampleRate"), max(1, pa.i("channel")),
                                       audio.FORMAT_DTYPE.get(fmt, "int16"))
            if err:
                messagebox.showwarning(t(".confm.errTitle"), "%s\n%s" % (t("setIODevice,errPa"), err))
                return 1
        pa["useRec"] = pa.i("useRequestRec")
        if pa.i("useRequestPlay"):
            dID = check_common("setIODevice,errPaOut2")
            if dID is None:
                return 1
            fmt = pa.get("sampleFormat", "Int16")
            err = audio.check_settings("output", dID, pa.i("sampleRate"), 1, "float32")
            if err:
                messagebox.showwarning(t(".confm.errTitle"), "%s\n%s" % (t("setIODevice,errPa"), err))
                return 1
        pa["usePlay"] = pa.i("useRequestPlay")
        self.readWavFile()
        return 0

    def ioSettings(self):
        t, dev, pa = self.tt, self.dev, self.paDev
        if self.isExist(self.ioswindow):
            return
        w = self._toplevel(self.ioswindow, t("ioSettings,title"))
        w.resizable(0, 0)
        w.bind("<Escape>", lambda e: w.destroy())
        dev_bk = dev.snapshot()
        pa_bk = pa.snapshot()
        req_bk = {"rec": self.pa_rec_on, "play": self.pa_play_on}

        sf = tk.LabelFrame(w, name="sf", text="Snack (MME)", relief="groove", padx=5, pady=5)
        sf.pack(fill="both", expand=False)
        ins = [d[1] for d in audio.mme_devices("input")] or ["none"]
        outs = [d[1] for d in audio.mme_devices("output")] or ["none"]
        f1 = tk.Frame(sf, name="f1")
        tk.Label(f1, name="lin", text=t("ioSettings,inDev"), width=12, anchor="w").pack(side="left")
        tk.OptionMenu(f1, TVar(f1, "dev(in)"), *ins).pack(side="left")
        f1.pack(anchor="w")
        f2 = tk.Frame(sf, name="f2")
        tk.Label(f2, name="l", text=t("ioSettings,outDev"), width=12, anchor="w").pack(side="left")
        tk.OptionMenu(f2, TVar(f2, "dev(out)"), *outs).pack(side="left")
        f2.pack(anchor="w")

        def gain_row(name, label, key):
            fr = tk.Frame(sf, name=name)
            tk.Label(fr, name="l", text=t(label), width=32, anchor="w").pack(side="left")
            self._linked_entry(fr, "dev(%s)" % key, name="e", width=6).pack(side="left")
            self._mkscale(fr, name="s", variable="dev(%s)" % key, orient="horizontal", from_=0, to=100,
                     resolution=1, showvalue=0).pack(side="left")
            fr.pack(anchor="w")
        gain_row("f3", "ioSettings,inGain", "ingain")
        gain_row("f4", "ioSettings,outGain", "outgain")

        def unit_row(name, label, key, unit):
            fr = tk.Frame(sf, name=name)
            tk.Label(fr, name="l", text=t(label), width=32, anchor="w").pack(side="left")
            tk.Entry(fr, name="e", textvariable="dev(%s)" % key, width=6).pack(side="left")
            tk.Label(fr, name="u", text=unit).pack(side="left")
            fr.pack(anchor="w")
        unit_row("f5", "ioSettings,latency", "latency", "(msec)")
        unit_row("f6", "ioSettings,sndBuffer", "sndBuffer", "(sample)")
        unit_row("f7", "ioSettings,bgmBuffer", "bgmBuffer", "(sample)")

        pa["useRequestRec"] = 1 if self.pa_rec_on else 0
        pa["useRequestPlay"] = 1 if self.pa_play_on else 0
        pal = tk.Frame(w, name="pa")
        tk.Label(pal, text=t("ioSettings,portaudio")).pack(side="left")

        def req_rec():
            if pa.i("useRequestRec"):
                if self.paRecRun():
                    pa["useRequestRec"] = 0
            else:
                self.paRecTerminate()
                pa["in"] = "none"

        def req_play():
            if pa.i("useRequestPlay"):
                if self.paPlayRun():
                    pa["useRequestPlay"] = 0
            else:
                self.paPlayTerminate()
                pa["out"] = "none"
        tk.Checkbutton(pal, variable="paDev(useRequestRec)", text=t("ioSettings,useRequestRec"),
                       command=req_rec).pack(side="left")
        tk.Checkbutton(pal, variable="paDev(useRequestPlay)", text=t("ioSettings,useRequestPlay"),
                       command=req_play).pack(side="left")
        pf = tk.LabelFrame(w, name="pf", labelwidget=pal, relief="groove", padx=5, pady=5, labelanchor="nw")
        pf.pack(fill="both", expand=False)
        tk.Label(pf, name="lin", text=t("ioSettings,inDev"), anchor="w").grid(row=0, column=0, sticky="w")
        om_in = tk.OptionMenu(pf, TVar(pf, "paDev(in)"), "none")
        om_in.grid(row=0, column=1, sticky="w", columnspan=2)
        self._pa_in_menu = om_in.nametowidget(om_in.menuname)
        self._pa_in_menu.delete(0, "end")
        for d in pa.lst("devList"):
            self._pa_in_menu.add_radiobutton(variable="paDev(in)", label=d, value=d)
        tk.Label(pf, name="lout", text=t("ioSettings,outDev"), anchor="w").grid(row=1, column=0, sticky="w")
        om_out = tk.OptionMenu(pf, TVar(pf, "paDev(out)"), "none")
        om_out.grid(row=1, column=1, sticky="w", columnspan=2)
        self._pa_out_menu = om_out.nametowidget(om_out.menuname)
        self._pa_out_menu.delete(0, "end")
        for d in pa.lst("outdevList"):
            self._pa_out_menu.add_radiobutton(variable="paDev(out)", label=d, value=d)
        intv = self._vcmd(lambda P: P == "" or re.match(r"^\s*[+-]?[0-9]+\s*$", P) is not None)
        tk.Label(pf, name="lsr", text=t("ioSettings,sampleRate"), anchor="w").grid(row=2, column=0, sticky="w")
        tk.Entry(pf, name="esr", textvariable="paDev(sampleRate)", width=6, validate="key",
                 validatecommand=intv).grid(row=2, column=1, sticky="w")
        tk.Label(pf, name="lbt", text=t("ioSettings,format"), anchor="w").grid(row=3, column=0, sticky="w")
        om_fmt = tk.OptionMenu(pf, TVar(pf, "paDev(sampleFormat)"), "Int16", "Int24", "Int32", "Float32")
        om_fmt.grid(row=3, column=1, sticky="w")
        tk.Label(pf, name="lch", text=t("ioSettings,inChannel"), anchor="w").grid(row=4, column=0, sticky="w")
        tk.Entry(pf, name="ech", textvariable="paDev(channel)", width=6, validate="key",
                 validatecommand=intv).grid(row=4, column=1, sticky="w")
        tk.Label(pf, name="lbs", text=t("ioSettings,bufferSize"), anchor="w").grid(row=5, column=0, sticky="w")
        tk.Entry(pf, name="ebs", textvariable="paDev(bufferSize)", width=6, validate="key",
                 validatecommand=intv).grid(row=5, column=1, sticky="w")
        # names used by updateIoSettings
        self._io_alias = {"pf.in": om_in, "pf.out": om_out, "pf.fmt": om_fmt}

        fb = tk.Frame(w, name="fb")

        def ok():
            if not self.setIODevice():
                w.destroy()
            else:
                w.lift()
                w.focus_set()

        def apply():
            if not self.setIODevice():
                dev_bk.clear()
                dev_bk.update(dev.snapshot())
                pa_bk.clear()
                pa_bk.update(pa.snapshot())
                req_bk["rec"], req_bk["play"] = self.pa_rec_on, self.pa_play_on
            else:
                w.lift()
                w.focus_set()

        def cancel():
            dev.restore(dev_bk)
            pa.restore(pa_bk)
            self.pa_rec_on, self.pa_play_on = req_bk["rec"], req_bk["play"]
            pa["useRequestRec"] = 1 if self.pa_rec_on else 0
            pa["useRequestPlay"] = 1 if self.pa_play_on else 0
            self.setIODevice()
            w.destroy()
        tk.Button(fb, text=t(".confm.ok"), width=8, command=ok).pack(side="left")
        tk.Button(fb, text=t(".confm.apply"), width=8, command=apply).pack(side="left")
        tk.Button(fb, text=t(".confm.c"), width=8, command=cancel).pack(side="left")
        fb.pack(anchor="w")
        fm = tk.Frame(w, name="fm")
        for k in ("ioSettings,comment0", "ioSettings,comment0b", "ioSettings,comment1", "ioSettings,comment2"):
            tk.Label(fm, fg="red", text=t(k)).pack(anchor="w", side="top")
        fm.pack(anchor="w")
        self.updateIoSettings()
        self._update_io_alias()
        w.lift()
        w.focus_set()

    def _update_io_alias(self):
        """OptionMenus get auto generated names in tkinter; apply the state
        that updateIoSettings computed for pf.in / pf.out / pf.fmt."""
        al = getattr(self, "_io_alias", {})
        rec, play = self.pa_rec_on, self.pa_play_on
        states = {"pf.in": rec, "pf.out": play, "pf.fmt": rec or play}
        for k, wdg in al.items():
            try:
                wdg.configure(state="normal" if states[k] else "disabled")
            except tk.TclError:
                pass
        try:
            f1 = self.root.nametowidget(self.ioswindow + ".sf.f1")
            f2 = self.root.nametowidget(self.ioswindow + ".sf.f2")
            for fr, on in ((f1, not rec), (f2, not play)):
                for ch in fr.winfo_children():
                    if isinstance(ch, tk.Menubutton):
                        ch.configure(state="normal" if on else "disabled")
        except (KeyError, tk.TclError):
            pass

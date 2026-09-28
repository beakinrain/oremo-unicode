"""oto.ini generation (port of proc-genParam.tcl)."""

import os
import re
import time
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

import numpy as np

from . import audio, dsp, textenc
from .state import TVar

VA = set("あかさたなはまやらわがざだばぱゃぁゎアカサタナハマヤラワガザダバパャァヮ")
VI = set("いきしちにひみりぎじぢびぴぃゐイキシチニヒミリギジヂビピィヰ")
VU = set("うくすつぬふむゆるヴぐずづぶぷぅゅっウクスツヌフムユルグズヅブプゥュッ")
VE = set("えけせてねへめれげぜでべぺぇゑエケセテネヘメレゲゼデベペェヱ")
VO = set("おこそとのほもよろをごぞどぼぽょぉオコソトノホモヨロヲゴゾドボポョォ")
VN = set("んン")
KANA = VA | VI | VU | VE | VO | VN | set("゛゜°_") | set("ヴ")
NOT_MORA = set("ぁぃぅぇぉゃゅょゎっァィゥェォャュョヮッ゛゜°")


def cut6(val):
    return int(float(val) * 1000000) / 1000000.0


def cut3(val):
    return int(float(val) * 1000) / 1000.0


def num(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def fmt(val):
    """Tcl like number formatting for oto.ini output."""
    if isinstance(val, str):
        return val
    if isinstance(val, float):
        return repr(val)
    return str(val)


def getMorae(inMorae):
    morae = []
    for ch in inMorae:
        if ch in KANA:
            if ch not in NOT_MORA or not morae:
                morae.append(ch)
            else:
                morae[-1] += ch
    return morae


def getVowel(mora):
    if not mora:
        return ""
    ch = mora[-1]
    if ch in VA:
        return "a"
    if ch in VI:
        return "i"
    if ch in VU:
        return "u"
    if ch in VE:
        return "e"
    if ch in VO:
        return "o"
    if ch in VN:
        return "n"
    if ch == "_":
        return "-"
    return ""


def getRenAlias(morae, i):
    mora = morae[i]
    prev = "-" if i == 0 else getVowel(morae[i - 1])
    return "%s %s" % (prev, mora)


def kind2c(k):
    return {"S": 1, "O": 2, "P": 3, "C": 4, "E": 5}.get(k, "")


def c2kind(c):
    return {1: "S", 2: "O", 3: "P", 4: "C", 5: "E"}.get(c, "")


class GenParamMixin:

    @staticmethod
    def sec2samp(sec, length):
        sec, length = str(sec), str(length)
        if sec.strip() == "" or length.strip() == "":
            return 0
        try:
            return int(float(sec) / float(length))
        except (ValueError, ZeroDivisionError):
            return -1

    # ------------------------------------------------------------------

    def checkWavForOREMO(self):
        """Returns False when the user pressed Cancel."""
        v = self.v
        if v.i("recStatus"):
            act = self.tk_dialog(".confm", self.tt(".confm"), self.tt("checkWavForOREMO,saveQ"), "question", 2,
                                 self.tt("checkWavForOREMO,saveA1"), self.tt("checkWavForOREMO,saveA2"),
                                 self.tt("checkWavForOREMO,saveA3"))
            if act == 2:
                return False if self.fix("F15") else None
            elif act == 0:
                self.saveWavFile()
        return True

    # ------------------------------------------------------------------
    # renzoku (continuous) oto.ini generation window

    def genParam(self):
        g, t = self.genParamA, self.tt
        if self.isExist(self.genWindow):
            return
        w = tk.Toplevel(self.root, name=self.genWindow[1:])
        w.title(t("genParam,title"))
        w.bind("<Escape>", lambda e: w.destroy())
        frames = []

        f = tk.LabelFrame(w, relief="groove", padx=5, pady=5)
        tk.Label(f, text=t("genParam,tempo")).grid(row=0, column=0, sticky="nse")
        tk.Entry(f, textvariable="genParam(bpm)", width=10).grid(row=0, column=1, sticky="nse")
        tk.Label(f, text=t("genParam,bpm")).grid(row=0, column=2, sticky="nsw", columnspan=2)
        tk.Label(f, text=t("genParam,S")).grid(row=1, column=0, sticky="nse")
        tk.Entry(f, textvariable="genParam(S)", width=10).grid(row=1, column=1, sticky="nse")
        tk.Label(f, text=t("genParam,unit")).grid(row=1, column=2, sticky="nsw")
        tk.OptionMenu(f, TVar(f, "genParam(SU)"), "msec", t("genParam,haku")).grid(row=1, column=3, sticky="nsw")
        frames.append(f)

        f = tk.Frame(w, padx=5, pady=0)
        tk.Label(f, text=t("genParam,darrow")).grid(row=0, column=0, sticky="nsew")
        tk.Button(f, text=t("genParam,bInit"), command=self.initGenParam).grid(row=1, column=0, sticky="nsew")
        tk.Label(f, text=t("genParam,darrow")).grid(row=2, column=0, sticky="nsew")
        frames.append(f)

        f = tk.LabelFrame(w, relief="groove", padx=5, pady=5)
        for r, k in enumerate("OPCE"):
            tk.Label(f, text=t("genParam,%s" % k)).grid(row=r, column=0, sticky="nse")
            tk.Entry(f, textvariable="genParam(%s)" % k, width=10).grid(row=r, column=1, sticky="nse")
            tk.Label(f, text=t("genParam,msec")).grid(row=r, column=2, sticky="nse")
        frames.append(f)

        f = tk.LabelFrame(w, relief="groove", padx=5, pady=5)
        tk.Checkbutton(f, variable="genParam(autoAdjustRen)", text=t("genParam,autoAdjustRen")).grid(
            row=0, column=0, sticky="nsw", columnspan=3)
        tk.Label(f, text=t("genParam,vLow")).grid(row=1, column=0, sticky="nse")
        tk.Entry(f, textvariable="genParam(vLow)", width=10).grid(row=1, column=1, sticky="nse")
        tk.Label(f, text=t("genParam,db")).grid(row=1, column=2, sticky="nsw")
        tk.Label(f, text=t("genParam,sRange")).grid(row=2, column=0, sticky="nse")
        tk.Entry(f, textvariable="genParam(sRange)", width=10).grid(row=2, column=1, sticky="nse")
        tk.Label(f, text=t("genParam,msec")).grid(row=2, column=2, sticky="nsw")
        tk.Label(f, text=t("genParam,f0pow")).grid(row=3, column=0, sticky="nsw", columnspan=3)
        frames.append(f)

        f = tk.LabelFrame(w, relief="groove", padx=5, pady=5)
        tk.Checkbutton(f, variable="genParam(autoAdjustRen2)", text=t("genParam,autoAdjustRen2")).grid(
            row=0, column=0, sticky="nsw", columnspan=3)
        tk.Label(f, text=t("genParam,autoAdjustRen2Opt")).grid(row=1, column=0, sticky="nse")
        tk.Entry(f, textvariable="genParam(autoAdjustRen2Opt)", width=35).grid(row=1, column=1, sticky="nsew", columnspan=2)
        tk.Label(f, text=t("genParam,autoAdjustRen2Pattern")).grid(row=2, column=0, sticky="nse")
        tk.Entry(f, textvariable="genParam(autoAdjustRen2Pattern)", width=35).grid(row=2, column=1, sticky="nsew", columnspan=2)
        frames.append(f)

        f = tk.LabelFrame(w, relief="groove", padx=5, pady=5)
        g["useAliasMax"] = 0
        g["aliasMax"] = 0
        tk.Label(f, text=t("genParam,aliasMax")).grid(row=0, column=0, sticky="nsw")
        tk.Radiobutton(f, variable="genParam(useAliasMax)", value=0, text=t("genParam,aliasMaxNo")).grid(
            row=1, column=0, sticky="nsw")
        tk.Radiobutton(f, variable="genParam(useAliasMax)", value=1, text=t("genParam,aliasMaxYes")).grid(
            row=1, column=1, sticky="nsw")
        tk.Label(f, text=t("genParam,aliasMaxNum")).grid(row=2, column=0, sticky="nse")
        tk.Entry(f, textvariable="genParam(aliasMax)", width=10).grid(row=2, column=1, sticky="nse")
        frames.append(f)

        f = tk.Frame(w, padx=5, pady=0)

        def do():
            if not self._bpm_ok():
                return
            self.doGenParamForOREMO()
            self.v["paramFile"] = self.v["saveDir"] + "/oto.ini"
            self.saveParamFile()
            w.destroy()
        tk.Label(f, text=t("genParam,darrow")).grid(row=0, column=0, columnspan=2, sticky="nsew")
        tk.Button(f, text=t("genParam,do"), command=do).grid(row=1, column=0, sticky="nsew")
        tk.Button(f, text=t(".confm.c"), command=w.destroy).grid(row=1, column=1, sticky="nsew")
        frames.append(f)
        for f in frames:
            f.pack(anchor="nw", padx=2, pady=2, expand=1, fill="x")
        w.lift()
        w.focus_set()

    def _bpm_ok(self):
        if self.genParamA.f("bpm", 0.0) <= 0:
            messagebox.showwarning(self.tt(".confm.errTitle"), "%s bpm > 0" % self.tt("genParam,tempo"))
            return False
        return True

    def initGenParam(self):
        g = self.genParamA
        if not self._bpm_ok():
            return
        mspb = 60000.0 / g.f("bpm")
        g["O"] = cut3(mspb / 6.0)
        g["P"] = cut3(mspb / 2.0)
        g["C"] = cut3(mspb * 3.0 / 4.0)
        g["E"] = cut3(-(mspb + g.f("O")))
        g["sRange"] = g["P"]

    # ------------------------------------------------------------------

    def _read_work(self, fname):
        """Read a wav as mono work sound (sWork). Cached per file name."""
        cache = getattr(self, "_work_cache", None)
        if cache is not None and cache[0] == fname:
            return cache[1]
        s = audio.Sound()
        s.read(fname)
        if s.channels > 1:
            s.set_data(s.mono().reshape(-1, 1))
        self._work_cache = (fname, s)
        return s

    def autoAdjustRen(self, fid, Porg, rng):
        v, f0, power, g = self.v, self.f0, self.power, self.genParamA
        fn = "%s/%s.%s" % (v["saveDir"], fid, v["ext"])
        if not os.path.exists(fn):
            return 0.0
        sw = self._read_work(fn)
        v["sndLength"] = sw.length_sec()
        x = sw.mono()
        sr = self._calc_rate(sw.rate)
        Lsec = Porg - rng if Porg > rng else 0
        start = int(Lsec * sr)
        end = int((Porg + rng) * sr)
        try:
            series = dsp.pitch(x[start:end], sw.rate, f0["method"], frame_length=f0.f("frameLength"),
                               window_length=f0.f("windowLength"), maxpitch=f0.f("max"), minpitch=f0.f("min"))
        except Exception as e:
            self.log("error: %s" % e)
            series = []
        f0old = 1
        i = 0
        found = False
        for i, f in enumerate(series):
            if f0old <= 0 and f > 0:
                found = True
                break
            f0old = f
        if found:
            Pnew = i * dsp._clampf(f0.f("frameLength"), 0.001, 0.5, 0.01) + Lsec
            Lsec = Pnew
            start = int(Lsec * sr)
        else:
            Pnew = Porg
        pw = dsp.power(x, sw.rate, power.f("frameLength"), power["window"], power.f("preemphasis"),
                       int(power.f("windowLength") * sr), start, end)
        Nmax = 30
        N = 0
        aveP = 0.0
        for i in range(min(len(pw), Nmax)):
            aveP += pw[i]
            N += 1
        if N > 0:
            aveP /= N
        vLow = aveP - g.f("vLow")
        powOld = vLow
        pn = -1
        pnMin = 10001
        powNowMin = 10000
        for i, powNow in enumerate(pw):
            if powNow < powNowMin:
                powNowMin = powNow
            if powOld < vLow and powNow >= vLow and powNowMin < pnMin:
                pn = i
                pnMin = powNowMin
                powNowMin = 10000
            powOld = powNow
        if pn >= 0:
            Pnew = pn * dsp._clampf(power.f("frameLength"), 0.001, 1.0, 0.01) + Lsec
        g["avePPrev"] = aveP
        return Pnew - Porg

    def setSto0(self, r):
        pu = self.paramU
        S = num(pu[(r, 1)])
        if S < 0:
            pu[(r, 5)] = cut3(num(pu[(r, 5)]) - S)
            pu[(r, 4)] = cut3(num(pu[(r, 4)]) + S)
            pu[(r, 3)] = cut3(num(pu[(r, 3)]) + S)
            pu[(r, 2)] = cut3(num(pu[(r, 2)]) + S)
            if num(pu[(r, 2)]) < 0:
                pu[(r, 2)] = 0
            pu[(r, 1)] = 0

    def doGenParamForOREMO(self):
        v, g, t = self.v, self.genParamA, self.tt
        recList = []
        ext = "." + v["ext"].lower()
        try:
            names = os.listdir(v["saveDir"])
        except OSError:
            names = []
        for fn in names:
            if fn.lower().endswith(ext) and fn[:-len(ext)] != "":
                recList.append(fn[:-len(ext)])
        self.initParamS()
        self.initParamU(1)
        self._work_cache = None
        mspb = 60000.0 / g.f("bpm")
        if g["SU"] == "msec":
            Sstart = g.f("S")
        else:
            Sstart = g.f("S") * mspb
        self.initProgressWindow()
        procStart = time.time()
        aliasChoufuku = {}
        recListMax = len(recList)
        pu = self.paramU
        for recListSeq, fid in enumerate(recList):
            S = Sstart
            morae = getMorae(fid.lstrip("_"))
            g["avePPrev"] = 0
            first_row = self.paramUsize
            for i, mora in enumerate(morae):
                if mora == "_":
                    S += mspb
                    continue
                alias = getRenAlias(morae, i)
                if g.i("useAliasMax") and alias in aliasChoufuku:
                    aliasChoufuku[alias] += 1
                    if g.i("aliasMax") <= 0 or aliasChoufuku[alias] <= g.i("aliasMax"):
                        alias = "%s%d" % (alias, aliasChoufuku[alias])
                    else:
                        S += mspb
                        continue
                else:
                    aliasChoufuku[alias] = 1
                if g.i("autoAdjustRen"):
                    Psec = (S + g.f("P")) / 1000.0
                    rng = g.f("sRange") / 1000.0
                    S = cut3(S + 1000.0 * self.autoAdjustRen(fid, Psec, rng))
                n = self.paramUsize
                pu[(n, 0)] = fid
                pu[(n, 6)] = alias
                pu[(n, 1)] = S
                pu[(n, 4)] = g["C"]
                pu[(n, 5)] = g["E"]
                pu[(n, 3)] = g["P"]
                pu[(n, 2)] = g["O"]
                pu[(n, "R")] = recListSeq
                self.setSto0(n)
                S += mspb
                fname = "%s/%s.%s" % (v["saveDir"], fid, v["ext"])
                if os.path.exists(fname):
                    sw = self._read_work(fname)
                    v["sndLength"] = sw.length_sec()
                    self.paramU2paramS(n)
                self.paramUsize += 1
            if len(morae) <= 0:
                n = self.paramUsize
                pu[(n, 0)] = fid
                pu[(n, 6)] = ""
                for c in (1, 4, 5, 3, 2):
                    pu[(n, c)] = 0
                pu[(n, "R")] = recListSeq
                self.paramUsize += 1
            if g.i("autoAdjustRen2") and len(morae) > 0:
                if self.fix("F16"):
                    if self.paramUsize - 1 >= first_row:
                        self.autoAdjustRen2(first_row, self.paramUsize - 1)
                else:
                    self.autoAdjustRen2(self.paramUsize - len(morae), self.paramUsize - 1)
            remain = int((time.time() - procStart) * (recListMax - recListSeq) / (recListSeq + 1))
            self.updateProgressWindow(100 * recListSeq // max(1, len(recList)),
                                      "(%d / %d) (remain: %d sec)" % (recListSeq, recListMax, remain))
        self.deleteProgressWindow()
        self._work_cache = None
        v["msg"] = self.msg("doGenParam,doneMsg")

    def autoAdjustRen2(self, start, end):
        v, g, pu, ps = self.v, self.genParamA, self.paramU, self.paramS
        patstr = g["autoAdjustRen2Pattern"]
        pattern = patstr.split(" ")
        start = max(1, start)

        def alias_parts(r):
            a = str(pu.get((r, 6), ""))
            parts = a.split(" ")
            return parts[0], (parts[1] if len(parts) > 1 else "")
        if patstr != "":
            f = start
            while f <= end:
                m = getMorae(alias_parts(f)[1])
                if m and m[0] in pattern:
                    break
                f += 1
            if f > end:
                return
        f = start
        while f <= end:
            fid = pu[(f, 0)]
            fname = "%s/%s.%s" % (v["saveDir"], fid, v["ext"])
            positions = []
            d = 0
            i = f
            while i <= end and i < self.paramUsize and pu[(f, 0)] == pu[(i, 0)]:
                positions.append(ps.get((i, "E"), 0.0) * 0.25 + ps.get((i, "P"), 0.0) * 0.75)
                d += 1
                i += 1
            try:
                sw = self._read_work(fname)
                newP = dsp.modify_pre(sw.mono(), sw.rate, positions, g["autoAdjustRen2Opt"],
                                      sw.rate if self.fix("F06") else 44100)
            except Exception as e:
                self.log("modifyPre: %s" % e)
                newP = None
            if newP is not None:
                r = f
                for i, p in enumerate(newP):
                    ftmp = f + i
                    pre, rest = alias_parts(ftmp)
                    m = getMorae(rest)
                    mora = m[0] if m else ""
                    if patstr != "":
                        if pre == "-" or mora not in pattern or pre == getVowel(mora):
                            r += 1
                            continue
                    S = cut3((ps.get((r, "S"), 0.0) + p - ps.get((r, "P"), 0.0)) * 1000.0)
                    if S >= 0:
                        pu[(r, 1)] = S
                        self.paramU2paramS(r)
                    else:
                        pu[(r, 1)] = 0
                        pu[(r, 3)] = cut3(num(pu[(r, 3)]) + S)
                        self.paramU2paramS(r)
                    r += 1
            f += max(d, 1)

    # ------------------------------------------------------------------
    # tandoku (single) oto.ini estimation window

    def estimateParam(self):
        v, power, t = self.v, self.power, self.tt
        if self.isExist(self.epwindow):
            return
        top = tk.Toplevel(self.root, name=self.epwindow[1:])
        top.title(t("estimateParam,title"))
        top.resizable(0, 0)
        top.bind("<Escape>", lambda e: top.destroy())
        w = tk.Frame(top, name="al")
        w.pack()
        row = [0]

        def nxt():
            row[0] += 1

        def vc_frame(P):
            try:
                if P.strip() != "":
                    float(P)
            except ValueError:
                return False
            if P.strip() != "" and float(P) > 0:
                tmp = self.sec2samp(power["uttLengthSec"], P)
                if tmp >= 0:
                    power["uttLength"] = tmp
            return True

        def vc_utt(P):
            tmp = self.sec2samp(P, power["frameLength"])
            if tmp >= 0:
                power["uttLength"] = tmp
                return True
            return False

        def vc_sil(P):
            tmp = self.sec2samp(P, power["frameLength"])
            if tmp >= 0:
                power["silLength"] = tmp
                return True
            return False

        r = row[0]
        tk.Label(w, text=t("estimateParam,pFLen")).grid(sticky="w", row=r, column=0)
        tk.Entry(w, textvariable="power(frameLength)", validate="all",
                 validatecommand=self._vcmd(vc_frame)).grid(sticky="w", row=r, column=1)
        tk.Label(w, text="(sec)").grid(sticky="w", row=r, column=2, columnspan=2)
        nxt()

        def simple(label, var, unit=None, span=3):
            r = row[0]
            tk.Label(w, text=t(label)).grid(sticky="w", row=r, column=0)
            if unit is None:
                tk.Entry(w, textvariable=var).grid(sticky="w", row=r, column=1, columnspan=span)
            else:
                tk.Entry(w, textvariable=var).grid(sticky="w", row=r, column=1)
                tk.Label(w, text=unit).grid(sticky="w", row=r, column=2, columnspan=2)
            nxt()
        simple("estimateParam,preemph", "power(preemphasis)")
        simple("estimateParam,pWinLen", "power(windowLength)", "(sec)")
        r = row[0]
        tk.Label(w, text=t("estimateParam,pWinkind")).grid(sticky="w", row=r, column=0)
        tk.OptionMenu(w, TVar(w, "power(window)"), "Hamming", "Hanning", "Bartlett", "Blackman",
                      "Rectangle").grid(sticky="w", row=r, column=1, columnspan=3)
        nxt()
        simple("estimateParam,pUttMin", "power(uttHigh)", "(db)")
        r = row[0]
        tk.Label(w, text=t("estimateParam,pUttMinTime")).grid(sticky="w", row=r, column=0)
        tk.Entry(w, textvariable="power(uttLengthSec)", validate="all",
                 validatecommand=self._vcmd(vc_utt)).grid(sticky="w", row=r, column=1)
        tk.Label(w, text="(sec) = ").grid(sticky="w", row=r, column=2)
        tk.Label(w, textvariable="power(uttLength)").grid(sticky="w", row=r, column=3)
        tk.Label(w, text="(sample)").grid(sticky="w", row=r, column=4)
        nxt()
        simple("estimateParam,uttLen", "power(uttKeep)", "(db)")
        simple("estimateParam,silMax", "power(uttLow)", "(db)")
        simple("estimateParam,vLow", "power(vLow)", "(db)")
        r = row[0]
        tk.Label(w, text=t("estimateParam,silMinTime")).grid(sticky="w", row=r, column=0)
        tk.Entry(w, textvariable="power(silLengthSec)", validate="all",
                 validatecommand=self._vcmd(vc_sil)).grid(sticky="w", row=r, column=1)
        tk.Label(w, text="(sec) = ").grid(sticky="w", row=r, column=2)
        tk.Label(w, textvariable="power(silLength)").grid(sticky="w", row=r, column=3)
        tk.Label(w, text="(sample)").grid(sticky="w", row=r, column=4)
        nxt()
        simple("estimateParam,minC", "estimate(minC)", "(sec)")
        tk.Label(w, text=t("estimateParam,f0")).grid(sticky="w", row=row[0], column=0, columnspan=3)
        nxt()
        first = True
        for k in "SCEPO":
            r = row[0]
            if first:
                tk.Label(w, text=t("estimateParam,target")).grid(sticky="w", row=r, column=0)
                first = False
            fe = tk.Frame(w)
            tk.Checkbutton(fe, variable="estimate(%s)" % k).pack(side="left")
            tk.Label(fe, text=t("estimateParam,%s" % k)).pack(side="left")
            fe.grid(sticky="w", row=r, column=1, columnspan=3)
            nxt()

        def run_all():
            if v.i("paramChanged"):
                act = self.tk_dialog(".confm", t(".confm"), t("estimateParam,overWrite"), "question", 1,
                                     t(".confm.ok"), t(".confm.c"))
                if act == 1:
                    return
            if str(power["silLengthSec"]).strip() == "":
                power["silLengthSec"] = 0
            if str(power["uttLengthSec"]).strip() == "":
                power["uttLengthSec"] = 0
            try:
                top.grab_set()
            except tk.TclError:
                pass
            try:
                self.makeRecListFromDir(0, 0)
                self.doEstimateParam("all")
                v["paramFile"] = v["saveDir"] + "/oto.ini"
                self.saveParamFile()
            finally:
                try:
                    top.grab_release()
                except tk.TclError:
                    pass
                top.destroy()
        r = row[0]
        tk.Button(w, text=t("estimateParam,runAll"), command=run_all).grid(sticky="we", row=r, column=0)
        tk.Button(w, text=t(".confm.c"), command=top.destroy).grid(sticky="we", row=r, column=2)

    def doEstimateParam(self, mode="all"):
        v, power, est, f0, t = self.v, self.power, self.estimate, self.f0, self.tt
        pu, ps = self.paramU, self.paramS
        v["msg"] = t("doEstimateParam,startMsg")
        self.initProgressWindow()
        targets = list(range(1, self.paramUsize))
        fl = dsp._clampf(power.f("frameLength"), 0.001, 1.0, 0.01)
        guard = self.fix("F01")
        for i in targets:
            fid = pu[(i, 0)]
            filename = "%s/%s.%s" % (v["saveDir"], fid, v["ext"])
            if not (os.path.isfile(filename) and os.access(filename, os.R_OK)):
                continue
            sw = audio.Sound()
            try:
                sw.read(filename)
            except Exception as e:
                self.log("%s: %s" % (filename, e))
                continue
            if sw.channels > 1:
                sw.set_data(sw.mono().reshape(-1, 1))
            v["sndLength"] = sw.length_sec()
            x = sw.mono()
            sr = self._calc_rate(sw.rate)
            pw = dsp.power(x, sw.rate, fl, power["window"], power.f("preemphasis"),
                           int(power.f("windowLength") * sr))
            if est.i("S"):
                ps[(i, "S")] = 0.0
            if est.i("C"):
                ps[(i, "C")] = est.f("minC")
            if est.i("E"):
                ps[(i, "E")] = sw.length_sec()
            if guard:
                ps.setdefault((i, "S"), 0.0)
            uttS = 0
            uttE = len(pw) - 1
            if len(pw) > 0:
                length = 0
                j = 0
                uttLength = power.i("uttLength")
                silLength = power.i("silLength")
                for j in range(len(pw)):
                    if pw[j] >= power.f("uttHigh"):
                        length += 1
                    else:
                        length = 0
                    if length >= uttLength + 1:
                        uttS = j
                        break
                if est.i("S"):
                    length = 0
                    for k in range(j, 0, -1):
                        if pw[k] <= power.f("uttLow"):
                            length += 1
                        else:
                            length = 0
                        if length >= silLength + 1:
                            ps[(i, "S")] = k * fl
                            break
                length = 0
                for j in range(len(pw) - 1, uttS, -1):
                    if pw[j] >= power.f("uttHigh"):
                        length += 1
                    else:
                        length = 0
                    if length >= uttLength + 1:
                        uttE = j
                        break
                Nmax = 30
                N = 0
                aveP = 0.0
                center = int((uttE + uttS) / 2)
                j = center + 1
                while j <= uttE and N < Nmax / 2:
                    aveP += pw[j]
                    N += 1
                    j += 1
                j = center
                while j >= uttS and N < Nmax:
                    aveP += pw[j]
                    N += 1
                    j -= 1
                if N == 0:
                    if not guard:
                        raise ZeroDivisionError("divide by zero")
                    aveP = 0.0
                else:
                    aveP /= N
                keep = power.f("uttKeep") / 2
                if est.i("E"):
                    j = center
                    while j <= uttE:
                        if aveP - pw[j] > keep:
                            break
                        j += 1
                    tm = j * fl
                    S = ps[(i, "S")]
                    ps[(i, "E")] = tm if S < tm else S
                if est.i("C"):
                    j = center
                    while j >= uttS:
                        if aveP - pw[j] > keep:
                            break
                        j -= 1
                    tm = j * fl
                    S = ps[(i, "S")]
                    minC = est.f("minC")
                    ps[(i, "C")] = tm if tm >= S + minC else S + minC
            if est.i("P"):
                ps[(i, "P")] = ps[(i, "S")]
                try:
                    series = dsp.pitch(x, sw.rate, f0["method"], frame_length=f0.f("frameLength"),
                                       window_length=f0.f("windowLength"), maxpitch=f0.f("max"),
                                       minpitch=f0.f("min"))
                except Exception as e:
                    self.log("error: %s" % e)
                    series = []
                ffl = dsp._clampf(f0.f("frameLength"), 0.001, 0.5, 0.01)
                vot = int(ps[(i, "P")] / ffl)
                while vot < len(series):
                    if series[vot] > 0:
                        break
                    vot += 1
                votSec = vot * ffl
                if (i, "C") not in ps:
                    if not guard:
                        raise KeyError("can't read \"paramS(%d,C)\": no such element in array" % i)
                    ps[(i, "C")] = sw.length_sec()
                C = ps[(i, "C")]
                j = int(votSec / fl)
                while j * fl < C:
                    if j < len(pw) and pw[j] >= power.f("vLow"):
                        break
                    j += 1
                tm = j * fl
                ps[(i, "P")] = tm if tm <= C else ps[(i, "S")]
            if est.i("O"):
                ps[(i, "O")] = ps[(i, "S")]
            for kind in "SECPO":
                if est.i(kind):
                    pu[(i, kind2c(kind))] = self.sec2u(i, kind, ps[(i, kind)], sw)
            self.updateProgressWindow(100 * i // max(1, self.paramUsize))
            v["msg"] = "%s (%d / %d)" % (t("doEstimateParam,startMsg"), i, self.paramUsize)
        self.deleteProgressWindow()
        v["msg"] = self.msg("doEstimateParam,doneMsg")

    # ------------------------------------------------------------------
    # saving oto.ini

    def saveParamFile(self, fn="", autoBackup=0):
        v, t = self.v, self.tt
        if fn == "":
            pf = v["paramFile"]
            fn = filedialog.asksaveasfilename(initialfile=os.path.basename(pf), initialdir=os.path.dirname(pf),
                                              title=t("saveParamFile,selFile"), defaultextension="ini")
            if not fn:
                return 0
        if not autoBackup:
            v["msg"] = t("saveParamFile,startMsg")
        if not os.path.exists(v["saveDir"]):
            os.makedirs(v["saveDir"], exist_ok=True)
        v["paramFile"] = fn.replace("\\", "/")
        lines = []
        pu = self.paramU
        for i in range(1, self.paramUsize):
            if (i, 0) in pu:
                name = "%s.%s" % (pu[(i, 0)], v["ext"])
                vals = []
                for c, dflt in ((6, ""), (1, 0), (4, 0), (5, 0), (3, 0), (2, 0)):
                    vals.append(fmt(pu.get((i, c), dflt)))
                A, S, C, E, P, O = vals
                lines.append("%s=%s,%s,%s,%s,%s,%s\n" % (name, A, S, C, E, P, O))
        try:
            used = self.write_textfile(fn, "".join(lines), "oto")
        except OSError:
            messagebox.showwarning(t(".confm.fioErr"), "error: can not open %s" % fn)
            return 0
        if not autoBackup:
            v["msg"] = self.msg("saveParamFile,doneMsg")
            want = textenc.normalize(self.enc_out("oto"))
            if want and used != want:
                v["msg"] = v["msg"] + " " + self.msg("enc,fallbackUsed", enc=textenc.label(used))
        return 1

    # ------------------------------------------------------------------
    # unit conversion

    def paramU2paramS(self, r):
        for c in range(1, 6):
            kind = c2kind(c)
            if (r, c) in self.paramU:
                self.paramS[(r, kind)] = self.u2sec(kind, r, c)

    def sec2u(self, r, kind, newVal, work=None):
        v, pu, ps = self.v, self.paramU, self.paramS
        fid = pu[(r, 0)]
        fname = "%s/%s.%s" % (v["saveDir"], fid, v["ext"])
        if self.fix("F02"):
            if work is not None:
                v["sndLength"] = work.length_sec()
        elif os.path.isfile(fname):
            # original: 'snd read $fname' -> replaces the sound shown in the main window
            try:
                self.snd.read(fname)
                if self.snd.channels != 1:
                    self.snd.set_data(self.snd.mono().reshape(-1, 1))
                v["sndLength"] = self.snd.length_sec()
            except Exception:
                pass
        S = ps.get((r, "S"), 0.0)
        newVal = float(newVal)
        if kind == "S":
            return cut3(newVal * 1000.0)
        if kind == "E":
            if v.i("setE") < 0:
                return cut3(-(newVal - S) * 1000.0)
            return cut3(v.f("sndLength") * 1000.0 - newVal * 1000.0)
        return cut3((newVal - S) * 1000)

    def u2sec(self, kind, r, c):
        ps, pu, v = self.paramS, self.paramU, self.v
        S = ps.get((r, "S"), 0.0)
        raw = pu.get((r, c), "")
        u = num(raw) if str(raw) != "" else 0.0
        if kind == "S":
            return cut6(u / 1000.0)
        if kind in ("C", "P", "O"):
            return cut6(u / 1000.0 + S)
        if kind == "E":
            if u >= 0:
                return cut6(v.f("sndLength") - u / 1000.0)
            return cut6(u / -1000.0 + S)
        return 0.0

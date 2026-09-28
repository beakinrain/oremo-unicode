"""KOREDE - guide BGM setting file maker (port of guideBGM/korede.tcl)."""

import os
import re
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

from . import audio, snackui, textenc

MSG = {
    "ja": {
        "bgmStartMsg": "BGM再生", "bgmEndMsg": "録音を保存し次へ", "recStartMsg": "録音開始",
        "recEndMsg": "録音停止", "uttStartMsg": "発声はじめ！", "uttEndMsg": "発声おわり！",
        "bgm": "BGMファイル：", "sel": "BGMファイルの選択", "no": "No.", "event": "イベント",
        "time": "時刻(秒)", "guide": "ガイド文", "region": "区間再生", "bgmStart": "BGM再生開始：",
        "recStart": "録音開始：", "uttStart": "発声開始：", "uttEnd": "発声停止：", "recEnd": "録音停止：",
        "bgmEnd": "BGM再生停止：", "save": "保存", "pre": "※最初の先行発声値 = 発声開始 - 録音開始 = ",
        "err": "エラー", "range": "規定範囲外の値があります。(%s)", "order": "(%s < %s)にして下さい",
        "confirm": "確認", "overwrite": "%s に上書き保存しますか？", "yes": "はい", "other": "別名で保存",
        "cancel": "キャンセル", "saveTitle": "設定ファイルの保存", "cant": "設定ファイル(%s)に保存できませんでした",
        "saved": "保存しました(%s)", "ok": "保存成功", "forfile": "%s用の設定ファイル",
        "header": "No, 時刻, r開始, r停止, ↓キー押, リピート, コメント",
    },
    "zh_CN": {
        "bgmStartMsg": "BGM播放", "bgmEndMsg": "保存录音并进入下一个", "recStartMsg": "开始录音",
        "recEndMsg": "停止录音", "uttStartMsg": "开始发声！", "uttEndMsg": "结束发声！",
        "bgm": "BGM文件：", "sel": "选择BGM文件", "no": "No.", "event": "事件", "time": "时刻(秒)",
        "guide": "提示文字", "region": "区间播放", "bgmStart": "BGM开始播放：", "recStart": "开始录音：",
        "uttStart": "开始发声：", "uttEnd": "结束发声：", "recEnd": "停止录音：", "bgmEnd": "BGM停止播放：",
        "save": "保存", "pre": "※第一个先行发声值 = 开始发声 - 开始录音 = ", "err": "错误",
        "range": "有超出规定范围的值。(%s)", "order": "请设为 (%s < %s)", "confirm": "确认",
        "overwrite": "要覆盖保存到 %s 吗？", "yes": "是", "other": "另存为", "cancel": "取消",
        "saveTitle": "保存设置文件", "cant": "无法保存到设置文件(%s)", "saved": "已保存(%s)", "ok": "保存成功",
        "forfile": "%s 用的设置文件", "header": "No, 时刻, r开始, r停止, ↓键, 重复, 备注",
    },
    "en": {
        "bgmStartMsg": "BGM start", "bgmEndMsg": "Save and next", "recStartMsg": "Recording",
        "recEndMsg": "Recording stopped", "uttStartMsg": "Sing!", "uttEndMsg": "Stop singing!",
        "bgm": "BGM file:", "sel": "Choose BGM file", "no": "No.", "event": "Event", "time": "Time (sec)",
        "guide": "Guide text", "region": "Play range", "bgmStart": "BGM start:", "recStart": "Rec start:",
        "uttStart": "Utterance start:", "uttEnd": "Utterance end:", "recEnd": "Rec stop:", "bgmEnd": "BGM end:",
        "save": "Save", "pre": "* first preutterance = utterance start - rec start = ", "err": "Error",
        "range": "A value is out of range. (%s)", "order": "Make it (%s < %s)", "confirm": "Confirm",
        "overwrite": "Overwrite %s ?", "yes": "Yes", "other": "Save as", "cancel": "Cancel",
        "saveTitle": "Save setting file", "cant": "Could not save (%s)", "saved": "Saved (%s)", "ok": "Saved",
        "forfile": "setting file for %s", "header": "No, time, rStart, rStop, next, repeat, comment",
    },
}

KEYS = ["bgmStart", "recStart", "uttStart", "uttEnd", "recEnd", "bgmEnd"]


class Korede:
    def __init__(self, topdir):
        self.topdir = topdir
        self.lang = self._lang()
        self.m = MSG.get(self.lang, MSG["ja"])
        from .app import _peek_sysini, enable_dpi_awareness, setup_scaling
        pre = _peek_sysini(os.path.join(self.topdir, "..", "oremo-setting.ini"))
        aware = pre.get("dpiAware", "1") != "0"
        if aware:
            enable_dpi_awareness()
        self.root = tk.Tk()
        self.S = setup_scaling(self.root, pre.get("uiScale", "auto"), aware)
        snackui.SCALE = self.S
        self.root.title("KOREDE 1.0-U1")
        self.snd = audio.Sound()
        self.player = audio.Player("korede")
        self.icons = snackui.create_icons(self.root, self.S)
        self.cWidth, self.cHeight, self.timeh = int(600 * self.S), int(200 * self.S), int(25 * self.S)
        self.sndLen = 0.0
        self.wavepps = 100
        self.v = {}
        for k in KEYS:
            self.v[k] = tk.StringVar(self.root, "0")
            self.v[k].trace_add("write", lambda *a: self.redraw())
            self.v[k + "Msg"] = tk.StringVar(self.root, self.m[k + "Msg"])
        self.bgmFile = tk.StringVar(self.root, "")
        self.pre = tk.StringVar(self.root, "0")
        self.playTime = tk.StringVar(self.root, "0")
        self.sndLenVar = tk.StringVar(self.root, "0")
        self._build()
        self.root.update()
        self.redraw()
        self.root.minsize(self.root.winfo_width(), self.root.winfo_height())
        self.root.bind("<Configure>", lambda e: self.redraw() if e.widget is self.root else None)
        self.root.after(20, self._poll)

    def _lang(self):
        try:
            text, _ = textenc.read_text(os.path.join(self.topdir, "..", "oremo-setting.ini"))
            m = re.search(r"^lang=(\S+)", text, re.M)
            if m:
                return m.group(1)
        except OSError:
            pass
        return "ja"

    def _poll(self):
        try:
            while True:
                fn, args = audio.ui_queue.get_nowait()
                fn(*args)
        except Exception:
            pass
        self.root.after(20, self._poll)

    def _build(self):
        m, r = self.m, self.root
        f = tk.Frame(r)
        f.grid(row=0, column=0, sticky="nw")
        tk.Label(f, text=m["bgm"]).pack(side="left")
        tk.Entry(f, textvariable=self.bgmFile, width=60).pack(side="left")
        tk.Button(f, image=self.icons["snackOpen"], command=self.choose).pack(side="left")
        tk.Button(f, image=self.icons["snackPlay"], command=lambda: self.play()).pack(side="left")
        tk.Button(f, image=self.icons["snackStop"], command=self.stop).pack(side="left")
        tk.Label(f, textvariable=self.playTime).pack(side="left")
        tk.Label(f, text="/").pack(side="left")
        tk.Label(f, textvariable=self.sndLenVar).pack(side="left")
        self.c = tk.Canvas(r, width=self.cWidth, height=self.cHeight)
        self.c.grid(row=1, column=0, sticky="nwse")
        f = tk.Frame(r)
        f.grid(row=2, column=0, sticky="nwse")
        for col, key in enumerate(["no", "event", "time", "guide", "no", "event", "time", "guide", "region"]):
            tk.Button(f, relief="groove", text=m[key]).grid(row=0, column=col, sticky="nwse")
        vc = (r.register(self.check), "%P")
        rows = [("bgmStart", "bgmEnd", "green", 1, 6), ("recStart", "recEnd", "red", 2, 5),
                ("uttStart", "uttEnd", "blue", 3, 4)]
        for i, (a, b, color, na, nb) in enumerate(rows, start=1):
            tk.Label(f, text=str(na)).grid(row=i, column=0, sticky="ne")
            tk.Label(f, text=m[a]).grid(row=i, column=1, sticky="ne")
            tk.Entry(f, width=5, textvariable=self.v[a], validate="all", validatecommand=vc).grid(row=i, column=2, sticky="nwse")
            tk.Entry(f, textvariable=self.v[a + "Msg"]).grid(row=i, column=3, sticky="nwse")
            tk.Label(f, text=str(nb)).grid(row=i, column=4, sticky="ne")
            tk.Label(f, text=m[b]).grid(row=i, column=5, sticky="ne")
            tk.Entry(f, width=5, textvariable=self.v[b], validate="all", validatecommand=vc).grid(row=i, column=6, sticky="nwse")
            tk.Entry(f, textvariable=self.v[b + "Msg"]).grid(row=i, column=7, sticky="nwse")
            tk.Button(f, image=self.icons["snackPlay"], bg=color,
                      command=lambda a=a, b=b: self.region(a, b)).grid(row=i, column=8, sticky="n")
        f = tk.Frame(r)
        f.grid(row=3, column=0, sticky="nwse")
        tk.Button(f, text=m["save"], command=self.save).grid(row=0, column=0, sticky="nw")
        tk.Label(f, text=m["pre"]).grid(row=0, column=1, sticky="nw")
        tk.Label(f, textvariable=self.pre).grid(row=0, column=2, sticky="nw")

    def check(self, P):
        if P == "":
            return True
        try:
            return float(P) >= 0
        except ValueError:
            return False

    def val(self, k):
        try:
            return float(self.v[k].get())
        except ValueError:
            return 0.0

    def choose(self):
        fn = filedialog.askopenfilename(title=self.m["sel"], defaultextension="wav",
                                        filetypes=[("wav file", ".wav"), ("All Files", "*")])
        if fn:
            self.bgmFile.set(fn)
            try:
                self.snd.read(fn)
            except Exception as e:
                messagebox.showerror(self.m["err"], str(e))
                return
            self.sndLen = int(1000 * self.snd.length_sec()) / 1000.0
            self.sndLenVar.set(str(self.sndLen))
            self.v["bgmEnd"].set(str(self.sndLen))
            self.redraw()

    def redraw(self):
        c = self.c
        try:
            self.pre.set(str(int((self.val("uttStart") - self.val("recStart")) * 1000 + 0.5) / 1000.0))
        except Exception:
            pass
        w = self.root.winfo_width() - 4
        if w > 0:
            self.cWidth = w
        c.configure(width=self.cWidth)
        self.wavepps = float(self.cWidth) / self.sndLen if self.sndLen > 0 else 1.0 / self.cWidth
        c.delete("all")
        mono = self.snd.mono() if self.snd.length() else []
        wh = self.cHeight - self.timeh
        snackui.draw_waveform(c, 0, 0, mono, self.cWidth, wh, 0, "#707070", ("wave",))
        snackui.time_axis(c, 0, wh, self.cWidth, self.timeh, self.wavepps)
        c.create_line(0, wh, self.cWidth, wh)
        c.create_line(0, self.cHeight, self.cWidth, self.cHeight)
        for a, b, color, off in (("bgmStart", "bgmEnd", "green", 20), ("recStart", "recEnd", "red", 22),
                                 ("uttStart", "uttEnd", "blue", 24)):
            l, r = self.val(a) * self.wavepps, self.val(b) * self.wavepps
            if l < r:
                c.create_rectangle(l, wh - off, r, wh, width=2, outline=color, fill=color, stipple="gray25")

    def play(self, st=0.0, en=-1.0):
        if self.snd.length() == 0:
            return
        rate = self.snd.rate
        end = int(en * rate) if en > 0 else -1
        try:
            self.player.play(self.snd.data, rate, int(st * rate), end, on_done=self.stop)
        except audio.AudioError as e:
            messagebox.showerror(self.m["err"], str(e))
            return
        self._bar()

    def _bar(self):
        self.c.delete("playBar")
        if not self.player.active():
            self.playTime.set("0")
            return
        t = self.player.position_sec()
        self.playTime.set("%.2f" % t)
        x = t * self.wavepps
        self.c.create_line(x, 0, x, self.cHeight, fill="#FFA000", tags="playBar")
        self.root.after(50, self._bar)

    def stop(self):
        self.player.stop()
        self.c.delete("playBar")

    def region(self, a, b):
        self.play(self.val(a), self.val(b))

    def save(self):
        m = self.m
        for k in KEYS:
            if self.val(k) < 0 or self.val(k) > self.sndLen:
                messagebox.showwarning(m["err"], m["range"] % k)
                return
        for a, b in zip(KEYS, KEYS[1:]):
            if self.val(a) >= self.val(b):
                messagebox.showwarning(m["err"], m["order"] % (m[a].rstrip("：:"), m[b].rstrip("：:")))
                return
        fn = os.path.splitext(self.bgmFile.get())[0] + ".txt" if self.bgmFile.get() else ""
        if fn and os.path.exists(fn):
            act = int(self.root.tk.call("tk_dialog", ".confm", m["confirm"], m["overwrite"] % fn, "question", 2,
                                        m["yes"], m["other"], m["cancel"]))
            if act == 1:
                fn = filedialog.asksaveasfilename(initialfile=os.path.basename(fn), initialdir=os.path.dirname(fn),
                                                  title=m["saveTitle"], defaultextension="txt")
            if act == 2:
                return
        if not fn:
            return
        g = lambda k: self.v[k].get()
        lines = ["sec", "#", "# " + m["forfile"] % os.path.basename(self.bgmFile.get()), "#", "# " + m["header"],
                 "   1, %s,\t0, 0, 0, 0, %s" % (g("bgmStart"), g("bgmStartMsg")),
                 "   2, %s,\t1, 0, 0, 0, %s" % (g("recStart"), g("recStartMsg")),
                 "   3, %s,\t0, 0, 0, 0, %s" % (g("uttStart"), g("uttStartMsg")),
                 "   4, %s,\t0, 0, 0, 0, %s" % (g("uttEnd"), g("uttEndMsg")),
                 "   5, %s,\t0, 1, 0, 0, %s" % (g("recEnd"), g("recEndMsg")),
                 "   6, %s,\t0, 0, 1, 1, %s" % (g("bgmEnd"), g("bgmEndMsg"))]
        try:
            textenc.write_text(fn, "\n".join(lines) + "\n", "cp932", "utf-8-sig")
        except OSError:
            messagebox.showwarning(m["err"], m["cant"] % fn)
            return
        messagebox.showinfo(m["ok"], m["saved"] % fn)

    def run(self):
        self.root.mainloop()

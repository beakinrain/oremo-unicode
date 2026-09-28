"""Unicode edition additions: encoding settings, batch encoding converter,
file name mojibake repair, language selection and bug-fix switches."""

import os
import unicodedata
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from tkinter import ttk

from . import fixes, textenc

READ_CHOICES = [textenc.AUTO] + [e for e, _ in textenc.ENCODINGS] + [textenc.SYSTEM]
WRITE_CHOICES = [e for e, _ in textenc.ENCODINGS] + [textenc.SYSTEM]
FALLBACK_CHOICES = ["utf-8-sig", "utf-8", "gb18030", "none"]
TEXT_PATTERNS = (".txt", ".ini", ".ust", ".tcl", ".csv", ".lab")


def _same_name(a, b):
    """True if two names denote the same file on a case / normalization insensitive file system."""
    n = lambda s: unicodedata.normalize("NFC", s).lower()
    return n(a) == n(b)


def _labels(choices, extra=None):
    out = []
    for c in choices:
        if extra and c in extra:
            out.append(extra[c])
        else:
            out.append(textenc.label(c))
    return out


class _EncCombo(ttk.Combobox):
    """Combobox showing encoding labels but returning codec names."""

    def __init__(self, master, choices, value, extra=None, width=22):
        self.choices = list(choices)
        self.labels = _labels(self.choices, extra)
        super().__init__(master, values=self.labels, state="readonly", width=width)
        self.set_value(value)

    def set_value(self, value):
        if value in self.choices:
            self.current(self.choices.index(value))
        else:
            self.choices.append(value)
            self.labels.append(textenc.label(value))
            self.configure(values=self.labels)
            self.current(len(self.choices) - 1)

    def value(self):
        i = self.current()
        return self.choices[i] if i >= 0 else self.choices[0]


class ToolsMixin:

    def build_tools_menu(self, m):
        t = self.tt
        m.add_command(label=t("tool,encSettings", "Encoding settings..."), command=self.encodingSettings)
        sub = tk.Menu(m, tearoff=0)
        m.add_cascade(label=t("tool,reloadRecList", "Reload reclist with encoding"), menu=sub)
        for enc in READ_CHOICES:
            sub.add_command(label=textenc.label(enc), command=lambda e=enc: self.reloadRecListWith(e))
        m.add_command(label=t("tool,converter", "Encoding / file name converter..."),
                      command=self.converterWindow)
        m.add_command(label=t("tool,korede", "KOREDE (guide BGM setting file maker)..."),
                      command=self.launchKorede)
        m.add_separator()
        lang = tk.Menu(m, tearoff=0)
        m.add_cascade(label=t("tool,language", "Language"), menu=lang)
        self._lang_var = tk.StringVar(self.root, value=self.lang)
        from .app import LANGS
        for code, name in LANGS:
            lang.add_radiobutton(label=name, value=code, variable=self._lang_var,
                                 command=lambda c=code: self.setLanguage(c))
        from .app import UI_SCALES
        sc = tk.Menu(m, tearoff=0)
        m.add_cascade(label=t("tool,uiScale", "UI zoom"), menu=sc)
        self._scale_var = tk.StringVar(self.root, value=self.ini("uiScale", "auto"))
        for s in UI_SCALES:
            lab = t("tool,uiScaleAuto", "Auto (Windows setting)") if s == "auto" else "%d%%" % int(float(s) * 100)
            sc.add_radiobutton(label=lab, value=s, variable=self._scale_var,
                               command=lambda s=s: self._set_restart_option("uiScale", s))
        self._dpi_var = tk.IntVar(self.root, value=0 if self.ini("dpiAware", "1") == "0" else 1)
        m.add_checkbutton(label=t("tool,dpiAware", "Sharp display on high DPI screens"), variable=self._dpi_var,
                          command=lambda: self._set_restart_option("dpiAware", self._dpi_var.get()))
        m.add_command(label=t("tool,fixes", "Bug fix switches..."), command=self.fixSettings)

    def _set_restart_option(self, key, value):
        self.set_ini(key, value)
        messagebox.showinfo(self.tt("tool", "Tools"),
                            self.tt("tool,restartMsg", "The change takes effect after restarting OREMO."))

    # ------------------------------------------------------------------

    def launchKorede(self):
        """Start KOREDE as a separate process."""
        import subprocess
        import sys
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            kexe = os.path.join(exe_dir, "korede.exe")
            cmd = [kexe] if os.path.exists(kexe) else [sys.executable, "--korede"]
        else:
            main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "oremo_main.py")
            cmd = [sys.executable, main, "--korede"]
        try:
            subprocess.Popen(cmd)
        except OSError as e:
            messagebox.showerror(self.tt(".confm.errTitle"), str(e))

    def setLanguage(self, code):
        self.set_ini("lang", code)
        messagebox.showinfo(self.tt("tool,language", "Language"),
                            self.tt("tool,restartMsg", "The change takes effect after restarting OREMO."))

    def reloadRecListWith(self, enc):
        v = self.v
        fn = v["recListFile"]
        if not os.path.exists(fn):
            self.readRecList()
            self.resetDisplay()
            return
        old = self.ini("enc.read", textenc.AUTO)
        self.sysini["enc.read"] = enc
        try:
            self.readRecList(fn)
        finally:
            self.sysini["enc.read"] = old
        self.resetDisplay()
        used = self.read_encoding.get(os.path.normcase(os.path.abspath(fn)), "")
        v["msg"] = "%s  [%s]" % (v["msg"], textenc.label(used))

    # ------------------------------------------------------------------

    def encodingSettings(self):
        t = self.tt
        if self.isExist(".encSettings"):
            return
        w = tk.Toplevel(self.root, name="encSettings")
        w.title(t("enc,title", "Encoding settings"))
        w.resizable(0, 0)
        w.bind("<Escape>", lambda e: w.destroy())
        f = tk.Frame(w, padx=8, pady=8)
        f.pack(fill="both")
        rows = []

        def add(label, combo):
            r = len(rows)
            tk.Label(f, text=t(label), anchor="w").grid(row=r, column=0, sticky="w", pady=2)
            combo.grid(row=r, column=1, sticky="w", pady=2)
            rows.append(combo)
            return combo
        c_read = add("enc,read", _EncCombo(f, READ_CHOICES, self.enc_read()))
        c_oto = add("enc,oto", _EncCombo(f, WRITE_CHOICES, self.enc_out("oto")))
        c_com = add("enc,comment", _EncCombo(f, WRITE_CHOICES, self.enc_out("comment")))
        c_rl = add("enc,reclist", _EncCombo(f, ["same"] + WRITE_CHOICES, self.enc_out("reclist"),
                                             extra={"same": t("enc,same", "same as read")}))
        c_ini = add("enc,init", _EncCombo(f, WRITE_CHOICES, self.enc_out("init")))
        c_fb = add("enc,fallback", _EncCombo(f, FALLBACK_CHOICES, self.ini("enc.fallback", "utf-8-sig"),
                                              extra={"none": t("enc,noFallback", "none (replace with ?)")}))
        r = len(rows)
        used = self.read_encoding.get(os.path.normcase(os.path.abspath(self.v["recListFile"])), "")
        info = "%s\n%s: %s" % (t("enc,note"), os.path.basename(self.v["recListFile"]),
                               textenc.label(used) if used else "-")
        tk.Label(f, text=info, justify="left", fg="#404040").grid(row=r, column=0, columnspan=2, sticky="w", pady=6)
        fb = tk.Frame(w)
        fb.pack(anchor="e", padx=6, pady=6)

        def ok():
            self.sysini["enc.read"] = c_read.value()
            self.sysini["enc.oto"] = c_oto.value()
            self.sysini["enc.comment"] = c_com.value()
            self.sysini["enc.reclist"] = c_rl.value()
            self.sysini["enc.init"] = c_ini.value()
            self.sysini["enc.fallback"] = c_fb.value()
            self.writeSysIniFile()
            w.destroy()
        tk.Button(fb, text=t(".confm.ok"), width=8, command=ok).pack(side="left")
        tk.Button(fb, text=t(".confm.c"), width=8, command=w.destroy).pack(side="left")

    # ------------------------------------------------------------------

    def fixSettings(self):
        t = self.tt
        if self.isExist(".fixSettings"):
            return
        w = tk.Toplevel(self.root, name="fixSettings")
        w.title(t("fix,title", "Bug fix switches"))
        w.bind("<Escape>", lambda e: w.destroy())
        tk.Label(w, text=t("fix,note"), justify="left", fg="red", wraplength=640).pack(anchor="w", padx=8, pady=4)
        f = tk.Frame(w, padx=8)
        f.pack(fill="both")
        vars_ = {}
        for r, (fid, _name) in enumerate(fixes.FIXES):
            var = tk.IntVar(w, value=1 if self.fix(fid) else 0)
            vars_[fid] = var
            tk.Checkbutton(f, variable=var, text=fid).grid(row=r, column=0, sticky="nw")
            tk.Label(f, text=t("fix,%s" % fid, fid), justify="left", wraplength=580, anchor="w").grid(
                row=r, column=1, sticky="w", pady=1)
        fb = tk.Frame(w)
        fb.pack(anchor="e", padx=6, pady=6)

        def set_all(val):
            for var in vars_.values():
                var.set(val)

        def ok():
            for fid, var in vars_.items():
                self.sysini["fix." + fid] = str(var.get())
            self.writeSysIniFile()
            w.destroy()
        tk.Button(fb, text=t("fix,all", "All"), width=8, command=lambda: set_all(1)).pack(side="left")
        tk.Button(fb, text=t("fix,none", "None"), width=8, command=lambda: set_all(0)).pack(side="left")
        tk.Button(fb, text=t(".confm.ok"), width=8, command=ok).pack(side="left")
        tk.Button(fb, text=t(".confm.c"), width=8, command=w.destroy).pack(side="left")

    # ------------------------------------------------------------------
    # converter window

    def converterWindow(self):
        if self.isExist(".converter"):
            return
        ConverterWindow(self)


class ConverterWindow:
    def __init__(self, app):
        self.app = app
        t = app.tt
        self.t = t
        w = tk.Toplevel(app.root, name="converter")
        self.w = w
        w.title(t("conv,title", "Encoding / file name converter"))
        w.geometry("%dx%d" % (int(900 * app.S), int(560 * app.S)))
        w.bind("<Escape>", lambda e: w.destroy())
        nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=1, padx=4, pady=4)
        self._build_content_tab(nb)
        self._build_name_tab(nb)
        self._build_text_tab(nb)
        self.undo = []

    # ---------------------------------------------------------------- content

    def _build_content_tab(self, nb):
        t = self.t
        f = tk.Frame(nb)
        nb.add(f, text=t("conv,tabContent", "File contents"))
        top = tk.Frame(f)
        top.pack(fill="x", pady=2)
        tk.Button(top, text=t("conv,addFiles", "Add files..."), command=self.add_files).pack(side="left")
        tk.Button(top, text=t("conv,addFolder", "Add folder..."), command=self.add_folder).pack(side="left")
        tk.Button(top, text=t("conv,remove", "Remove"), command=self.remove_sel).pack(side="left")
        tk.Button(top, text=t("conv,clear", "Clear"), command=lambda: self.ctree.delete(*self.ctree.get_children())).pack(side="left")
        opt = tk.Frame(f)
        opt.pack(fill="x", pady=2)
        tk.Label(opt, text=t("conv,src", "From:")).pack(side="left")
        self.c_src = _EncCombo(opt, READ_CHOICES, textenc.AUTO, width=18)
        self.c_src.pack(side="left")
        self.c_src.bind("<<ComboboxSelected>>", lambda e: (self.refresh_detect(), self.preview()))
        tk.Label(opt, text="  " + t("conv,dst", "To:")).pack(side="left")
        self.c_dst = _EncCombo(opt, WRITE_CHOICES, "utf-8-sig", width=18)
        self.c_dst.pack(side="left")
        tk.Label(opt, text="  " + t("conv,newline", "Newline:")).pack(side="left")
        self.nl = ttk.Combobox(opt, state="readonly", width=8, values=[t("conv,keep", "keep"), "CRLF", "LF"])
        self.nl.current(0)
        self.nl.pack(side="left")
        self.bak = tk.IntVar(f, value=1)
        tk.Checkbutton(opt, text=t("conv,backup", "Make .bak backup"), variable=self.bak).pack(side="left")
        tk.Button(opt, text=t("conv,run", "Convert"), command=self.convert_contents).pack(side="right")
        pw = tk.PanedWindow(f, orient="vertical")
        pw.pack(fill="both", expand=1)
        tf = tk.Frame(pw)
        self.ctree = ttk.Treeview(tf, columns=("enc", "status"), selectmode="extended")
        self.ctree.heading("#0", text=t("conv,file", "File"))
        self.ctree.heading("enc", text=t("conv,detected", "Detected"))
        self.ctree.heading("status", text=t("conv,status", "Status"))
        self.ctree.column("#0", width=520)
        self.ctree.column("enc", width=150)
        self.ctree.column("status", width=150)
        sb = ttk.Scrollbar(tf, command=self.ctree.yview)
        self.ctree.configure(yscrollcommand=sb.set)
        self.ctree.pack(side="left", fill="both", expand=1)
        sb.pack(side="left", fill="y")
        self.ctree.bind("<<TreeviewSelect>>", lambda e: self.preview())
        pw.add(tf, height=260)
        self.ptext = tk.Text(pw, height=10, wrap="none")
        pw.add(self.ptext)

    def _add_path(self, p):
        p = os.path.abspath(p)
        for iid in self.ctree.get_children():
            if self.ctree.item(iid, "text") == p:
                return
        self.ctree.insert("", "end", text=p, values=(self._detect(p), ""))

    def _detect(self, p):
        try:
            with open(p, "rb") as fp:
                data = fp.read()
        except OSError as e:
            return str(e)
        src = self.c_src.value()
        if src != textenc.AUTO:
            return textenc.label(src)
        return textenc.label(textenc.detect(data))

    def refresh_detect(self):
        for iid in self.ctree.get_children():
            self.ctree.set(iid, "enc", self._detect(self.ctree.item(iid, "text")))

    def add_files(self):
        fns = filedialog.askopenfilenames(parent=self.w, title=self.t("conv,addFiles", "Add files..."),
                                          filetypes=[("text", "*.txt *.ini *.ust *.tcl *.csv"), ("All Files", "*")])
        for fn in fns:
            self._add_path(fn)

    def add_folder(self):
        d = filedialog.askdirectory(parent=self.w)
        if not d:
            return
        for root, dirs, files in os.walk(d):
            for fn in files:
                if fn.lower().endswith(TEXT_PATTERNS):
                    self._add_path(os.path.join(root, fn))

    def remove_sel(self):
        for iid in self.ctree.selection():
            self.ctree.delete(iid)

    def preview(self):
        sel = self.ctree.selection()
        self.ptext.delete("1.0", "end")
        if not sel:
            return
        p = self.ctree.item(sel[0], "text")
        try:
            text, used = textenc.read_text(p, self.c_src.value())
        except OSError as e:
            self.ptext.insert("end", str(e))
            return
        self.ptext.insert("end", "[%s]\n" % textenc.label(used))
        self.ptext.insert("end", "\n".join(text.split("\n")[:200]))

    def convert_contents(self):
        t = self.t
        items = self.ctree.get_children()
        if not items:
            return
        dst = self.c_dst.value()
        nlsel = self.nl.current()
        ok = 0
        for iid in items:
            p = self.ctree.item(iid, "text")
            try:
                with open(p, "rb") as fp:
                    data = fp.read()
                text, used = textenc.decode_bytes(data, self.c_src.value())
                if nlsel == 1:
                    newline = "\r\n"
                elif nlsel == 2:
                    newline = "\n"
                else:
                    newline = None
                try:
                    out_bytes = None
                    tx = text if newline is None else text.replace("\r\n", "\n").replace("\n", newline)
                    out_bytes = tx.encode(textenc.normalize(dst) or "utf-8")
                except UnicodeEncodeError as e:
                    bad = tx[e.start:e.end]
                    self.ctree.set(iid, "status", t("conv,unencodable", "cannot encode") + " '%s'" % bad)
                    continue
                if self.bak.get():
                    bakp = p + ".bak"
                    n = 1
                    while os.path.exists(bakp):
                        n += 1
                        bakp = "%s.bak-%d" % (p, n)
                    with open(bakp, "wb") as fp:
                        fp.write(data)
                with open(p, "wb") as fp:
                    fp.write(out_bytes)
                self.ctree.set(iid, "status", "%s -> %s" % (textenc.label(used), textenc.label(dst)))
                self.ctree.set(iid, "enc", textenc.label(dst))
                ok += 1
            except OSError as e:
                self.ctree.set(iid, "status", str(e))
        messagebox.showinfo(t("conv,title", "Converter"), t("conv,done", "Done") + " (%d/%d)" % (ok, len(items)),
                            parent=self.w)

    # ---------------------------------------------------------------- names

    def _build_name_tab(self, nb):
        t = self.t
        f = tk.Frame(nb)
        nb.add(f, text=t("conv,tabName", "File names"))
        top = tk.Frame(f)
        top.pack(fill="x", pady=2)
        tk.Label(top, text=t("conv,folder", "Folder:")).pack(side="left")
        self.folder = tk.StringVar(f, value=self.app.v["saveDir"])
        tk.Entry(top, textvariable=self.folder, width=60).pack(side="left", fill="x", expand=1)
        tk.Button(top, image=self.app.icons["snackOpen"], command=self._choose_folder).pack(side="left")
        opt = tk.Frame(f)
        opt.pack(fill="x", pady=2)
        self.recursive = tk.IntVar(f, value=0)
        self.dirs = tk.IntVar(f, value=0)
        tk.Checkbutton(opt, text=t("conv,recursive", "Include sub folders"), variable=self.recursive).pack(side="left")
        tk.Checkbutton(opt, text=t("conv,dirs", "Rename folders too"), variable=self.dirs).pack(side="left")
        tk.Label(opt, text="  " + t("conv,wrong", "Shown as:")).pack(side="left")
        wrong_choices = [textenc.AUTO, "gbk", "cp932", "cp437", "cp1252", "latin-1", "big5"]
        self.c_wrong = _EncCombo(opt, wrong_choices, textenc.AUTO, width=16)
        self.c_wrong.pack(side="left")
        tk.Label(opt, text=" " + t("conv,real", "Real:")).pack(side="left")
        real_choices = [textenc.AUTO, "cp932", "gbk", "utf-8", "big5"]
        self.c_real = _EncCombo(opt, real_choices, textenc.AUTO, width=16)
        self.c_real.pack(side="left")
        tk.Button(opt, text=t("conv,scan", "Scan"), command=self.scan_names).pack(side="left", padx=4)
        tf = tk.Frame(f)
        tf.pack(fill="both", expand=1)
        self.ntree = ttk.Treeview(tf, columns=("new", "how", "status"), selectmode="extended")
        self.ntree.heading("#0", text=t("conv,current", "Current name"))
        self.ntree.heading("new", text=t("conv,new", "New name"))
        self.ntree.heading("how", text=t("conv,how", "Method"))
        self.ntree.heading("status", text=t("conv,status", "Status"))
        self.ntree.column("#0", width=300)
        self.ntree.column("new", width=300)
        self.ntree.column("how", width=110)
        self.ntree.column("status", width=120)
        sb = ttk.Scrollbar(tf, command=self.ntree.yview)
        self.ntree.configure(yscrollcommand=sb.set)
        self.ntree.pack(side="left", fill="both", expand=1)
        sb.pack(side="left", fill="y")
        bot = tk.Frame(f)
        bot.pack(fill="x", pady=2)
        tk.Label(bot, text=t("conv,nameNote", ""), fg="#404040").pack(side="left")
        tk.Button(bot, text=t("conv,undo", "Undo"), command=self.undo_rename).pack(side="right")
        tk.Button(bot, text=t("conv,rename", "Rename selected"), command=self.do_rename).pack(side="right")
        self.name_rows = {}

    def _choose_folder(self):
        d = filedialog.askdirectory(parent=self.w, initialdir=self.folder.get())
        if d:
            self.folder.set(d)

    def scan_names(self):
        t = self.t
        self.ntree.delete(*self.ntree.get_children())
        self.name_rows = {}
        d = self.folder.get()
        if not os.path.isdir(d):
            messagebox.showwarning(t("conv,title", "Converter"), d, parent=self.w)
            return
        entries = []
        if self.recursive.get():
            for root, dirs, files in os.walk(d, topdown=False):
                for fn in files:
                    entries.append((root, fn, False))
                if self.dirs.get():
                    for dn in dirs:
                        entries.append((root, dn, True))
        else:
            for fn in os.listdir(d):
                isdir = os.path.isdir(os.path.join(d, fn))
                if isdir and not self.dirs.get():
                    continue
                entries.append((d, fn, isdir))
        wrong, real = self.c_wrong.value(), self.c_real.value()
        n = 0
        for root, name, isdir in entries:
            base, ext = (name, "") if isdir else os.path.splitext(name)
            nfc = unicodedata.normalize("NFC", base)
            if nfc != base:
                # macOS decomposed name (か+゛): recompose, no code page involved
                fixed, w_, r_ = nfc, "NFD", "NFC"
            else:
                fixed, w_, r_ = textenc.repair_mojibake(base, wrong, real)
            if not fixed or fixed == base:
                continue
            newname = fixed + ext
            bad = textenc.invalid_filename_chars(newname)
            status = ""
            if bad:
                status = t("conv,invalid", "invalid char")
            elif os.path.exists(os.path.join(root, newname)) and _same_name(newname, name) is False:
                status = t("conv,exists", "exists")
            rel = os.path.relpath(os.path.join(root, name), d)
            iid = self.ntree.insert("", "end", text=rel, values=(newname, "%s→%s" % (w_, r_), status))
            self.name_rows[iid] = (root, name, newname)
            if not status:
                self.ntree.selection_add(iid)
            n += 1
        if n == 0:
            messagebox.showinfo(t("conv,title", "Converter"), t("conv,nothing", "No garbled names found."), parent=self.w)

    def do_rename(self):
        t = self.t
        done = []
        for iid in self.ntree.selection():
            root, old, new = self.name_rows.get(iid, (None, None, None))
            if root is None:
                continue
            src = os.path.join(root, old)
            dst = os.path.join(root, new)
            if os.path.exists(dst) and _same_name(old, new) is False:
                self.ntree.set(iid, "status", t("conv,exists", "exists"))
                continue
            try:
                os.rename(src, dst)
                done.append((dst, src))
                self.ntree.set(iid, "status", t("conv,renamed", "renamed"))
            except OSError as e:
                self.ntree.set(iid, "status", str(e))
        if done:
            self.undo.append(done)
        messagebox.showinfo(t("conv,title", "Converter"), t("conv,done", "Done") + " (%d)" % len(done), parent=self.w)

    def undo_rename(self):
        if not self.undo:
            return
        done = self.undo.pop()
        for dst, src in reversed(done):
            try:
                os.rename(dst, src)
            except OSError:
                pass
        self.scan_names()

    # ---------------------------------------------------------------- text

    def _build_text_tab(self, nb):
        t = self.t
        f = tk.Frame(nb)
        nb.add(f, text=t("conv,tabText", "Text repair"))
        tk.Label(f, text=t("conv,textNote", "Paste garbled text:"), anchor="w").pack(fill="x")
        self.tin = tk.Text(f, height=6)
        self.tin.pack(fill="x")
        tk.Button(f, text=t("conv,repair", "Repair"), command=self.repair_text).pack(anchor="w")
        self.tout = ttk.Treeview(f, columns=("how", "score"), selectmode="browse")
        self.tout.heading("#0", text=t("conv,candidate", "Candidate"))
        self.tout.heading("how", text=t("conv,how", "Method"))
        self.tout.heading("score", text="score")
        self.tout.column("#0", width=600)
        self.tout.pack(fill="both", expand=1)

        def copy(e):
            sel = self.tout.selection()
            if sel:
                self.w.clipboard_clear()
                self.w.clipboard_append(self.tout.item(sel[0], "text"))
        self.tout.bind("<Double-1>", copy)

    def repair_text(self):
        self.tout.delete(*self.tout.get_children())
        text = self.tin.get("1.0", "end-1c")
        for gain, fixed, w_, r_ in textenc.repair_candidates(text):
            self.tout.insert("", "end", text=fixed, values=("%s→%s" % (w_, r_), "%.1f" % gain))

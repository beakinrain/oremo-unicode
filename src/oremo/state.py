"""Program state kept in Tcl global arrays (v, f0, power, ...).

The original stored everything in Tcl arrays and bound widgets to array
elements with -textvariable / -variable / -listvariable.  Keeping the state
in the Tcl interpreter embedded in tkinter lets this rewrite bind widgets the
same way and write oremo-init.tcl in exactly the original format.
"""

import tkinter as tk

from . import tclfmt


class TclArray:
    def __init__(self, tkapp, name):
        self.tk = tkapp
        self.name = name

    def var(self, key):
        return "%s(%s)" % (self.name, key)

    def exists(self, key):
        return self.tk.getboolean(self.tk.call("info", "exists", self.var(key)))

    def _raw(self, key):
        return self.tk.globalgetvar(self.var(key))

    def __getitem__(self, key):
        val = self._raw(key)
        if isinstance(val, tuple):
            return tclfmt.format_list([str(x) for x in val])
        if isinstance(val, str):
            return val
        return str(val)

    def get(self, key, default=""):
        if not self.exists(key):
            return default
        return self[key]

    def __setitem__(self, key, value):
        if isinstance(value, (list, tuple)):
            self.tk.call("set", self.var(key), tuple(str(x) for x in value))
        elif isinstance(value, bool):
            self.tk.globalsetvar(self.var(key), 1 if value else 0)
        elif isinstance(value, float):
            self.tk.globalsetvar(self.var(key), value)
        else:
            self.tk.globalsetvar(self.var(key), value)

    def lst(self, key):
        if not self.exists(key):
            return []
        val = self._raw(key)
        if isinstance(val, tuple):
            return [str(x) for x in val]
        return [str(x) for x in self.tk.splitlist(val)]

    def i(self, key, default=0):
        try:
            v = self._raw(key)
            if isinstance(v, (int, float)):
                return int(v)
            s = str(v).strip()
            if s == "":
                return default
            return int(float(s))
        except Exception:
            return default

    def f(self, key, default=0.0):
        try:
            v = self._raw(key)
            if isinstance(v, (int, float)):
                return float(v)
            s = str(v).strip()
            if s == "":
                return default
            return float(s)
        except Exception:
            return default

    def b(self, key):
        try:
            return self.tk.getboolean(self._raw(key))
        except Exception:
            return self.i(key) != 0

    def incr(self, key, n=1):
        val = self.i(key) + n
        self[key] = val
        return val

    def unset(self, key):
        try:
            self.tk.call("unset", "-nocomplain", self.var(key))
        except tk.TclError:
            pass

    def unset_all(self):
        self.tk.call("array", "unset", self.name)

    def keys(self):
        return [str(k) for k in self.tk.splitlist(self.tk.call("array", "names", self.name))]

    def items(self):
        out = []
        for k in self.keys():
            out.append((k, self[k]))
        return out

    def snapshot(self, keys=None):
        if keys is None:
            keys = self.keys()
        out = {}
        for k in keys:
            if self.exists(k):
                out[k] = self._raw(k)
        return out

    def restore(self, snap):
        for k, v in snap.items():
            if isinstance(v, tuple):
                self.tk.call("set", self.var(k), v)
            else:
                self.tk.globalsetvar(self.var(k), v)


class TVar(tk.StringVar):
    """StringVar bound to an existing Tcl variable (e.g. 'v(fftlen)') that is
    *not* unset when the Python object is garbage collected."""

    def __init__(self, master, name):
        self._tk = master.tk
        self._root = master._root()
        self._name = name
        self._tclCommands = None
        if not self._tk.getboolean(self._tk.call("info", "exists", name)):
            self._tk.globalsetvar(name, "")

    def __del__(self):
        pass

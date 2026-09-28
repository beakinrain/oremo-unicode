"""Minimal Tcl syntax support.

OREMO keeps its settings in ``oremo-init.tcl`` and its UI messages in
``message/*-text.tcl``.  Both files only contain ``set name(key) value``
commands.  The original program *sourced* them as Tcl scripts; this rewrite
parses them without evaluating anything, so the file formats stay 100%
compatible while arbitrary code can no longer be executed.
"""

import re

_BS_MAP = {
    "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
}


def _backslash(s, i):
    """Parse a backslash sequence starting at s[i] == '\\'. Returns (text, next_i)."""
    if i + 1 >= len(s):
        return "\\", i + 1
    c = s[i + 1]
    if c in _BS_MAP:
        return _BS_MAP[c], i + 2
    if c == "\n":
        # backslash-newline: replaced by a single space, eats leading blanks
        j = i + 2
        while j < len(s) and s[j] in " \t":
            j += 1
        return " ", j
    if c == "x":
        m = re.match(r"[0-9a-fA-F]{1,2}", s[i + 2:])
        if m:
            return chr(int(m.group(0), 16)), i + 2 + len(m.group(0))
        return "x", i + 2
    if c == "u":
        m = re.match(r"[0-9a-fA-F]{1,4}", s[i + 2:])
        if m:
            return chr(int(m.group(0), 16)), i + 2 + len(m.group(0))
        return "u", i + 2
    if c == "U":
        m = re.match(r"[0-9a-fA-F]{1,8}", s[i + 2:])
        if m:
            try:
                return chr(int(m.group(0), 16)), i + 2 + len(m.group(0))
            except ValueError:
                pass
        return "U", i + 2
    if c in "01234567":
        m = re.match(r"[0-7]{1,3}", s[i + 1:])
        return chr(int(m.group(0), 8) & 0xFF), i + 1 + len(m.group(0))
    return c, i + 2


def _parse_braced(s, i):
    """s[i] == '{'. Returns (text, next_i). Backslashes stay literal except \\-newline."""
    depth = 1
    j = i + 1
    out = []
    while j < len(s):
        c = s[j]
        if c == "\\" and j + 1 < len(s):
            if s[j + 1] == "\n":
                t, j = _backslash(s, j)
                out.append(t)
                continue
            out.append(s[j:j + 2])
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return "".join(out), j + 1
        out.append(c)
        j += 1
    return "".join(out), j  # unbalanced: take the rest


def _parse_quoted(s, i):
    """s[i] == '"'. Backslash substitution only ($ and [ are kept literally)."""
    j = i + 1
    out = []
    while j < len(s):
        c = s[j]
        if c == "\\":
            t, j = _backslash(s, j)
            out.append(t)
            continue
        if c == '"':
            return "".join(out), j + 1
        out.append(c)
        j += 1
    return "".join(out), j


def _parse_bare(s, i):
    j = i
    out = []
    while j < len(s):
        c = s[j]
        if c in " \t\n;":
            break
        if c == "\\":
            t, j = _backslash(s, j)
            out.append(t)
            continue
        out.append(c)
        j += 1
    return "".join(out), j


def parse_commands(script):
    """Split a Tcl script into a list of commands (each a list of words)."""
    cmds = []
    s = script.replace("\r\n", "\n").replace("\r", "\n")
    i = 0
    n = len(s)
    while i < n:
        # skip white space and command separators
        while i < n and s[i] in " \t\n;":
            i += 1
        if i >= n:
            break
        if s[i] == "#":
            # comment up to an unescaped newline
            while i < n and s[i] != "\n":
                if s[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                i += 1
            continue
        words = []
        while i < n and s[i] not in "\n;":
            if s[i] in " \t":
                i += 1
                continue
            if s[i] == "\\" and i + 1 < n and s[i + 1] == "\n":
                i += 2
                continue
            if s[i] == "{":
                w, i = _parse_braced(s, i)
            elif s[i] == '"':
                w, i = _parse_quoted(s, i)
            else:
                w, i = _parse_bare(s, i)
            words.append(w)
        if words:
            cmds.append(words)
    return cmds


_NAME_RE = re.compile(r"^([^()]+)\((.*)\)\]*$", re.S)


def split_varname(name):
    """'v(recList)' -> ('v', 'recList'); 'foo' -> ('foo', None)."""
    m = _NAME_RE.match(name)
    if m:
        return m.group(1), m.group(2)
    return name, None


def parse_set_file(script):
    """Return list of (array, key, value) for every ``set a(k) v`` command.

    Other commands are ignored.
    """
    out = []
    for words in parse_commands(script):
        if len(words) >= 3 and words[0] == "set":
            arr, key = split_varname(words[1])
            out.append((arr, key, words[2]))
    return out


def unsafe_lines(script):
    """Lines the original OREMO's 'simple sanitizing' would have rejected."""
    bad = []
    for line in script.replace("\r\n", "\n").split("\n"):
        if re.match(r"^[ \t]*$", line):
            continue
        if re.match(r"^[ \t]*(;|)[ \t]*#", line):
            continue
        l2 = line.replace("\\[", "")
        if re.match(r"^[ \t]*set[ \t]+[^;\[]+$", l2):
            continue
        bad.append(line)
    return bad


# --------------------------------------------------------------------------
# Writing

def _braces_balanced(s):
    depth = 0
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0


def quote_braced(value):
    """Represent *value* as a Tcl word the way OREMO's saveSettings did.

    OREMO wrote ``{value}`` and escaped '[' as '\\['.  If the value cannot be
    put in braces (unbalanced braces / trailing backslash) a quoted word with
    full backslash escaping is produced instead.
    """
    v = value.replace("[", "\\[")
    if _braces_balanced(v) and not v.endswith("\\") and "\n" not in v:
        return "{" + v + "}"
    return quote_string(value)


def quote_string(value):
    out = ['"']
    for c in value:
        if c in '\\"$[]{}':
            out.append("\\" + c)
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        elif c == "\r":
            out.append("\\r")
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


def list_element(e, first=True):
    """Format one element of a Tcl list ('#' only needs quoting in front)."""
    if e == "":
        return "{}"
    if re.search(r'[\s{}\[\]"$\\;]', e) or (first and e.startswith("#")):
        if _braces_balanced(e) and not e.endswith("\\"):
            return "{" + e + "}"
        return quote_string(e)
    return e


def format_list(items):
    return " ".join(list_element(str(x), i == 0) for i, x in enumerate(items))


def split_list(s):
    """Parse a Tcl list string into Python list of strings."""
    out = []
    i = 0
    n = len(s)
    while i < n:
        while i < n and s[i] in " \t\n\r":
            i += 1
        if i >= n:
            break
        if s[i] == "{":
            w, i = _parse_braced(s, i)
        elif s[i] == '"':
            w, i = _parse_quoted(s, i)
        else:
            j = i
            buf = []
            while j < n and s[j] not in " \t\n\r":
                if s[j] == "\\":
                    t, j = _backslash(s, j)
                    buf.append(t)
                    continue
                buf.append(s[j])
                j += 1
            w, i = "".join(buf), j
        out.append(w)
    return out


# --------------------------------------------------------------------------
# Message substitution ("eval format $t(...)" replacement)

_SUBST_RE = re.compile(r"\$\{([^}]*)\}|\$([A-Za-z0-9_:]+)(\(([^)]*)\))?")


def substitute(template, ctx):
    """Replace $var / $arr(key) / ${var} by values from ctx.

    ctx maps names to plain values or to mapping objects (for arrays).
    Unknown references are left untouched.  Unlike the original ``eval
    format`` this never executes code and never truncates the text at white
    space, '%' or '[' contained in file names.
    """
    def repl(m):
        if m.group(1) is not None:
            name, idx = m.group(1), None
        else:
            name, idx = m.group(2), m.group(4)
        if name not in ctx:
            return m.group(0)
        val = ctx[name]
        if idx is not None:
            try:
                return str(val[idx])
            except Exception:
                return m.group(0)
        if isinstance(val, (list, tuple)):
            return format_list(val)
        return str(val)
    return _SUBST_RE.sub(repl, template)


def strip_outer_quotes(s):
    """Message values like '"$n 個..."' carry literal quotes (from \\"...\\")."""
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s

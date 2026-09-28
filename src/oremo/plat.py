"""Platform specific helpers (Windows / macOS)."""

import os
import shutil
import sys
import unicodedata

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def resource_dir():
    """Folder with the bundled resources (reclists, guideBGM, message, ...)."""
    if getattr(sys, "frozen", False):
        if IS_MAC:
            # PyInstaller .app: data files live under sys._MEIPASS
            return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "res")
        return os.path.dirname(os.path.abspath(sys.executable))
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "res"))


def user_dir(topdir):
    """Folder for files OREMO writes (oremo-setting.ini, oremo-init.tcl).

    Windows: next to the program like the original.  macOS: an .app bundle
    is read only, so ~/Library/Application Support/OREMO is used.
    """
    if not IS_MAC:
        return topdir
    d = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "OREMO")
    os.makedirs(d, exist_ok=True)
    ini = os.path.join(d, "oremo-setting.ini")
    src = os.path.join(topdir, "oremo-setting.ini")
    if not os.path.exists(ini) and os.path.exists(src):
        try:
            shutil.copyfile(src, ini)
        except OSError:
            pass
    return d


def default_save_dir(topdir):
    if not IS_MAC:
        return os.path.join(topdir, "result")
    d = os.path.join(os.path.expanduser("~"), "Documents", "OREMO", "result")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def nfc(s):
    """macOS may hand out decomposed names (か+゛ instead of が); compare in NFC."""
    return unicodedata.normalize("NFC", s) if s else s


def mac_system_lang():
    """'zh_CN' / 'ja' / 'en' from the macOS preferred languages."""
    try:
        import subprocess
        out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True,
                             text=True, timeout=3).stdout
        for line in out.splitlines():
            code = line.strip().strip('",()').lower()
            if not code:
                continue
            if code.startswith("zh"):
                return "zh_CN"
            if code.startswith("ja"):
                return "ja"
            return "en"
    except Exception:
        pass
    return ""


def mac_font_missing_chars(family, chars):
    """Characters of *chars* missing in *family* (CoreText).  '' if unknown."""
    try:
        import ctypes
        import ctypes.util
        cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
        ct = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreText"))
        cf.CFStringCreateWithCharacters.restype = ctypes.c_void_p
        cf.CFStringCreateWithCharacters.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        ct.CTFontCreateWithName.restype = ctypes.c_void_p
        ct.CTFontCreateWithName.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_void_p]
        ct.CTFontCopyFamilyName.restype = ctypes.c_void_p
        ct.CTFontCopyFamilyName.argtypes = [ctypes.c_void_p]
        ct.CTFontGetGlyphsForCharacters.restype = ctypes.c_bool
        ct.CTFontGetGlyphsForCharacters.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                    ctypes.c_long]
        chars = "".join(c for c in chars if ord(c) < 0x10000)
        if not chars:
            return ""
        name = (ctypes.c_uint16 * len(family))(*[ord(c) for c in family])
        cfname = cf.CFStringCreateWithCharacters(None, name, len(family))
        font = ct.CTFontCreateWithName(cfname, 20.0, None)
        cf.CFRelease(cfname)
        if not font:
            return ""
        try:
            n = len(chars)
            uni = (ctypes.c_uint16 * n)(*[ord(c) for c in chars])
            glyphs = (ctypes.c_uint16 * n)()
            ct.CTFontGetGlyphsForCharacters(font, uni, glyphs, n)
            return "".join(chars[i] for i in range(n) if glyphs[i] == 0)
        finally:
            cf.CFRelease(font)
    except Exception:
        return ""

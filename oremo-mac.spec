# PyInstaller spec for macOS (Apple Silicon): builds dist/OREMO.app
# usage (on a Mac):  pyinstaller oremo-mac.spec --noconfirm
# KOREDE is included as "OREMO --korede" (Tools menu).

import os

here = os.path.abspath(".")
VERSION = "3.0.190106"

a = Analysis(
    [os.path.join("src", "oremo_main.py")],
    pathex=[os.path.join(here, "src")],
    binaries=[],
    datas=[("res", "res")],
    hiddenimports=["sounddevice", "_sounddevice_data", "korede_main"],
    excludes=["matplotlib", "scipy", "pandas", "IPython", "pytest", "setuptools"],
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="OREMO",
          console=False, argv_emulation=False, target_arch="arm64",
          icon=os.path.join("res", "oremo.ico"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="OREMO")
app = BUNDLE(
    coll,
    name="OREMO.app",
    icon=os.path.join("res", "oremo.ico"),
    bundle_identifier="io.github.beakinrain.oremo",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "OREMO",
        "CFBundleName": "OREMO",
        "CFBundleShortVersionString": VERSION,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription":
            "OREMO 需要使用麦克风来录制音源。 / OREMO records your voice for UTAU voicebanks.",
        "LSApplicationCategoryType": "public.app-category.music",
    },
)

# PyInstaller spec: builds oremo.exe and korede.exe sharing one runtime folder.
# usage:  .venv\Scripts\pyinstaller oremo.spec --noconfirm

import os

block_cipher = None
here = os.path.abspath(".")

a = Analysis(
    [os.path.join("src", "oremo_main.py"), os.path.join("src", "korede_main.py")],
    pathex=[os.path.join(here, "src")],
    binaries=[],
    datas=[],
    hiddenimports=["sounddevice", "_sounddevice_data"],
    excludes=["matplotlib", "scipy", "PIL", "pandas", "IPython", "pytest", "setuptools"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

scripts_oremo = [s for s in a.scripts if s[0] != "korede_main"]
scripts_korede = [s for s in a.scripts if s[0] != "oremo_main"]

exe_oremo = EXE(pyz, scripts_oremo, [], exclude_binaries=True, name="oremo",
                console=False, icon=os.path.join("res", "oremo.ico"))
exe_korede = EXE(pyz, scripts_korede, [], exclude_binaries=True, name="korede",
                 console=False, icon=os.path.join("res", "oremo.ico"))

coll = COLLECT(exe_oremo, exe_korede, a.binaries, a.zipfiles, a.datas,
               strip=False, upx=False, name="OREMO")

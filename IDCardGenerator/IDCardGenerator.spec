# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for ID Card Generator.

Quick build:
    .\build.ps1

Manual build:
    .\venv\Scripts\python.exe -m PyInstaller IDCardGenerator.spec --noconfirm

Output:  dist\IDCardGenerator\IDCardGenerator.exe  (onedir layout)

Runtime dependencies NOT bundled (must be installed on target machine):
  - Tesseract OCR  https://github.com/UB-Mannheim/tesseract/wiki
    (OCR auto-detection is optional; the app works without it)
"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# ── base Python paths (needed for TCL/TK when building from a venv) ───────────
_PY_HOME = r"C:\Users\HARI\AppData\Local\Programs\Python\Python313"
_TCL_SRC = os.path.join(_PY_HOME, "tcl", "tcl8.6")
_TK_SRC  = os.path.join(_PY_HOME, "tcl", "tk8.6")

# ── data files ────────────────────────────────────────────────────────────────
_datas = [
    # Default config shipped with the app
    ("config", "config"),
    # OpenCV data directory — contains haarcascade_frontalface_default.xml etc.
    *collect_data_files("cv2"),
]

# TCL/TK runtime (tkinter GUI toolkit — required for the app to start)
if os.path.isdir(_TCL_SRC):
    _datas.append((_TCL_SRC, "tcl/tcl8.6"))
if os.path.isdir(_TK_SRC):
    _datas.append((_TK_SRC, "tcl/tk8.6"))

# ── analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ["app.py"],
    pathex=[os.path.abspath(".")],
    binaries=collect_dynamic_libs("cv2"),   # cv2.pyd + opencv DLLs
    datas=_datas,
    hiddenimports=[
        # tkinter — not always auto-detected from a venv
        "tkinter", "tkinter.ttk",
        "tkinter.filedialog", "tkinter.messagebox", "tkinter.colorchooser",
        "_tkinter",
        # Pillow — ImageEnhance imported conditionally inside functions so
        # PyInstaller's static analyser misses it; list explicitly here.
        "PIL", "PIL._tkinter_finder",
        "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont",
        "PIL.ImageTk", "PIL.ImageChops", "PIL.ImageEnhance",
        # pandas
        "pandas", "pandas._libs.parsers",
        "pandas._libs.hashtable", "pandas._libs.lib",
        # openpyxl
        "openpyxl",
        "openpyxl.styles.stylesheet",
        "openpyxl.styles.styleable",
        "openpyxl.cell._writer",
        # pytesseract (wraps the external Tesseract binary — not bundled)
        "pytesseract",
        # OpenCV + NumPy
        "cv2",
        "numpy", "numpy.core._multiarray_umath",
        # app modules (belt-and-suspenders — analyser should find these via
        # the import chain from app.py, but list them to be safe)
        "card_generator", "photo_editor", "face_extract_editor",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # keep the bundle small — none of these are used
        "matplotlib", "scipy", "sklearn", "tensorflow", "torch",
        "IPython", "jupyter", "notebook", "pytest", "sphinx",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="IDCardGenerator",
    debug=False,
    strip=False,
    upx=False,       # UPX off — triggers antivirus false positives
    console=False,   # windowed GUI, no black console window
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="IDCardGenerator",
)

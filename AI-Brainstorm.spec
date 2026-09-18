# -*- mode: python ; coding: utf-8 -*-
"""
Single-file Windows build.

    pyinstaller --noconfirm --clean AI-Brainstorm-release.spec
    -> dist/AI-Brainstorm-release.exe

The app is stdlib-only, so nothing here needs hidden imports. What this
spec DOES do is throw out the parts of the stdlib and of Tcl/Tk that
PyInstaller pulls in transitively but the app never reaches — see
EXCLUDES and the a.datas filter below. Everything excluded was verified
against the app's actual import list (base64/json/logging/mimetypes/os/
queue/re/ssl/subprocess/threading/tkinter/urllib/webbrowser/ctypes).
"""

# Stdlib packages nothing in the app (or in its transitive imports)
# reaches. Two families are deliberately NOT excluded:
#  - email: http.client parses response headers with email.parser.
#  - copyreg: re imports it at module level (for pickling compiled
#    patterns), so excluding it kills the app at startup, inside
#    PyInstaller's own inspect runtime hook. Verified the hard way.
EXCLUDES = [
    # dev/test tooling that ships with CPython
    "unittest", "doctest", "pydoc", "pydoc_data", "test", "lib2to3",
    "idlelib", "ensurepip", "venv", "distutils", "setuptools", "pip",
    "pkg_resources", "pdb", "bdb", "cProfile", "profile", "pstats",
    # third-party GUI/science stacks: absent here, but excluding them
    # keeps the build reproducible on a machine that does have them
    "numpy", "pandas", "matplotlib", "scipy", "PIL",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    # tkinter corners the app never touches
    "tkinter.test", "tkinter.tix", "tkinter.dnd", "turtle", "turtledemo",
    # stdlib subsystems with no call path from this app
    "sqlite3", "dbm", "xml", "xmlrpc", "html", "asyncio", "multiprocessing",
    "concurrent", "curses", "decimal", "_decimal", "tarfile", "bz2", "lzma",
    "ftplib", "imaplib", "smtplib", "poplib", "socketserver", "http.server",
    "argparse", "zoneinfo", "pickle", "pickletools",
]

# Tcl script modules under tcl8/ that a plain Tk GUI never sources.
# msgcat is deliberately kept — Tk's own file dialogs (filedialog, used
# by the export/attach-image buttons) load it for their button labels.
TCL_MODULE_DROPS = (
    "tcltest-", "http-", "opt-", "platform-", "shell-", "tdbc", "sqlite3-",
)


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # fonts/ carries Manrope + JetBrains Mono, which theme.py registers
    # into the process at startup (see register_bundled_fonts). Without
    # them the app still runs, in Segoe UI / Consolas.
    datas=[('favicon.ico', '.'), ('fonts', 'fonts')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,  # strip docstrings + asserts from bundled bytecode
)

a.datas = [
    entry for entry in a.datas
    if not (entry[0].replace("\\", "/").startswith("tcl8/")
            and any(drop in entry[0] for drop in TCL_MODULE_DROPS))
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AI-Brainstorm-release',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,          # honored only if upx is on PATH; silently skipped otherwise
    upx_exclude=[
        # UPX-packing these two corrupts them on some Windows builds
        'vcruntime140.dll', 'python311.dll',
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['favicon.ico'],
)

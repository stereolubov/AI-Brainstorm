# -*- coding: utf-8 -*-
"""
One-command single-file build.

    python build.py              -> dist/AI-Brainstorm-release.exe  (windowed)
    python build.py --console    -> same, but with a console attached

The app itself is stdlib-only; PyInstaller is the single build-time
dependency. The --console build exists because a windowed onefile exe
that fails during startup dies silently with exit code 1 and nothing to
read — the console build prints the traceback instead. Reach for it
whenever a release build stops launching (a too-aggressive entry in the
spec's EXCLUDES is the usual cause).

All build knobs live in AI-Brainstorm.spec, not here.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(ROOT, "AI-Brainstorm.spec")
DIST = os.path.join(ROOT, "dist")


def _console_spec():
    """Writes a throwaway copy of the spec with console=True and a
    distinct exe name, so a diagnostic build never overwrites (or gets
    confused with) the real release artifact."""
    source = open(SPEC, encoding="utf-8").read()
    patched = re.sub(r"^(\s*)console=False,", r"\1console=True,", source, flags=re.M)
    patched = patched.replace("AI-Brainstorm-release", "AI-Brainstorm-console")
    path = os.path.join(tempfile.gettempdir(), "AI-Brainstorm-console.spec")
    # PyInstaller resolves the spec's relative paths (main.py, favicon.ico)
    # against its own --workpath/CWD, so build this from ROOT.
    open(path, "w", encoding="utf-8").write(patched)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--console", action="store_true",
                        help="build with a console window to see startup tracebacks")
    parser.add_argument("--keep-work", action="store_true",
                        help="keep the intermediate build/ directory")
    args = parser.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("PyInstaller is not installed. Run:  pip install pyinstaller")

    spec = _console_spec() if args.console else SPEC
    work = os.path.join(ROOT, "build")

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--distpath", DIST,
        "--workpath", work,
        spec,
    ]
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        sys.exit(result.returncode)

    if not args.keep_work:
        shutil.rmtree(work, ignore_errors=True)

    name = "AI-Brainstorm-console.exe" if args.console else "AI-Brainstorm-release.exe"
    exe = os.path.join(DIST, name)
    if os.path.exists(exe):
        print(f"\n  {exe}  ({os.path.getsize(exe) / 1048576:.2f} MB)")
    else:
        sys.exit(f"Build reported success but {exe} is missing.")


if __name__ == "__main__":
    main()

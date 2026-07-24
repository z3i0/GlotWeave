#!/usr/bin/env python3
"""
Build Script for GlotWeave Installer
====================================
1. Compiles Python source code into a standalone directory using PyInstaller.
2. Compiles the resulting bundle into a Windows Setup (.exe) using Inno Setup (ISCC).
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path

# Reconfigure stdout/stderr encoding for Windows console compatibility
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from app.config import APP_VERSION

SPEC_FILE = PROJECT_ROOT / "instant_translator.spec"
ISS_FILE = PROJECT_ROOT / "installer.iss"
DIST_DIR = PROJECT_ROOT / "dist" / "GlotWeave"
OUTPUT_DIR = PROJECT_ROOT / "installer_output"

COMMON_ISCC_PATHS = [
    Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Inno Setup 5" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Inno Setup 5" / "ISCC.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
]


def kill_running_instances():
    """Ensure any running GlotWeave.exe instances are closed to avoid file lock issues."""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "GlotWeave.exe"], capture_output=True)
    except Exception:
        pass


def find_iscc() -> Path | None:
    """Find the Inno Setup Compiler executable on system PATH or default folders."""
    which_iscc = shutil.which("iscc") or shutil.which("iscc.exe")
    if which_iscc:
        return Path(which_iscc)

    for path in COMMON_ISCC_PATHS:
        if path.exists():
            return path
    return None


def run_pyinstaller() -> bool:
    """Run PyInstaller with instant_translator.spec."""
    print("=" * 60)
    print("Step 1: Building standalone bundle with PyInstaller...")
    print("=" * 60)
    
    kill_running_instances()
    if DIST_DIR.exists():
        try:
            shutil.rmtree(DIST_DIR, ignore_errors=True)
        except Exception:
            pass

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC_FILE)]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("\n[ERROR] PyInstaller build failed!")
        return False

    print("\n[OK] PyInstaller build complete! Directory created at:")
    print(f"   {DIST_DIR}\n")
    return True


def run_inno_setup(iscc_path: Path) -> bool:
    """Run Inno Setup Compiler to create the Windows Installer."""
    print("=" * 60)
    print("Step 2: Creating Windows Installer executable with Inno Setup...")
    print("=" * 60)
    print(f"Using ISCC at: {iscc_path}\n")

    cmd = [str(iscc_path), str(ISS_FILE)]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("\n[ERROR] Inno Setup compilation failed!")
        return False

    setup_exe = OUTPUT_DIR / f"GlotWeave_Setup_v{APP_VERSION}.exe"
    print("\n" + "=" * 60)
    print("[SUCCESS] Installer created successfully!")
    print("=" * 60)
    print(f"Setup File: {setup_exe}")
    print("You can now run or distribute this setup file to install GlotWeave on any Windows PC!\n")
    return True


def main():
    print(f"Starting GlotWeave Installer Build process in {PROJECT_ROOT}\n")

    # Step 1: PyInstaller build
    if not run_pyinstaller():
        sys.exit(1)

    # Step 2: Search for Inno Setup compiler
    iscc_path = find_iscc()
    if iscc_path:
        if not run_inno_setup(iscc_path):
            sys.exit(1)
    else:
        print("=" * 60)
        print("[WARNING] Inno Setup (ISCC.exe) was not found automatically on this machine.")
        print("=" * 60)
        print("PyInstaller successfully built the standalone application in:")
        print(f"  {DIST_DIR}\n")
        print(f"To generate the single-file setup installer (GlotWeave_Setup_v{APP_VERSION}.exe):")
        print("1. Download & install Inno Setup 6 (Free) from:")
        print("   https://jrsoftware.org/isdl.php")
        print("2. Run this script again: python scripts/build_installer.py")
        print("   OR right-click 'installer.iss' -> 'Compile' in Inno Setup.\n")


if __name__ == "__main__":
    main()

"""Resolve Concat binary from auto-installer or an existing Windows installation.

This module uses supported Concat --mcp interfaces; it never loads Concat
private databases or rewrites its own project format.
"""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def candidates() -> list[Path]:
    """Likely binaries, preserving explicit user override first."""
    paths: list[Path] = []
    custom = os.environ.get('LMK_CONCAT_EXE', '').strip().strip('"')
    if custom:
        paths.append(Path(custom))
    paths.append(ROOT / '.runtime' / 'concat' / 'concat.exe')
    home = os.environ.get('LOCALAPPDATA', '')
    pf = os.environ.get('ProgramFiles', '')
    pf86 = os.environ.get('ProgramFiles(x86)', '')
    if home:
        paths.extend([Path(home) / 'Programs' / 'Concat' / 'concat.exe',
                      Path(home) / 'Concat' / 'concat.exe'])
    if pf:
        paths.append(Path(pf) / 'Concat' / 'concat.exe')
    if pf86:
        paths.append(Path(pf86) / 'Concat' / 'concat.exe')
    found = shutil.which('concat')
    if found:
        paths.append(Path(found))
    return paths


def find_concat(override: str = '') -> str | None:
    if override:
        path = Path(override.strip().strip('"')).expanduser()
        if path.is_file():
            return str(path.resolve())
    for path in candidates():
        if path.is_file():
            return str(path.resolve())
    return None


def launch_concat(override: str = '') -> str:
    binary = find_concat(override)
    if not binary:
        raise FileNotFoundError('Chưa tìm thấy Concat. Chạy SETUP_ALL.cmd để cài Concat.')
    subprocess.Popen([binary], cwd=str(Path(binary).parent),
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return binary

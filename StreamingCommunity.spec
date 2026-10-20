# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_submodules

pkg = 'StreamingCommunity'

def _find_all_py_modules(package_dir):
    modules = []
    for root, dirs, files in os.walk(package_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            if f.endswith('.py') and f != '__init__.py':
                rel = os.path.relpath(os.path.join(root, f), '.')
                mod = rel.replace(os.sep, '.').rsplit('.py', 1)[0]
                modules.append(mod)
    return modules

def _find_all_init_packages(package_dir):
    packages = []
    for root, dirs, files in os.walk(package_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        if '__init__.py' in files:
            rel = os.path.relpath(root, '.').replace(os.sep, '.')
            packages.append(rel)
    return packages

def _find_data_files(package_dir, extensions=('.json', '.yaml', '.txt', '.dat', '.tcss')):
    files = []
    for root, dirs, filenames in os.walk(package_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in filenames:
            if f.endswith(extensions):
                src = os.path.join(root, f)
                rel = os.path.relpath(root, '.')
                files.append((src, rel))
    return files

all_modules = _find_all_py_modules(pkg)
all_packages = _find_all_init_packages(pkg)
data_files = _find_data_files(pkg)

# Modules never needed at runtime; dropping them shrinks the bundled PYZ.
#  - setuptools/pkg_resources/_distutils_hack (~1.6 MB): only referenced by
#    optional import shims (cffi build helpers, click's pkg_resources fallback).
#  - pydoc + pydoc_data (~0.7 MB): interactive help only.
#  - unittest/doctest/lib2to3: test tooling, unused at runtime.
#  - pygments (~4.2 MB): only reached via rich.syntax / rich.traceback /
#    textual.highlight, which are never imported on this app's startup path
#    (verified: all 220 package modules import fine without it). Trade-off:
#    textual's rich crash-screen for an unhandled TUI exception falls back to
#    a plain traceback.
# pdb/bdb/cmd/code must NOT be listed: `construct` (used by pywidevine) does a
# top-level `import pdb`.
excluded_modules = [
    'setuptools',
    'pkg_resources',
    '_distutils_hack',
    'pydoc',
    'pydoc_data',
    'doctest',
    'unittest',
    'lib2to3',
    'pygments',
]

datas = [('Conf', 'Conf')] + data_files
binaries = []
hiddenimports = (
    ['curl_cffi', '_cffi_backend']
    + all_packages
    + all_modules
    # Textual lazy-loads its widget modules at runtime (textual/widgets/__init__.py
    # uses importlib inside __getattr__), so PyInstaller's static analysis misses
    # them (e.g. "No module named 'textual.widgets._tab'"). Collect them all.
    + collect_submodules('textual')
)


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    noarchive=False,
    # 1 = strip assert statements from bundled bytecode. NOTE: 2 (-OO) is NOT
    # usable here - it also strips __doc__ strings, and pycparser's bundled ply
    # derives its C grammar from those docstrings, so cffi raises
    # "YaccError: Unable to build parser" at startup and the app dies.
    optimize=1,
)

# Ship only libraries the OS does not provide (libssl, libcrypto, libstdc++,
# libsqlite3, libncurses, ...). libpython and everything under lib-dynload is
# always kept. Saves several MB; the target machine must provide the usual
# system libraries (any desktop distro does).
a.exclude_system_libraries()

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='StreamingCommunity',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

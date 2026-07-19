# -*- mode: python ; coding: utf-8 -*-

import os

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

def _find_data_files(package_dir, extensions=('.json', '.yaml', '.txt', '.dat')):
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

datas = [('Conf', 'Conf')] + data_files
binaries = []
hiddenimports = ['curl_cffi', '_cffi_backend'] + all_packages + all_modules


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
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
    strip=False,
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

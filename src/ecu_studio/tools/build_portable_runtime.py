"""Build an inspectable Windows folder with unmodified CPython/Qt binaries.

Uses the installed, locked development runtime; no executable freezer,
bootloader, self-extraction, obfuscation, network download or AV exceptions.
The small C# starter's complete source ships alongside the portable runtime.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig


def copytree(source, target, *, extra_ignored=()):
    shutil.copytree(source,target,ignore=shutil.ignore_patterns(
        '__pycache__','*.pyc','tests','test',*extra_ignored))


def build():
    if sys.version_info[:2] != (3,13):raise RuntimeError('CPython 3.13 x64 required')
    root=Path(__file__).resolve().parents[3]
    output=root/'dist'/'ECU-Studio-AI-1.14-portable'
    # This script only replaces its own reproducible build output. Verify the
    # resolved absolute target before any recursive operation on Windows.
    if output.is_symlink() or output.resolve().parent != (root/'dist').resolve():
        raise ValueError('Portable output must remain inside the project dist directory')
    if output.exists():shutil.rmtree(output)
    runtime=output/'_internal'/'python'
    packages=runtime/'Lib'/'site-packages'
    app=output/'_internal'/'app'
    packages.mkdir(parents=True)
    base=Path(sys.base_prefix)
    installed=Path(sysconfig.get_paths()['purelib'])
    for name in ('python.exe','pythonw.exe','python3.dll','python313.dll',
                 'vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt'):
        shutil.copy2(base/name,runtime/name)
    # site-packages already exists, so merge the standard library explicitly.
    for path in (base/'Lib').iterdir():
        if path.name in {'site-packages','__pycache__','test','tests','tkinter','idlelib','turtledemo','ensurepip','venv'}:continue
        if path.is_dir():copytree(path,runtime/'Lib'/path.name)
        elif path.suffix=='.py':shutil.copy2(path,runtime/'Lib'/path.name)
    copytree(base/'DLLs',runtime/'DLLs',extra_ignored=('_tkinter.pyd','_test*.pyd'))
    (runtime/'python313._pth').write_text('.\nLib\nDLLs\nLib/site-packages\n../app\n',encoding='ascii')
    for name in ('numpy','numpy.libs','defusedxml','shiboken6'):
        copytree(installed/name,packages/name,extra_ignored=('include','*.lib','*.a'))
    qt_source=installed/'PySide6'
    qt=packages/'PySide6';qt.mkdir()
    copytree(qt_source/'support',qt/'support')
    modules={'QtCore.pyd','QtGui.pyd','QtWidgets.pyd','QtNetwork.pyd','QtTest.pyd'}
    dlls={'Qt6Core.dll','Qt6Gui.dll','Qt6Widgets.dll','Qt6Network.dll','Qt6Test.dll',
          'Qt6OpenGL.dll','Qt6Svg.dll','opengl32sw.dll','pyside6.abi3.dll'}
    for path in qt_source.iterdir():
        if path.is_file() and (path.suffix=='.py' or path.name in modules|dlls
                              or (path.suffix.lower()=='.dll' and path.name.lower().startswith(('msvcp','vcruntime','concrt')))):
            shutil.copy2(path,qt/path.name)
    for folder,names in {
        'platforms':('qwindows.dll','qoffscreen.dll','qminimal.dll'),
        'styles':('qmodernwindowsstyle.dll',),
        'imageformats':('qgif.dll','qico.dll','qjpeg.dll','qsvg.dll','qwebp.dll')}.items():
        target=qt/'plugins'/folder;target.mkdir(parents=True)
        for name in names:shutil.copy2(qt_source/'plugins'/folder/name,target/name)
    # License texts / package metadata accompany all redistributed components.
    for path in installed.glob('*.dist-info'):
        if path.name.lower().startswith(('numpy-','defusedxml-','shiboken6-','pyside6-','pyside6_essentials-','pyside6_addons-')):
            copytree(path,packages/path.name)
    copytree(root/'src'/'ecu_studio',app/'ecu_studio')
    shutil.copy2(root/'launcher.py',app/'launch.py')
    shutil.copy2(root/'packaging'/'windows_launcher.cs',output/'windows_launcher.cs')
    compiler=Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    exe=output/'ECU-Studio-AI-1.14.exe'
    subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+',
                    '/reference:System.Windows.Forms.dll','/out:'+str(exe),
                    str(root/'packaging'/'windows_launcher.cs')],check=True)
    (output/'RUNTIME_NOTICE.txt').write_text(
        'ECU Studio AI 1.14 portable\n'
        'C# starter source: windows_launcher.cs (process launch only).\n'
        'Unmodified CPython '+sys.version.split()[0]+' executables/DLLs; license: _internal/python/LICENSE.txt.\n'
        'Runtime is isolated through python313._pth; no installed Python required.\n'
        'Qt/PySide6, Shiboken, NumPy and defusedxml licenses: _internal/python/Lib/site-packages/*.dist-info.\n'
        'Replaceable dynamic libraries, application Python source and definitions are provided as ordinary files.\n'
        'No AV settings, exceptions, downloads, self-extraction or executable packing.\n',encoding='utf-8')
    # Relative-path integrity inventory; do not expose development environment.
    files=[{'path':p.relative_to(output).as_posix(),'size':p.stat().st_size,
            'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
           for p in sorted(output.rglob('*')) if p.is_file()]
    (output/'RUNTIME_INVENTORY.json').write_text(json.dumps({'format':1,'python':sys.version.split()[0],
        'architecture':'Windows x64','files':files},indent=2),encoding='utf-8')
    print(str(exe))
    return exe


if __name__=='__main__':build()

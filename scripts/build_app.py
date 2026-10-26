"""Build a native, self-contained application on its target OS."""
import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--install',action='store_true');parser.add_argument('--no-start',action='store_true');parser.add_argument('--no-autostart',action='store_true');args=parser.parse_args()
    system=platform.system();build=ROOT/'build';build.mkdir(exist_ok=True)
    imports=['dock_twoo','sherpa_onnx','kokoro_onnx','espeakng_loader','onnxruntime','sounddevice','tokenizers','grpc','truststore']
    spec='''from PyInstaller.utils.hooks import collect_all, collect_submodules
from pathlib import Path
import importlib.util
datas=[];binaries=[];hiddenimports=collect_submodules('dock_twoo')
'''
    for name in imports:
        spec+=f"if importlib.util.find_spec({name!r}):\n    d,b,h=collect_all({name!r});datas+=d;binaries+=b;hiddenimports+=h\n"
    spec+=f"a=Analysis([{str(ROOT/'scripts/app_entry.py')!r}],pathex=[{str(ROOT)!r}],hookspath=[{str(ROOT/'scripts/pyinstaller_hooks')!r}],datas=datas,binaries=binaries,hiddenimports=hiddenimports,excludes=['torch','transformers','tensorflow','pytest','matplotlib'])\n"
    spec+="pyz=PYZ(a.pure)\nexe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='DockTwoo',console=False)\ncoll=COLLECT(exe,a.binaries,a.datas,name='DockTwoo')\n"
    if system=='Darwin':
        spec+="app=BUNDLE(coll,name='DockTwoo.app',bundle_identifier='dev.karthikramesh.DockTwoo',info_plist={'LSUIElement':True,'NSMicrophoneUsageDescription':'Listen for your chosen assistant name and spoken requests.','NSSpeechRecognitionUsageDescription':'Convert your requests into text locally.'})\n"
    file=build/'DockTwoo.spec';file.write_text(spec)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(ROOT/'dist'),'--workpath',str(build/'freeze'),str(file)],check=True,cwd=ROOT)
    bundle=ROOT/'dist'/('DockTwoo.app' if system=='Darwin' else 'DockTwoo')
    exe=bundle/('Contents/MacOS/DockTwoo' if system=='Darwin' else 'DockTwoo.exe' if system=='Windows' else 'DockTwoo')
    subprocess.run([str(exe),'--verify-installation'],check=True,timeout=90)
    if system=='Windows':(bundle/'Install.cmd').write_text('@echo off\r\n"%~dp0DockTwoo.exe" --install %*\r\n')
    elif system=='Linux':
        launcher=bundle/'install.sh';launcher.write_text('#!/bin/sh\ncd "$(dirname "$0")" || exit 1\nexec ./DockTwoo --install "$@"\n');launcher.chmod(0o755)
    archive=shutil.make_archive(str(ROOT/'dist'/f'DockTwoo-{system}-{platform.machine()}'),'zip' if system!='Linux' else 'gztar',root_dir=bundle.parent,base_dir=bundle.name)
    print('Share this native package:',archive)
    if args.install:
        from dock_twoo.installation import install_bundle
        install_bundle(bundle,autostart=not args.no_autostart,start=not args.no_start)
if __name__=='__main__':main()

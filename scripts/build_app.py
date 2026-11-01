"""Build a native, self-contained application on its target OS."""
import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
def ensure_icons(root: Path):
    assets_dir = root / 'assets'
    logo = assets_dir / 'logo.png'
    if not logo.exists():
        return
    system = platform.system()
    if system == 'Darwin':
        icns = assets_dir / 'DockTwoo.icns'
        if not icns.exists() and shutil.which('sips') and shutil.which('iconutil'):
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                iconset = Path(tmpdir) / 'DockTwoo.iconset'
                iconset.mkdir()
                sizes = [
                    (16, 'icon_16x16.png'), (32, 'icon_16x16@2x.png'),
                    (32, 'icon_32x32.png'), (64, 'icon_32x32@2x.png'),
                    (128, 'icon_128x128.png'), (256, 'icon_128x128@2x.png'),
                    (256, 'icon_256x256.png'), (512, 'icon_256x256@2x.png'),
                    (512, 'icon_512x512.png'), (1024, 'icon_512x512@2x.png'),
                ]
                for sz, name in sizes:
                    subprocess.run(['sips', '-z', str(sz), str(sz), str(logo), '--out', str(iconset / name)], check=True, capture_output=True)
                subprocess.run(['iconutil', '-c', 'icns', str(iconset), '-o', str(icns)], check=True)
    elif system == 'Windows':
        ico = assets_dir / 'DockTwoo.ico'
        if not ico.exists():
            try:
                from PIL import Image
                img = Image.open(logo)
                img.save(ico, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
            except Exception:
                pass


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--install',action='store_true');parser.add_argument('--no-start',action='store_true');parser.add_argument('--no-autostart',action='store_true');args=parser.parse_args()
    ensure_icons(ROOT)
    system=platform.system();build=ROOT/'build';build.mkdir(exist_ok=True)
    icon_darwin = ROOT / 'assets' / 'DockTwoo.icns'
    icon_win = ROOT / 'assets' / 'DockTwoo.ico'
    imports=['dock_twoo','sherpa_onnx','kokoro_onnx','espeakng_loader','onnxruntime','sounddevice','tokenizers','grpc','truststore']
    spec=f'''from PyInstaller.utils.hooks import collect_all, collect_submodules
from pathlib import Path
import importlib.util
datas=[({str(ROOT/'assets')!r}, 'assets')];binaries=[];hiddenimports=collect_submodules('dock_twoo')
'''
    for name in imports:
        spec+=f"if importlib.util.find_spec({name!r}):\n    d,b,h=collect_all({name!r});datas+=d;binaries+=b;hiddenimports+=h\n"
    spec+=f"a=Analysis([{str(ROOT/'scripts/app_entry.py')!r}],pathex=[{str(ROOT)!r}],hookspath=[{str(ROOT/'scripts/pyinstaller_hooks')!r}],datas=datas,binaries=binaries,hiddenimports=hiddenimports,excludes=['torch','transformers','tensorflow','pytest','matplotlib'])\n"
    spec+="pyz=PYZ(a.pure)\n"
    exe_icon = f",icon={str(icon_darwin)!r}" if system=='Darwin' and icon_darwin.exists() else (f",icon={str(icon_win)!r}" if system=='Windows' and icon_win.exists() else "")
    spec+=f"exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='DockTwoo',console=False{exe_icon})\ncoll=COLLECT(exe,a.binaries,a.datas,name='DockTwoo')\n"
    if system=='Darwin':
        bundle_icon = f",icon={str(icon_darwin)!r}" if icon_darwin.exists() else ""
        spec+=f"app=BUNDLE(coll,name='DockTwoo.app',bundle_identifier='dev.karthikramesh.DockTwoo'{bundle_icon},info_plist={{'CFBundleIconFile':'DockTwoo.icns','CFBundleDisplayName':'Dock T(w)oo','CFBundleName':'Dock T(w)oo','LSUIElement':True,'NSMicrophoneUsageDescription':'Listen for your chosen assistant name and spoken requests.','NSSpeechRecognitionUsageDescription':'Convert your requests into text locally.'}})\n"
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

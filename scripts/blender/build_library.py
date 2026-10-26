"""Blender --background --python scripts/blender/build_library.py -- --id NAME."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from library.pipeline import build
p=argparse.ArgumentParser();p.add_argument('--id',required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);build(a.id)

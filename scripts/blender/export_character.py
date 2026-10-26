"""Export an individual saved project without rebuilding or saving over it.

blender --background characters/default/default.blend --python this_file -- --version 4.0.0
"""
import argparse,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from library.roster import ROSTER
from library.publish import export_saved
p=argparse.ArgumentParser();p.add_argument('--version',required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
if not re.fullmatch(r'\d+\.\d+\.\d+',a.version):raise ValueError('Use a semantic character version.')
identifier=Path(bpy.data.filepath).parent.name
desc=next((d for d in ROSTER if d['id']==identifier),None)
if desc is None:raise ValueError('Open a source from characters/<id>/<id>.blend first.')
print('BRAIN_RELEASE',export_saved(desc,a.version))

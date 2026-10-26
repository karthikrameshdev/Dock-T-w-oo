"""Build independent sources in bounded Blender processes; fail on Python errors too."""
import argparse,concurrent.futures,subprocess,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from library.roster import ROSTER
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--blender',default='/Applications/Blender.app/Contents/MacOS/Blender');p.add_argument('--jobs',type=int,default=3);p.add_argument('--ids',nargs='*');args=p.parse_args()
ids=args.ids or [d['id'] for d in ROSTER if d['id']!='default']
logdir=ROOT/'characters/build-logs';logdir.mkdir(exist_ok=True)
def build(identifier):
    path=logdir/(identifier+'.log')
    with path.open('w') as out:
        run=subprocess.run([args.blender,'--background','--threads','4','--python',str(ROOT/'scripts/blender/build_library.py'),'--','--id',identifier],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
    ok=run.returncode==0 and f'CHARACTER_COMPLETE {identifier} success=True' in path.read_text()
    print(('PASS ' if ok else 'FAIL ')+identifier,flush=True)
    return identifier,ok
with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(args.jobs,4))) as pool:results=dict(pool.map(build,ids))
(logdir/'results.json').write_text(json.dumps(results,indent=2)+'\n')
sys.exit(0 if all(results.values()) else 1)

"""Validate deliverable assets, provenance, anatomy and separate motion libraries."""
import hashlib,json,struct
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
LIB=ROOT/'characters'
CATALOG=json.loads((LIB/'catalog.json').read_text())

def test_complete_roster_and_default_migration():
    entries=CATALOG['characters'];ids=[e['id'] for e in entries]
    assert len(ids)==len(set(ids))==30
    assert CATALOG['default']=='default'
    assert {'robot','quadruped','bird','human'}=={e['family'] for e in entries}
    assert {'corgi','beagle','husky','tuxedo','calico','siamese','owl','parrot','robin','rat','lion','tiger'}<=set(ids)
    assert not (ROOT/'character').exists()
    assert not [p for p in (LIB/'default').rglob('*') if p.is_file() and 'brain' in p.name.lower()]
    assert (LIB/'default/default.blend').is_file()
    assert len({e['asset_sha256'] for e in entries})==30

@pytest.mark.parametrize('entry',CATALOG['characters'],ids=lambda e:e['id'])
def test_each_character_owns_a_valid_rig_export_and_action_library(entry):
    folder=LIB/entry['id'];source=folder/(entry['id']+'.blend');asset=folder/(entry['id']+'.glb')
    release=json.loads((folder/'character.json').read_text());audit=json.loads((folder/'validation.json').read_text())
    # Blender 5 saves Zstandard-compressed projects by default.
    assert source.read_bytes().startswith((b'BLENDER', b'\x28\xb5\x2f\xfd'))
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest(source)==release['source_sha256']==audit['source_sha256']
    assert digest(asset)==release['asset_sha256']==audit['asset_sha256']
    static=ROOT/'dock_twoo/server/static/brain3d/characters'/entry['id']
    assert digest(static/asset.name)==release['asset_sha256']
    data=asset.read_bytes();magic,version,length=struct.unpack_from('<4sII',data)
    assert magic==b'glTF' and version==2 and length==len(data)
    size,kind=struct.unpack_from('<II',data,12);assert kind==0x4E4F534A
    gltf=json.loads(data[20:20+size]);nodes={n.get('name'):n for n in gltf['nodes']}
    assert 'Antenna bulb' in nodes and 'antenna' in nodes
    assert len(gltf['skins'])==1
    if entry['family']=='bird':
        assert {'Tongue','Upper beak','Lower beak','Beak interior'}<=nodes.keys()
        assert 'Upper teeth' not in nodes
    else:
        assert {'Tongue','Upper teeth','Mouth cavity'}<=nodes.keys()
    assert len(gltf['animations'])==136
    assert {a['name'] for a in gltf['animations']}==set(release['actions'])
    assert audit['success'] and audit['independent_motion_signatures']>=120
    assert audit['samples']==136*25 and not audit['binding_errors'] and not audit['issues']
    assert all(a['channels'] and a['samplers'] for a in gltf['animations'])
    assert all(a['duration']>0 for a in release['actions'].values())
    assert all(m.get('alphaMode','OPAQUE')=='OPAQUE' for m in gltf['materials'])
    assert (folder/(entry['id']+'-preview.png')).is_file()
    if entry['family']=='bird':assert any('Primary feather' in n for n in nodes if n)
    if entry['family']=='quadruped':assert {'tail','ear.L','ear.R'}<=nodes.keys()
    if entry['id'] in ('rat','mouse'):
        assert nodes['Brain_Rig']['scale'][0]<.5


def test_bird_beaks_articulate_with_live_and_authored_speech():
    import shutil,subprocess
    node=shutil.which('node')
    if not node:pytest.skip('Node is required for the actual Three.js morph test')
    result=subprocess.run([node,str(ROOT/'scripts/verify_bird_beaks.mjs')],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr

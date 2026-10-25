"""Publish the local character catalog, gallery and a render contact sheet."""
import json,sys,html
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from library.roster import ROSTER
ROOT=Path(__file__).resolve().parents[2];LIB=ROOT/'characters';STATIC=ROOT/'dock_twoo/server/static/brain3d'
entries=[]
for desc in ROSTER:
    folder=LIB/desc['id'];manifest=folder/'character.json';audit=folder/'validation.json'
    data={**desc,'preview':f"characters/{desc['id']}/preview.png",'manifest':f"characters/{desc['id']}/character.json"}
    if manifest.exists():
        m=json.loads(manifest.read_text());data.update(actions=len(m['actions']),source=m['source'],asset_sha256=m['asset_sha256'])
    if audit.exists():data['distinct_motions']=json.loads(audit.read_text())['independent_motion_signatures']
    entries.append(data)
catalog={'version':'4.0.0','default':'default','characters':entries}
for path in (LIB/'catalog.json',STATIC/'catalog.json'):path.write_text(json.dumps(catalog,indent=2)+'\n')
style='''*{box-sizing:border-box}body{margin:0;color:#eaf2f3;background:#0d171d;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1400px;margin:auto;padding:48px 36px}header{display:flex;justify-content:space-between;gap:30px;align-items:end;margin-bottom:30px}.eyebrow{color:#7ce6cd;letter-spacing:.18em;font-size:11px;font-weight:700;text-transform:uppercase}h1{font-size:clamp(34px,5vw,64px);letter-spacing:-.05em;margin:14px 0}header p{color:#aabec7;max-width:620px;line-height:1.6}.stats{white-space:nowrap;color:#8db4bf;font-size:13px;margin-bottom:20px}.filters{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}button{background:#20313b;border:1px solid #34505c;border-radius:24px;padding:10px 18px;color:inherit;cursor:pointer}button.active{background:#a0efd8;border-color:#a0efd8;color:#14392e}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:18px}.card{background:linear-gradient(145deg,#24343e,#15252e);border:1px solid #344852;border-radius:20px;overflow:hidden;transition:transform .18s,border-color .18s}.card:hover{transform:translateY(-4px);border-color:#86ccba}.card[hidden]{display:none}.art{background:radial-gradient(ellipse at 50% 46%,#42576366,transparent 72%);position:relative}.art:after{content:"";position:absolute;left:25%;right:25%;bottom:16px;height:7px;border-radius:50%;background:#07121566;filter:blur(5px)}img{width:100%;height:260px;object-fit:contain;display:block;position:relative;z-index:1}.info{padding:14px 20px 20px}h2{font-size:20px;margin:0 0 6px}small{color:#a7bdc5;text-transform:capitalize}.links{display:flex;gap:12px;align-items:center;margin-top:15px;font-size:12px}.links a{color:#a0efd8;text-decoration:none}.links a:first-child{background:#a0efd8;color:#153c32;font-weight:700;padding:8px 13px;border-radius:8px}.count{font-size:11px;color:#7f9ba7;margin-top:12px}footer{font-size:12px;color:#8ca3ad;line-height:1.8;margin-top:36px}a:focus-visible,button:focus-visible{outline:3px solid #d5fbf1;outline-offset:4px}@media(max-width:600px){main{padding:28px 18px}header{display:block}.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}img{height:180px}.info{padding:12px}.links{flex-wrap:wrap}}'''
def gallery(local=False):
    cards=[]
    for d in entries:
        identifier=d['id'];preview=f'{identifier}/{identifier}-preview.png' if local else d['preview']
        model=f'{identifier}/{identifier}.blend' if local else f'characters/{identifier}/{identifier}.glb'
        previewlink=f'http://127.0.0.1:28842/brain3d/index.html?character={identifier}' if local else f'index.html?character={identifier}'
        cards.append(f'''<article class="card" data-family="{d['family']}"><div class="art"><img src="{preview}" alt="{html.escape(d['name'])}, {d['species'].replace('_',' ')} with an antenna" loading="lazy"></div><div class="info"><h2>{html.escape(d['name'])}</h2><small>{d['species'].replace('_',' ')} · {d['family']}</small><div class="count">{d.get('actions',136)} animations · own antenna</div><div class="links"><a href="{previewlink}">Explore motion ↗</a><a href="{model}" download>{'Blender source' if local else '3D model'}</a></div></div></article>''')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Brain · Companion library</title><style>'''+style+'''</style></head><body><main><header><div><div class="eyebrow">Brain / Companion collection</div><h1>A little personality.<br>A whole lot of motion.</h1><p>Meet thirty glossy desktop companions. Robots, animals, birds and people — each with an expressive face, an individual antenna and a full animation library.</p></div><div class="stats">30 companions &nbsp; / &nbsp; 136 clips each</div></header><nav class="filters" aria-label="Character family">'''+''.join(f'<button class="{"active" if k=="all" else ""}" data-filter="{k}">{v}</button>' for k,v in [('all','Everyone'),('robot','Robots'),('quadruped','Animals'),('bird','Birds'),('human','People')])+'''</nav><section class="grid" aria-label="Companions">'''+''.join(cards)+'''</section><footer>Smooth enamel and subtle gradients. Every character has a separate, editable Blender source and keyed action library.<br>Motion uses reusable procedural choreography adapted to each rig, including wings, paws, tails and articulated hands. The manifest in each folder lists all clips.</footer></main><script>document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b===button));document.querySelectorAll('[data-family]').forEach(card=>card.hidden=button.dataset.filter!=='all'&&card.dataset.family!==button.dataset.filter);}));</script></body></html>'''
(STATIC/'library.html').write_text(gallery());(LIB/'index.html').write_text(gallery(True))
if not all((LIB/d['id']/(d['id']+'-preview.png')).exists() for d in entries):
    print('Published provisional catalog; renders are still building');sys.exit()
from PIL import Image,ImageDraw,ImageFont
font_path='/System/Library/Fonts/Supplemental/Arial.ttf';font=ImageFont.truetype(font_path,23);small=ImageFont.truetype(font_path,16);title=ImageFont.truetype(font_path,42)
canvas=Image.new('RGB',(1920,1990),'#101e27');pen=ImageDraw.Draw(canvas)
pen.text((40,26),'BRAIN / COMPANION LIBRARY',font=title,fill='#e3f7f2');pen.text((42,81),'30 characters · 136 animations each · smooth glossy materials · individual antennas',font=small,fill='#8fc1bc')
for i,d in enumerate(entries):
    x=20+(i%6)*316;y=130+(i//6)*366
    pen.rounded_rectangle((x,y,x+302,y+352),radius=18,fill='#213440')
    image=Image.open(LIB/d['id']/(d['id']+'-preview.png')).convert('RGBA');image.thumbnail((290,284))
    canvas.paste(image,(x+6+(290-image.width)//2,y+3),image)
    pen.text((x+18,y+286),d['name'],font=font,fill='#e9f6f4')
    pen.text((x+18,y+318),d['species'].replace('_',' ').title()+'  /  136 clips',font=small,fill='#a3c7cc')
canvas.save(LIB/'library-contact-sheet.jpg',quality=94)
print('Published complete gallery and contact sheet')

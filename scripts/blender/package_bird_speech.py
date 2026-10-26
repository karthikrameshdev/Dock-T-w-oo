"""Package the native renders from render_bird_speech.py into a speech preview."""
import json,subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2]
frames_root=Path('/tmp/brain-bird-speech');combined=frames_root/'combined';combined.mkdir(parents=True,exist_ok=True)
font_path='/System/Library/Fonts/Supplemental/Arial.ttf'
font=ImageFont.truetype(font_path,20) if Path(font_path).exists() else ImageFont.load_default(size=20)
frames=[]
for index in range(48):
    canvas=Image.new('RGB',(1152,432),'#13242e');pen=ImageDraw.Draw(canvas)
    for col,(identifier,name) in enumerate([('owl','Luma · Owl'),('parrot','Rio · Parrot'),('robin','Pip · Robin')]):
        canvas.paste(Image.open(frames_root/identifier/f'{index:03d}.png').convert('RGB'),(col*384,0))
        pen.text((col*384+22,397),name,font=font,fill='#d5f1ea')
    canvas.save(combined/f'{index:03d}.png');frames.append(canvas)
palette_source=Image.new('RGB',(1152,432*6))
for row,index in enumerate([0,9,18,27,36,45]):palette_source.paste(frames[index],(0,row*432))
palette=palette_source.quantize(colors=192,method=Image.Quantize.MEDIANCUT)
converted=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in frames]
duration=json.loads((ROOT/'characters/owl/character.json').read_text())['actions']['talk']['duration']
converted[0].save(ROOT/'characters/bird-speech.gif',save_all=True,append_images=converted[1:],loop=0,duration=round(duration/48*1000),optimize=False,disposal=2)
subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate',str(48/duration),'-i',str(combined/'%03d.png'),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(ROOT/'characters/bird-speech.mp4')],check=True)
frames[22].save(ROOT/'characters/bird-speech-preview.jpg',quality=94)
print('Packaged three bird speech close-ups')

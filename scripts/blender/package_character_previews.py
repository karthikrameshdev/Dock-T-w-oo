"""Assemble locally rendered previews and encode a labeled animation reel."""
from pathlib import Path
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[2] / 'character'
font_path = '/System/Library/Fonts/Supplemental/Arial.ttf'
font = ImageFont.truetype(font_path, 22) if Path(font_path).exists() else ImageFont.load_default(size=22)
names = ['hero', 'back', 'climb', 'fly', 'talk', 'magnifier', 'camera', 'read', 'scan_code', 'drag', 'walk', 'run']
canvas = Image.new('RGB', (1536, 1200), '#14232e')
draw = ImageDraw.Draw(canvas)
for index, name in enumerate(names):
    im = Image.open(root / 'previews' / (name + '.png')).convert('RGBA').resize((384, 368))
    x, y = index % 4 * 384, index // 4 * 400
    canvas.paste(im, (x, y), im)
    draw.text((x + 18, y + 367), name.replace('_', ' ').title(), font=font, fill='#aeefff')
canvas.save(root / 'animation-contact-sheet.jpg', quality=94)
frames = root / 'previews' / 'reel-frames'
labels = root / 'previews' / 'reel-labels.txt'
if labels.exists() and len(list(frames.glob('*.png'))) == 576:
    # Label copies preserve raw renders and make repeated packaging idempotent.
    labeled = frames / 'labeled'
    labeled.mkdir(exist_ok=True)
    titles = labels.read_text().splitlines()
    for index in range(576):
        im = Image.open(frames / f'{index:04d}.png').convert('RGB')
        pen = ImageDraw.Draw(im)
        pen.rounded_rectangle((20, 18, 300, 56), radius=12, fill='#14232e')
        pen.text((32, 25), titles[index // 48], font=font, fill='#c8f8ff')
        im.save(labeled / f'{index:04d}.png', compress_level=1)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '24',
                    '-i', str(labeled / '%04d.png'), '-c:v', 'libx264', '-crf', '20',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                    str(root / 'MiniAssistant-actions.mp4')], check=True)
    shutil.rmtree(labeled)
print('Packaged previews in', root)

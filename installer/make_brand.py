"""Draw the MaxTrack steering wheel and tracking reticle icon."""
from pathlib import Path

from PIL import Image, ImageDraw

folder = Path(__file__).parent
icon = Image.new('RGBA', (256, 256))
draw = ImageDraw.Draw(icon)
draw.rounded_rectangle((6, 6, 249, 249), radius=54, fill='#131e2c', outline='#2b4358', width=6)
for x, y, dx, dy in [(49, 49, 1, 1), (207, 49, -1, 1), (49, 207, 1, -1), (207, 207, -1, -1)]:
    draw.line([(x, y+dy*24), (x, y), (x+dx*24, y)], fill='#61decd', width=8, joint='curve')
draw.ellipse((72, 72, 184, 184), outline='#edf6ff', width=12)
draw.line([(79, 116), (128, 136), (177, 116)], fill='#edf6ff', width=12)
draw.line([(128, 136), (128, 178)], fill='#edf6ff', width=12)
draw.ellipse((113, 121, 143, 151), fill='#61decd')
icon.save(folder / 'MaxTrackPro.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
badge = Image.new('RGB', (64, 64), '#131e2c')
badge.paste(icon.resize((64,64), Image.Resampling.LANCZOS), mask=icon.resize((64,64), Image.Resampling.LANCZOS).getchannel('A'))
badge.save(folder / 'MaxTrackPro-Wizard.bmp')

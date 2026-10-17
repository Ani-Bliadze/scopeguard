"""Contact sheet of the PowerPoint-rendered slides (pitch/qa/slide-NN.png -> pitch/qa/montage.png)."""

from pathlib import Path

from PIL import Image, ImageDraw

QA = Path(__file__).parent / "qa"
slides = sorted(QA.glob("slide-*.png"))
if len(slides) != 8:
    raise SystemExit(f"expected 8 rendered slides, found {len(slides)}; run pitch/render_deck.ps1")
W, H, PAD, COLS = 800, 450, 24, 2
rows = (len(slides) + COLS - 1) // COLS
sheet = Image.new("RGB", (COLS * W + (COLS + 1) * PAD, rows * (H + 34) + (rows + 1) * PAD), "#05080f")
draw = ImageDraw.Draw(sheet)
for i, path in enumerate(slides):
    r, c = divmod(i, COLS)
    x, y = PAD + c * (W + PAD), PAD + r * (H + 34 + PAD)
    sheet.paste(Image.open(path).convert("RGB").resize((W, H), Image.LANCZOS), (x, y + 30))
    draw.text((x, y + 6), f"Slide {i + 1}", fill="#9AA9C2")
sheet.save(QA / "montage.png")
print(f"wrote {QA / 'montage.png'} ({sheet.size[0]}x{sheet.size[1]})")

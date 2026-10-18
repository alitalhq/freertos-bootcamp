"""SystemView ekran görüntülerine numaralı işaret ve alt açıklama ekler.

Koordinatlar ham ekran görüntüsünün piksel koordinatlarıdır (Retina, 2832 genişlik).
Kullanım: python annotate.py   ->  screenshots/*_isaretli.png
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent / "screenshots"
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
RED, INK, BG = (208, 59, 59), (20, 20, 20), (255, 255, 255)


def annotate(src: str, dst: str, crop_bottom: int, marks: list, caption: list[str]) -> Path:
    im = Image.open(HERE / src).convert("RGB")
    im = im.crop((0, 0, im.width, crop_bottom))
    f = ImageFont.truetype(FONT_B, 34)
    fc = ImageFont.truetype(FONT, 34)
    fh = ImageFont.truetype(FONT_B, 38)
    pad, line_h = 28, 50
    band = pad * 2 + line_h * len(caption)
    out = Image.new("RGB", (im.width, im.height + band), BG)
    out.paste(im, (0, 0))
    d = ImageDraw.Draw(out)
    for n, (bx, by, text, tx, ty) in enumerate(marks, 1):
        label = f"{n}  {text}"
        w = d.textlength(label, font=f)
        d.line([(bx, by + 24), (tx, ty)], fill=RED, width=5)
        d.ellipse([tx - 9, ty - 9, tx + 9, ty + 9], fill=RED)
        d.rounded_rectangle([bx - 14, by - 8, bx + w + 14, by + 52], radius=10, fill=BG, outline=RED, width=4)
        d.text((bx, by), label, fill=RED, font=f)
    y = im.height + pad
    for i, line in enumerate(caption):
        d.text((pad, y), line, fill=INK, font=fh if i == 0 else fc)
        y += line_h
    p = HERE / dst
    out.save(p)
    return p


if __name__ == "__main__":
    # 1 · CPU beklemesi (A-S5t2, basış #18). Hedefler: EXTI15_10 kesmesi, telemetry işi, button Ready çizgisi.
    print(annotate("1_cpu_bekleme_ham.png", "1_cpu_bekleme_isaretli.png", 1000, [
        (700, 735, "t0: basış (EXTI15_10 kesmesi)", 556, 727),
        (2120, 745, "telemetry (öncelik 3): 5 ms CPU işi", 1900, 883),
        (1560, 1010 - 110, "button hazır ama CPU alamıyor: 5,1 ms", 1350, 963),
    ], [
        "A/S5 · basış #18 · CPU beklemesi (t1 − t0 = 5,2 ms)",
        "Basış, telemetri 5 ms'lik işini yaparken geldi. ButtonTask hazır (Ready) ama önceliği (2) telemetriden (3) düşük: 5,1 ms CPU bekledi.",
        "Bu sırada telemetri TEL mesajını kuyruğa koyup son boş yeri aldı; buton yanıtı kuyruğa giremedi ve düştü (BTN_DROP).",
        "Ödev 2'deki A/S5 kayıplarının nedeni: kuyruk doluyken son yere telemetri önce varıyor.",
    ]))

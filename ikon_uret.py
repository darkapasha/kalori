"""İkonlar: koyu zemin, yeşil ilerleme halkası, ortada çatal-bıçak."""
from pathlib import Path
from PIL import Image, ImageDraw
WEB = Path(__file__).resolve().parent / "web"
def ciz(boy):
    s = 4; B = boy * s
    im = Image.new("RGB", (B, B), (15, 20, 18)); d = ImageDraw.Draw(im)
    m = B * 0.16; w = int(B * 0.085)
    d.arc([m, m, B - m, B - m], 0, 360, fill=(33, 43, 38), width=w)
    d.arc([m, m, B - m, B - m], -90, 200, fill=(74, 222, 128), width=w)
    c = (238, 243, 239); lw = int(B * 0.03)
    # çatal
    x = B * 0.43; ust = B * 0.33; alt = B * 0.68
    for dx in (-0.045, 0, 0.045):
        d.line([x + B * dx, ust, x + B * dx, B * 0.45], fill=c, width=int(lw * 0.8))
    d.rounded_rectangle([x - B * 0.06, B * 0.44, x + B * 0.06, B * 0.49], radius=B * 0.02, fill=c)
    d.line([x, B * 0.47, x, alt], fill=c, width=lw)
    # bıçak
    x2 = B * 0.58
    d.pieslice([x2 - B * 0.05, ust, x2 + B * 0.05, B * 0.55], 180, 270, fill=c)
    d.rectangle([x2 - B * 0.005, ust, x2 + B * 0.035, B * 0.5], fill=c)
    d.line([x2 + B * 0.012, B * 0.5, x2 + B * 0.012, alt], fill=c, width=lw)
    return im.resize((boy, boy), Image.LANCZOS)
for ad, b in (("ikon-192.png", 192), ("ikon-512.png", 512), ("apple-touch-icon.png", 180)):
    ciz(b).save(WEB / ad)
print("ikonlar tamam")

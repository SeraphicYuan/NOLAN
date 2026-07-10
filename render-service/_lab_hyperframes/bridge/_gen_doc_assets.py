"""Generate placeholder document pages for the `document` block demo (run with Windows nolan python
so PIL + Windows fonts are available). Writes into videos/doc-demo/assets/."""
import os, random
from PIL import Image, ImageDraw, ImageFont
random.seed(7)
OUT = r"D:/ClaudeProjects/NOLAN/render-service/_lab_hyperframes/videos/doc-demo/assets"
os.makedirs(OUT, exist_ok=True)
FD = "C:/Windows/Fonts/"
def F(name, sz):
    try: return ImageFont.truetype(FD + name, sz)
    except Exception: return ImageFont.load_default()

def textbars(d, x, y, w, lh, n, shade=118, jitter=0.22, gap=1.0):
    for i in range(n):
        ll = int(w * random.uniform(1 - jitter, 0.99))
        d.rounded_rectangle([x, y, x + ll, y + int(lh * 0.44)], radius=3, fill=(shade, shade, shade))
        y += int(lh * gap)
    return y

def doc_page(path, w, h, header, sub, bold_at=(), bg=(252, 251, 247)):
    img = Image.new("RGB", (w, h), bg); d = ImageDraw.Draw(img)
    m = int(w * 0.075); y = int(h * 0.05)
    d.text((m, y), header, font=F("timesbd.ttf", int(w * 0.030)), fill=(28, 26, 22)); y += int(w * 0.05)
    if sub:
        d.text((m, y), sub, font=F("times.ttf", int(w * 0.017)), fill=(95, 92, 85)); y += int(w * 0.035)
    lh = int(h * 0.026); li = 0
    while y < h - m:
        if li in bold_at:  # a darker "heading" line the highlight can target
            d.rounded_rectangle([m, y, m + int((w - 2 * m) * 0.66), y + int(lh * 0.5)], radius=3, fill=(40, 38, 34))
            y += int(lh * 1.5)
        else:
            y = textbars(d, m, y, w - 2 * m, lh, 1)
        li += 1
    img.save(path)

# 1) a wide prospectus page (page mode; highlight targets the bold lines)
doc_page(OUT + "/docpage.png", 1600, 1180, "SPACEX  ·  FORM S-1  REGISTRATION STATEMENT",
         "Item 5.02  Compensation of the founder and certain performance milestones",
         bold_at=(6, 13))

# 2) a web article (page mode; highlight the headline)
def article(path, w, h):
    img = Image.new("RGB", (w, h), (255, 255, 255)); d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, int(h * 0.055)], fill=(245, 245, 245))
    d.text((int(w * 0.04), int(h * 0.016)), "GALLUP    News   Politics   Economy   World", font=F("arialbd.ttf", int(w * 0.017)), fill=(30, 30, 30))
    m = int(w * 0.07); y = int(h * 0.11)
    d.text((m, y), "In U.S., 4% Identify as Vegetarian,", font=F("timesbd.ttf", int(w * 0.045)), fill=(20, 20, 20)); y += int(w * 0.06)
    d.text((m, y), "1% as Vegan", font=F("timesbd.ttf", int(w * 0.045)), fill=(20, 20, 20)); y += int(w * 0.075)
    d.rectangle([m, y, w - m, y + int(h * 0.24)], fill=(214, 210, 204)); y += int(h * 0.27)
    textbars(d, m, y, w - 2 * m, int(h * 0.03), 9)
    img.save(path)
article(OUT + "/article.png", 1400, 1500)

# 3) three doc pages for a stack
for i in range(1, 4):
    doc_page(OUT + f"/stack{i}.png", 900, 1180, f"SPACEX PROSPECTUS  —  page {180 + i}", "", bold_at=())

# 4) two aged letters (artifact mode)
def letter(path, w, h, seed):
    random.seed(seed)
    img = Image.new("RGB", (w, h), (233, 223, 199)); d = ImageDraw.Draw(img)
    # aged blotches
    for _ in range(40):
        x, yy = random.randint(0, w), random.randint(0, h); r = random.randint(20, 90)
        d.ellipse([x - r, yy - r, x + r, yy + r], fill=(228, 216, 190))
    # ink calligraphy: vertical columns of squiggly strokes
    for col in range(4):
        cx = int(w * (0.22 + col * 0.16)); yy = int(h * 0.12)
        while yy < h * 0.82:
            pts = [(cx + random.randint(-14, 14), yy + k * 12) for k in range(6)]
            d.line(pts, fill=(35, 30, 26), width=random.randint(3, 6), joint="curve")
            yy += random.randint(70, 110)
    # a red seal
    sx, sy = int(w * 0.30), int(h * 0.80)
    d.ellipse([sx - 34, sy - 34, sx + 34, sy + 34], outline=(150, 30, 28), width=6)
    img.save(path)
letter(OUT + "/letter1.png", 700, 930, 11)
letter(OUT + "/letter2.png", 700, 930, 22)

print("generated:", sorted(os.listdir(OUT)))

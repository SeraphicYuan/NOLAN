from PIL import Image
names = ["st_va", "st_ca", "st_tx", "st_gaky"]
imgs = [Image.open(f"snapshots/{n}/frame-00-at-5.0s.png") for n in names]
w, h = imgs[0].size
sw, sh = w // 2, h // 2
grid = Image.new("RGB", (sw * 2, sh * 2), "white")
for i, im in enumerate(imgs):
    grid.paste(im.resize((sw, sh)), ((i % 2) * sw, (i // 2) * sh))
grid.save("snapshots/states-grid.png")
print("grid saved:", grid.size)

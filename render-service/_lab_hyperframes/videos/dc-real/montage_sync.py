from PIL import Image
order = ["3.5","8.7","13.5","16.6","24.3","25.9"]
imgs=[Image.open(f"out/sync/t_{t}.png") for t in order]
w,h=imgs[0].size; sw,sh=w//2,h//2   # 2 cols x 3 rows
g=Image.new("RGB",(sw*2,sh*3),"white")
for i,im in enumerate(imgs): g.paste(im.resize((sw,sh)),((i%2)*sw,(i//2)*sh))
g.save("out/sync-grid.png"); print("saved",g.size)

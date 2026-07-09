from PIL import Image
files = ["frame-00-at-3.5s.png","frame-01-at-8.0s.png","frame-02-at-12.5s.png"]
imgs=[Image.open(f"snapshots/f1/{f}") for f in files]
w,h=imgs[0].size; sw,sh=w//2,h//2   # 960x540 tiles stacked -> 960x1620
g=Image.new("RGB",(sw,sh*3),"white")
for i,im in enumerate(imgs): g.paste(im.resize((sw,sh)),(0,i*sh))
g.save("snapshots/f1-grid.png"); print("saved",g.size)

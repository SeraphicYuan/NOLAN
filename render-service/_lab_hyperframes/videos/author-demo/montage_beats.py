from PIL import Image
files = ["frame-00-at-4.5s.png","frame-01-at-10.5s.png","frame-02-at-17.5s.png","frame-03-at-24.5s.png"]
imgs=[Image.open(f"snapshots/beats/{f}") for f in files]
w,h=imgs[0].size; sw,sh=w//2,h//2
g=Image.new("RGB",(sw*2,sh*2),"white")
for i,im in enumerate(imgs): g.paste(im.resize((sw,sh)),((i%2)*sw,(i//2)*sh))
g.save("snapshots/beats-grid.png"); print("saved",g.size)

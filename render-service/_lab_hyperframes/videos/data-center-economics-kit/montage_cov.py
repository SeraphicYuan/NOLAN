from PIL import Image
files = ["frame-00-at-15.0s.png","frame-01-at-55.0s.png","frame-02-at-85.0s.png","frame-03-at-104.0s.png","frame-04-at-140.0s.png"]
imgs = [Image.open(f"snapshots/coverage/{f}") for f in files]
w,h = imgs[0].size; sw,sh = w//2, h//2
# 5 tiles -> 3 rows x 2 cols
grid = Image.new("RGB",(sw*2, sh*3),"white")
for i,im in enumerate(imgs):
    grid.paste(im.resize((sw,sh)), ((i%2)*sw,(i//2)*sh))
grid.save("snapshots/coverage-grid.png"); print("saved", grid.size)

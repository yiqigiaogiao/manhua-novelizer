import sys, os
from PIL import Image

src = sys.argv[1]
out = sys.argv[2]
box = [float(x) for x in sys.argv[3].split(',')]  # x0,y0,x1,y1 normalized
im = Image.open(src).convert('L')
W,H = im.size
x0,y0,x1,y1 = int(box[0]*W), int(box[1]*H), int(box[2]*W), int(box[3]*H)
crop = im.crop((x0,y0,x1,y1))
scale = 3
crop = crop.resize((crop.width*scale, crop.height*scale), Image.LANCZOS)
crop.save(out, quality=95)
print(out, crop.size)

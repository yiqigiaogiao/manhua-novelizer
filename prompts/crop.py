import sys
from PIL import Image

src = sys.argv[1]
out = sys.argv[2]
box = [float(x) for x in sys.argv[3].split(',')]
im = Image.open(src).convert('RGB')
W,H = im.size
x0,y0,x1,y1 = int(box[0]*W), int(box[1]*H), int(box[2]*W), int(box[3]*H)
c = im.crop((x0,y0,x1,y1)).resize(((x1-x0)*3, (y1-y0)*3), Image.LANCZOS)
c.save(out, quality=95)
print(out, c.size)

import sys
from PIL import Image, ImageOps, ImageEnhance

src = sys.argv[1]
out = sys.argv[2]
im = Image.open(src).convert('L')
im = ImageOps.invert(im)
im = ImageEnhance.Contrast(im).enhance(2.0)
im = ImageOps.autocontrast(im, cutoff=0.5)
im.save(out, quality=95)
print(out, im.size)

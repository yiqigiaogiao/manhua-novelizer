import sys
from PIL import Image, ImageOps, ImageEnhance

src = sys.argv[1]
out = sys.argv[2]
im = Image.open(src).convert('L')
im = ImageOps.autocontrast(im, cutoff=1)
im = ImageEnhance.Contrast(im).enhance(2.5)
im.save(out, quality=95)
print(out, im.size)

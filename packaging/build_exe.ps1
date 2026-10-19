# 构建单文件 exe（需先 pip install pyinstaller）
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

Write-Host "== 生成图标 =="
python -c @"
from PIL import Image, ImageDraw
sizes=[16,24,32,48,64,128,256]
base=Image.new('RGBA',(256,256),(0,0,0,0))
d=ImageDraw.Draw(base)
d.rounded_rectangle([16,16,240,240], radius=44, fill=(32,36,44,255))
d.rounded_rectangle([54,44,176,206], radius=10, fill=(238,232,220,255))
d.rounded_rectangle([176,44,202,206], radius=6, fill=(196,88,72,255))
for y in (80,112,144,176):
    d.rounded_rectangle([72,y,158,y+8], radius=4, fill=(120,110,100,255))
base.save('packaging/icon.ico', sizes=[(s,s) for s in sizes])
"@

Write-Host "== PyInstaller =="
python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name ManhuaNovelizer --icon packaging\icon.ico `
    --distpath dist --workpath build\pyinstaller --specpath build `
    packaging\entry.py

Write-Host "== 自检 =="
& .\dist\ManhuaNovelizer.exe --selftest

Write-Host ""
Write-Host "完成：dist\ManhuaNovelizer.exe"

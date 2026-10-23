# -*- coding: utf-8 -*-
"""Windows 内置 OCR（Windows.Media.Ocr）提取页面对白。

无需第三方依赖；使用系统已安装的 zh-Hans-CN 识别器。
输出格式与 ocr_pages.py 保持一致：
{"pages":[{"page":1,"coverage":0.18,"lines":[{"text":"…","bbox":[x0,y0,x1,y1],"conf":0.93}]}]}
bbox 为归一化坐标。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile

PS_TEMPLATE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) {
    $m = $asTaskGeneric.MakeGenericMethod($type)
    $t = $m.Invoke($null, @($op))
    $t.Wait(-1) | Out-Null
    $t.Result
}
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$lang = New-Object Windows.Globalization.Language 'zh-Hans-CN'
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
if ($null -eq $engine) { Write-Error 'no zh-Hans-CN OCR engine'; exit 2 }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:OCR_IMAGE)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$w = [double]$decoder.PixelWidth
$h = [double]$decoder.PixelHeight
$out = New-Object System.Collections.ArrayList
foreach ($line in $result.Lines) {
    $minX = [double]::MaxValue; $minY = [double]::MaxValue; $maxX = 0.0; $maxY = 0.0
    foreach ($word in $line.Words) {
        $r = $word.BoundingRect
        if ($r.X -lt $minX) { $minX = $r.X }
        if ($r.Y -lt $minY) { $minY = $r.Y }
        if (($r.X + $r.Width) -gt $maxX) { $maxX = $r.X + $r.Width }
        if (($r.Y + $r.Height) -gt $maxY) { $maxY = $r.Y + $r.Height }
    }
    if ($minX -eq [double]::MaxValue) { continue }
    [void]$out.Add([pscustomobject]@{
        text = $line.Text
        bbox = @([math]::Round($minX/$w,4), [math]::Round($minY/$h,4),
                 [math]::Round($maxX/$w,4), [math]::Round($maxY/$h,4))
        w = $w; h = $h
    })
}
$out | ConvertTo-Json -Depth 5 -Compress
"""


def ocr_image(path: str) -> list[dict]:
    script = os.path.join(tempfile.gettempdir(), "_winocr_run.ps1")
    with open(script, "w", encoding="utf-8-sig") as fh:
        fh.write(PS_TEMPLATE)
    env = dict(os.environ)
    env["OCR_IMAGE"] = path
    proc = subprocess.run(["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass",
                           "-File", script],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)
    if proc.returncode != 0:
        raise SystemExit(f"Windows OCR 失败：{proc.stderr.strip()[:500]}")
    raw = proc.stdout.strip()
    if not raw:
        return []
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    lines = []
    for item in data:
        text = (item.get("text") or "").strip()
        if text:
            lines.append({"text": text, "bbox": item["bbox"], "conf": 0.9})
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="Windows 内置 OCR 提取对白")
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--direction", default="ltr", choices=["ltr", "rtl"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start-page", type=int, default=1)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.pages, "p[0-9]*.jpg")) +
                   glob.glob(os.path.join(args.pages, "p[0-9]*.png")))
    pages = []
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as fh:
            pages = json.load(fh).get("pages", [])
    done = {p["page"] for p in pages}

    todo = []
    for idx, path in enumerate(files, start=1):
        if idx < args.start_page or idx in done:
            continue
        todo.append((idx, path))
    if args.limit:
        todo = todo[: args.limit]

    for idx, path in todo:
        lines = ocr_image(path)
        rows = {}
        for line in lines:
            key = round((line["bbox"][1] + line["bbox"][3]) / 2, 2)
            rows.setdefault(key, []).append(line)
        ordered = []
        for key in sorted(rows):
            rows[key].sort(key=lambda l: l["bbox"][0], reverse=(args.direction == "rtl"))
            ordered.extend(rows[key])
        area = sum((l["bbox"][2] - l["bbox"][0]) * (l["bbox"][3] - l["bbox"][1])
                   for l in ordered)
        pages.append({"page": idx, "coverage": round(min(area, 1.0), 3), "lines": ordered})
        print(f"page {idx}: {len(ordered)} lines coverage={round(area,3)}", file=sys.stderr)
        pages.sort(key=lambda p: p["page"])
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"pages": pages, "engine": "winocr", "direction": args.direction},
                      fh, ensure_ascii=False, indent=1)

    pages.sort(key=lambda p: p["page"])
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"pages": pages, "engine": "winocr", "direction": args.direction},
                  fh, ensure_ascii=False, indent=1)
    print(json.dumps({"pages": len(pages), "new_pages": len(todo), "out": args.out},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

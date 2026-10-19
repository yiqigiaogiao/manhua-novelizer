# 打包成 exe

## 一键构建

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1
```

产物：`dist\ManhuaNovelizer.exe`（单文件，双击即用，无需装 Python）。

## 手动构建

```powershell
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name ManhuaNovelizer --icon packaging\icon.ico ^
  --distpath dist --workpath build\pyinstaller --specpath build ^
  packaging\entry.py
```

## 验证

```powershell
.\dist\ManhuaNovelizer.exe --selftest
```

应输出版本号与依赖信息（pymupdf / pillow / python-docx / tkinter），`"frozen": true` 表示确实在 exe 内运行。

## 三种运行方式

| 方式 | 命令 |
|---|---|
| 图形界面 | 双击 `ManhuaNovelizer.exe` |
| 自检 | `ManhuaNovelizer.exe --selftest` |
| 命令行 | `ManhuaNovelizer.exe build --work work --out build --title "书名"` |

## 说明

- **体积**：单文件约 90–150 MB（打包了 PyMuPDF 与 Pillow）。启动首次解压约 3–8 秒，属正常。
- **杀软误报**：PyInstaller onefile 偶尔被启发式误判，可改用 `--onedir` 生成目录版，或给 exe 做代码签名。
- **不要放在中文路径的只读目录**：onefile 启动时会解压到 `%TEMP%`，路径含特殊字符偶发失败。
- **升级**：改完代码重新跑一次构建脚本即可；`dist/` 与 `build/` 已在 `.gitignore` 里，不提交。
- **发布**：把 `dist\ManhuaNovelizer.exe` 上传到 GitHub Release，不要提交进仓库（>100 MB 会被拒）。

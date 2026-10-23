# Manhua Novelizer · 漫画转小说 Skill

把**只有图、没有文本层**的中文漫画 PDF，按原作叙事风格转成小说，并导出成书。

```
PDF 页图 ──► 页脚本 JSON ──► 章脉络(+state) ──► 正文(读 style.md) ──► 质检
             (逐格转录)       (合并成场)         (按原作风格写)      (台词/事件/忠实)
                                                                    │
                                        全本一致性审计 ◄────────────┘
                                    (年龄/建模/死亡/时间线)
```

## 形态

这是一个 **skill**，不是软件包：

```
manhua-novelizer/
├─ SKILL.md                  agent 主入口（先读这个）
├─ prompts/                  00–08，写作各阶段的提示词
├─ references/               改编原则、流程、schema、风格配置规范
├─ scripts/                  确定性工作：拆页、质检、审计、成书、清理
└─ examples/                 合成示例
```

- **脚本**负责机器能判的事：拆页、阅读顺序、台词覆盖、一致性、成书、清理。
- **agent** 负责需要理解的事：风格分析、逐页转录、写正文。它读 `SKILL.md` 与 `prompts/`。
- **不需要 API**：脚本不联网；agent 那边本来就有模型。

## 安装

```bash
git clone <repo> && cd manhua-novelizer
pip install pymupdf pillow          # 必需
pip install python-docx             # 可选，导出 docx
pip install zhconv                  # 推荐：台版/港版繁体原稿的台词覆盖会失真，不装则退化
```

> `zhconv` 只影响 `check_prose.py` 的台词覆盖比对：装上后繁体原稿（「話」「來」）
> 会归一成简体再比对；**没装也能跑**，只是繁简混排的稿子可能被误判漏台词。

## 快速开始

```bash
# 1) 建清单 / 拆页 / 合本拆章
python scripts/build_manifest.py --dir pdf --out work/manifest.csv
python scripts/prep_pages.py --pdf "pdf/001.pdf" --out work/ch001/pages
python scripts/split_book.py --pdf book.pdf --out chapters      # 一册几十话时

# 1b) 话级覆盖清单（源里有几话，就登记几话）★ 覆盖闸门的基准
python scripts/build_chapter_map.py --src 源目录 --out work/chapter-map.csv
#   源里是整卷时声明每卷覆盖哪些话：
#   python scripts/build_chapter_map.py --src 源目录 --out work/chapter-map.csv \
#       --volumes "1:1-5,2:6-10,3:11-15"

# 2) 阅读顺序（拆页之后、转录之前）
python scripts/detect_order.py --pages work/ch001/pages --work work
python scripts/detect_order.py --set rtl --work work

# 3) 风格配置（必须，写作前置）
python scripts/style_config.py --action init --work work
#   → agent 按 prompts/00-style-analysis.md 填写 work/style.json
python scripts/style_config.py --action render --work work      # 出 style.md
python scripts/style_config.py --action confirm --work work     # 确认后才批量写
python scripts/style_config.py --action check --work work       # 未确认/有空维度 → 退出码 1

# 4) 写作交给 agent：prompts/01 → 02 → 03 → 04

# 5) 质检 / 审计 / 成书 / 清理
python scripts/check_prose.py --draft work/ch001/draft.md --outline work/ch001/outline.json --bible work/bible.md
python scripts/check_consistency.py --work work --bible work/bible.md --out work/audit/consistency.md

# 5b) 覆盖闸门：源里几话都写了、都出书了？缺一话就红
python scripts/check_coverage.py --map work/chapter-map.csv --work work --books 出书目录
python scripts/check_ready.py --work work --check-qa --chapter-map work/chapter-map.csv

# 6) 成书（给了 chapter-map 就先过覆盖闸门，覆盖不全拒绝出书）
python scripts/assemble.py --work work --out work/build --title "书名" \
    --chapter-map work/chapter-map.csv

# 7) 全本合并：把已出的各卷（含番外）合成一部完整小说
python scripts/merge_books.py --books 出书目录 --out 全本 \
    --title "书名" --formats md docx epub
#   对账不过（章节数对不上 / 跨卷重复）会拒绝合并，不会悄悄丢话
```

## 七项要求的落点

| 要求 | 实现 |
|---|---|
| PNG 及时清理 | `scripts/clean_pages.py`（`--dry-run` / `--confirm` / `--keep`）；**唯一的删除入口，`assemble.py` 不删页图** |
| 取消字数上下限 | 配置无 `length_per_page`；`check_prose.py` 不查长度；提示词写"不写字数目标" |
| 取消禁用词、情节优先 | 无 `banned_words`；质检改为台词覆盖 / 事件完整性 / 忠实度 / 声音 / 风格 |
| mobi、png 格式 | `assemble.py` 出 md/docx/epub/**mobi** + **cover.png**；`prep_pages.py --format png`。MOBI 是内置 PalmDOC 写出器（不依赖 calibre），**本地阅读器（Kindle 设备/KOReader/Calibre）可读取**；体积偏大（无压缩），**未经 Kindle 邮件推送验证**，推送请先用 `ebook-convert book.epub book.mobi`（calibre）二次转换 |
| 软件形式 | `scripts/` 提供完整命令行工具链（无需安装成包） |
| 叙事风格配置（前置） | 八维度、要依据、`confirmed` 闸门、`style_history/` 版本快照 |
| 改编原则 | `references/principles.md`：五级优先级、视觉转译、对白、十二条 AI 式补写、A/B/C、自检 |

## 叙事风格配置

八个维度：叙事节奏、情绪表达、对白特征、画面转译、信息揭示、描写密度、特有表达习惯、禁止破坏的特征。

- 每条都要给**原作依据**，资料不足标 `尚未确认`，不许凭空假设。
- 保存时自动把上一版快照到 `work/style_history/`，改风格前后可对比。
- `--action check` 在"未确认"或"仍有空维度"时返回非 0，可以当写作前的闸门。
- 配置是**判断依据，不是套版**：整体偏慢的作品，战斗场仍应快；常用留白的作品，不是每场都留白。

## 阅读顺序

`scripts/detect_order.py` 给方向 + 置信度 + 依据：

- 竖排文字气泡多 → 倾向 `rtl`（日式漫画）
- 横排文字气泡多 → 倾向 `ltr`
- 页面高/宽 > 2.6 → `ttb`（纵向条漫）
- 上半页气泡整体偏右 → 倾向 `rtl`

置信度 < 0.6 不要直接采信；人工确认流程见 `prompts/08-reading-order.md`。
`--set rtl/ltr/ttb` 会把方向连同 `confidence` / `confirmed: true` 一起写进
`config.json`；未确认（`confirmed` 非 true）时，`check_ready.py` 会以
「阅读方向未人工确认」拒绝成书——无人值守批量也不会被默认 `ltr` 蒙混。

## 输出与清理

成书前先把引号统一（台版/日式原稿常见的「」要换成“”）：

```bash
python scripts/normalize_quotes.py --work work --check   # 先看有多少
python scripts/normalize_quotes.py --work work           # 「」→“”、『』→‘’
```

- 成书：`book.md` / `book.docx` / `book.epub` / `book.mobi` / `cover.png` / `stats.csv` / `index.csv`
- 中间页图常有几百 MB 到几 GB。**页图是 S6.7 原图复检的事实源，`assemble.py` 不会删它**；
  确认全书核对无误后，由人显式执行唯一删除入口：

```bash
python scripts/clean_pages.py --work work --dry-run                 # 先看会删多少、省多少
python scripts/clean_pages.py --work work --confirm                 # 确认无误，真删
python scripts/clean_pages.py --work work --confirm --after-verify  # 只删过了复检的章
python scripts/clean_pages.py --work work --keep work/ch001/pages   # 留某一话
```

  没有 `--confirm` 一律只报不删。页图被删掉后就再也没法核对"描述与画面不一致"，
  所以这一步永远是**人工显式动作**，不进任何自动化流水线。

## 省 token：别每页都喂视觉模型

逐页读图约 1.5k token/页，182 页就是 27 万视觉 token。可以按页面分流：

| 方案 | 成本 | 适合 |
|---|---|---|
| 本地 OCR（`scripts/ocr_pages.py`） | 0 视觉 token | 对话密集页 |
| OCR + 400px 缩略图 | ≈15% | 默认推荐 |
| 本地视觉模型（Qwen2.5-VL / MiniCPM-V） | 电费 | 有显卡、量大 |
| API 视觉模型 | 100% | 战斗页、跨页、关键揭示 |

开源组合：`comic-text-detector`（切气泡）→ `PaddleOCR/RapidOCR`（识别，含竖排）→ `magi`（分格排序、文字归属说话人），
再接文本模型写 `page_script.json`。详见 `references/cheap-vision.md` 与 `prompts/01b-page-script-from-ocr.md`。

只删 `.jpg/.jpeg/.png`，正文、JSON、清单、圣经、风格配置都保留。

## 质量闸门

| 检查 | 合格线 | 谁做 |
|---|---|---|
| 台词覆盖（原文对白逐字落地） | **100%** | `scripts/check_prose.py` |
| **转录完整性**（`page_script.json` 的对白格 vs `outline.quotes`） | **不缺记** | `scripts/check_prose.py` |
| 事件完整性（beats 是否落地） | 无关键遗漏 | agent |
| 忠实度（抽 3 页对照原图） | 无编造 | agent |
| **话级覆盖（源里几话都写了、都出书了）** | **无缺失、无重复** | `scripts/check_coverage.py` |
| 一致性（年龄/建模/死亡/时间线） | 0 error | `scripts/check_consistency.py` |
| **阅读方向已人工确认**（置信度 ≥ 0.6 或 `confirmed: true`） | **已确认** | `scripts/detect_order.py` + `scripts/check_ready.py` |

**没有字数线，没有禁词线。**

> 另两条防"一路绿灯但是空检查"的闸门：`check_prose.py` 会拿
> `page_script.json` 里所有 `speech`/`dialogue` 格和 `outline.quotes` 对账
> （上游漏记一句对白，台词覆盖率再高也发现不了）；`check_consistency.py`
> 在 `bible.md` 为空或 `state` 大面积缺失时直接标 **WARN: 输入不完整，结果不可信**
> 并以非零退出（`--lenient` 才放行），并在正文出现「回忆/往事/当年」等闪回信号
> 而 `state.timeline` 没标时主动提示。

## 封面字体

`assemble.py` 画标题卡时按平台探测中文字体，先到先得：

| 来源 | 路径 |
|---|---|
| `MHN_COVER_FONT` 环境变量 | 用户自定义，**优先级最高** |
| macOS | `/System/Library/Fonts/STHeiti Light.ttc` |
| Linux | `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc` |
| Windows | `C:\Windows\Fonts\msyh.ttc` → `simhei.ttf` |

一个都没找到时**不画字、只出底色封面**（不会崩，但封面没标题）。
非 Windows 平台请设 `MHN_COVER_FONT` 指向一个中文字体：

```bash
MHN_COVER_FONT=/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc \
    python scripts/assemble.py --work work --out build
```

## 常见坑

- **整回版可能是残片**：同回有"整回"和"上/中/下"时按页数选全。
- **合本没书签**：`split_book.py` 会报错并提示写 `chapter-map.csv`。
- **长条页**：高/宽 > 2.6 必须切片，片间留 10–15% 重叠。
- **低清页**：宽 < 1000 px 放大到 1100+ 再识读。
- **跨叙事层误报**：回忆/往事给 `state.timeline = "flashback"`，否则死亡与年龄检查会误判。
- **别用字数判断好坏**：写得短可能是原作就短；写得长可能是把留白填满了。
- **整卷 ≠ 全部话**：有的作品整卷只到话 70，剩下的 71–78 只以单话目录存在。
  先用 `build_chapter_map.py` 登记源里到底有几话，别用"卷数 × 5"去推。
- **S5 半截稿骗过 check_ready**：一话一个 `draft.md` 时，agent 写一半挂掉，磁盘上
  就是半截稿、和完成稿长得一模一样，`check_ready` 只看 mtime 分不出来。写作 agent
  应**逐场写 `draft_seg_NNN.md`，写完一段落一盘**，所有段齐了再
  `python scripts/draft_progress.py --work work --ch ch001 --merge` 拼回 `draft.md`
  （原子写，不会留半截稿）。
- **闸门只查 work 目录会漏**：没建目录的话不会变成 problem，闸门一路全绿。
  必须用 `check_coverage.py --map chapter-map.csv` 拿源当基准对账。
- **路径里带方括号会打瞎 glob**：中文下载目录常见「【完】」「[扫描]」，
  `glob`/`fnmatch` 把方括号当字符类，一条都匹配不到。脚本里用
  `_shared.list_dirs()`（`os.scandir` + 字面前后缀），不要用 `glob`。

## License

MIT

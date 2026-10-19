---
name: manhua-novelizer
description: Turn image-only Chinese comic (manhua) PDFs into literary novel prose. A skill with bundled Python scripts: chapter manifests, page-image extraction (jpg/png, long-strip tiling, one-shot cleanup), per-page vision transcription, chapter outlines with character state, a mandatory narrative-style profile (8 dimensions) built before writing, fidelity-first novelization with no word-count or banned-word rules, automated dialogue-coverage QA, whole-book consistency audit (ageing, character-design drift, death, timeline), and export to md/docx/epub/mobi plus a PNG cover. Use when adapting manga/manhua/comic chapters into a novel, or when extracting scene/character/dialogue data from comic PDFs.
license: MIT
---

# Manhua Novelizer · 漫画转小说

把"只有图、没有文本层"的中文漫画 PDF，先转成可核对的分镜 JSON，再按**原作叙事风格**写成小说正文，
最后做全本一致性审计并导出成书。

## 三条硬规则（其余都服从它们）

1. **情节第一**。原作的事件、因果、信息揭示顺序、人物动机与结局不得改动。字数不是目标，篇幅由事件密度决定。
2. **不设字数上下限、不设禁用词表**。写得长或短、用哪些词，由原作风格决定，不由检查表决定。
3. **先定风格，再动笔**。`work/style.json` 未确认（`confirmed=false`）时，不批量写作。

## 什么时候用 / 不用

**用**：漫画转小说；漫画场景/人物/台词结构化；几百话批量处理；完本查设定与情节矛盾。
**不用**：PDF 有文本层（`pdftotext` 更快）；只要摘要；只要翻译。

## 安装与运行

```bash
pip install pymupdf pillow          # 必需；docx 导出另需 python-docx
python scripts/build_manifest.py --help
```

**形态**：这是一个 skill——`SKILL.md` + `prompts/` + `references/` + `scripts/`。
脚本负责确定性的工作（拆页、质检、审计、成书、清理），写作由 agent 读提示词执行；不需要安装成包，也不需要 API。

## 流程

| 阶段 | 做什么 | 命令 / 执行者 | 产物 |
|---|---|---|---|
| S0 | 建清单：解析文件名、上/中/下去重、剔非正文 | `python scripts/build_manifest.py --dir pdf` | `manifest.csv` |
| S0b | 合本拆章：按书签或页表切分 | `python scripts/split_book.py --pdf book.pdf --out chapters` | `chNNN_*.pdf` |
| S1 | 拆页：原生图抽取、长条切片、低清放大、jpg/png；也支持图片目录与**双页扫描拆分** | `python scripts/prep_pages.py --pdf x.pdf --out ch001/pages`<br>`python scripts/prep_pages.py --images 卷目录 --out ch001/pages --split-spread --direction rtl` | `pages/p0001.jpg` |
| S1.5 | **阅读顺序**：左起 / 右起 / 条漫，可人工覆盖 | `python scripts/detect_order.py --pages ch001/pages` | 写入 `config.json` |
| **S-1** | **叙事风格配置**（八维度，需用户确认） | agent + `prompts/00-style-analysis.md` | `style.json` `style.md` |
| **S-0** | **全书脊柱**：低清通读全本，写主线/人物弧/时间线/母题/节奏表 | agent + `prompts/00b-spine.md` | `spine.md` |
| S2 | 圣经：人物/势力/术法/地名/方言 | agent + `prompts/05-bible.md` | `bible.md` |
| S2.5 | 联网考据 | agent + `prompts/07-web-research.md` | `refs.md` |
| S3 | 页脚本：逐页识读成 JSON（**必经，不抽样**） | 视觉 agent + `prompts/01-page-script.md` | `page_script.json` |
| S3-alt | **廉价转录**：本地 OCR 出文字，文本模型整理（零视觉 token） | `python scripts/ocr_pages.py` + `prompts/01b-page-script-from-ocr.md` | `ocr.json` → `page_script.json` |
| S4 | 章脉络：合页成场、裁说话人、写 state；**只做索引，不产出句子** | agent + `prompts/02-chapter-outline.md` | `outline.json` |
| S5 | 写正文：**逐场打开页脚本写**，读 style.md | agent + `prompts/03-prose.md` | `draft.md` |
| S6 | 质检：台词覆盖 + 事件完整性 + **沉浸检查** + 抽象句比例 | `python scripts/check_prose.py` + agent + `prompts/04-qa.md` | `qa.json` |
| S6.5 | 全本一致性审计（年龄/建模/死亡/时间线/称谓），对照 spine | `python scripts/check_consistency.py` + `prompts/06-consistency-audit.md` | `audit/consistency.md` |
| **S6.9** | **成书闸门**：所有话写完且静置 N 分钟、质检未过期 | `python scripts/check_ready.py --work . --check-qa` | 退出码 0 才继续 |
| S7 | 统一引号 → 成书：md/docx/epub/mobi + PNG 封面 | `python scripts/normalize_quotes.py` → `python scripts/assemble.py` | `book.*` |
| S8 | 清理中间页图 | `python scripts/clean_pages.py --work .` | 释放磁盘 |

> **S6.9 不可跳过。** 并行写多话时，写作 agent 的收尾写入会和成书抢同一个文件——
> 实测出现过 4 次"成书后又被改写"，每次都靠人工比对 mtime 才发现。
> `check_ready.py` 把这个判断变成一条命令：缺文件、还在改、质检过期，任一命中就拒绝成书。

**全局层与局部层是并列的，不能互相替代**：`spine.md` 管"全书不矛盾"，
`page_script.json` 管"每一页都在场"，章节 1:1 管"完整还原"。详见 `references/global-local.md`。

细节见 `references/pipeline.md`；改编原则见 `references/principles.md`；风格配置见 `references/style-config.md`；
**省钱方案（OCR / 本地模型 / 分级）见 `references/cheap-vision.md`**。

## 叙事风格配置（前置任务，必做）

改编前先回答：**这部作品怎么讲故事？** 八个维度：叙事节奏、情绪表达、对白特征、画面转译、
信息揭示、描写密度、特有表达习惯、禁止破坏的特征。每条都要给原作依据，资料不足标"尚未确认"。

```bash
python scripts/style_config.py --action check      # 查看还有哪些维度没填
python scripts/style_config.py --action render     # 生成 style.md 给写作 agent 读
python scripts/style_config.py --action confirm    # 用户确认后标记
```

配置是**判断依据，不是套版**：整体偏慢的作品，战斗场仍应快；常用留白的作品，不是每场都留白。

## 视觉转译要点

- 动作 → 时间顺序与因果；不逐格描述姿势。
- 表情 → 用原作的动作、视线、停顿承载；画面已表达的不再补同义心理。
- 构图 → 只转对理解有用的空间关系（谁挡住出口、谁在高处）。
- 镜头 → 转成**信息顺序**，正文不写"镜头拉近"。
- 无对白格 → 先判断功能（衔接/停顿/悬念/意象），再决定写不写。
- 画面外信息 → 不得写成确定事实。

## 输出与清理

- 成书格式：`md` / `docx` / `epub` / `mobi`（MOBI 由内置写出器生成，不依赖 calibre）+ `cover.png`。
- 页图支持 `jpg`（默认）与 `png`：`python scripts/prep_pages.py --format png`。
- **中间页图会占几百 MB 到几 GB**：`python scripts/assemble.py --cleanup` 或 `python scripts/clean_pages.py --work .` 一键删除；
  `--keep ch001/pages` 可保留某一话，`--dry-run` 先看会删多少。

## 质量闸门

| 检查 | 合格线 | 谁做 |
|---|---|---|
| 台词覆盖（原文对白逐字落地） | ≥ 95% | `python scripts/check_prose.py` |
| 事件完整性（beats 是否落地） | 无关键遗漏 | agent |
| 忠实度（抽 3 页对照原图） | 无编造 | agent |
| 一致性（年龄/建模/死亡/时间线） | 0 error | `python scripts/check_consistency.py` |

**没有字数线，没有禁词线。**

## 目录约定

```
<work>/
├─ pdf/ 或 book.pdf
├─ chapters/                 S0b 产物
├─ manifest.csv
├─ style.json  style.md  style_history/    S-1
├─ bible.md  glossary.csv                  S2
├─ refs.md   claims.csv                    S2.5
├─ config.json
├─ audit/consistency.md                    S6.5
├─ build/                    S7（book.md/docx/epub/mobi, cover.png）
└─ ch001/
   ├─ pages/                S1（用完可删）
   ├─ page_script.json       S3
   ├─ outline.json           S4（含 state）
   ├─ draft.md               S5
   └─ qa.json                S6
```

## 常见坑

- **整回版可能是残片**：同回有"整回"和"上/中/下"时按页数选全。
- **合本没书签**：`scripts/split_book.py` 会报错并提示写 `chapter-map.csv`。
- **长条页**：高/宽 > 2.6 必须切片，片间留 10–15% 重叠。
- **低清页**：宽 < 1000 px 放大到 1100+ 再识读。
- **同名不同世**：跨时代角色用 `名(时代)` 作主键。
- **跨叙事层误报**：回忆/往事要给 `state.timeline = "flashback"`，否则死亡与年龄检查会误判。
- **别用字数判断好坏**：写得短可能是原作就短；写得长可能是把留白填满了。

---
name: manhua-novelizer
description: Convert image-only Chinese comic (manhua) PDFs into structured panel scripts and then literary Chinese prose. Handles single-chapter PDFs and multi-chapter "book" PDFs, chapter manifests, page-image extraction with long-strip tiling, per-page vision transcription to JSON, chapter outlines with character state, novelization, automated QA (dialogue coverage, banned words, length, names), web fact-checking, and a whole-book consistency audit (ageing, character-design drift, death reappearing, timeline conflicts). Use when adapting manga/manhua/comic chapters into a novel, or when extracting scene/character/dialogue data from comic PDFs.
license: MIT
---

# Manhua Novelizer · 漫画小说化

把"只有图、没有文本层"的中文漫画 PDF，变成**可核对的分镜 JSON**，再写成**小说正文**，最后做
**全本一致性审计**。

适用于：单话 PDF、图片集、以及**一册装几十话的合本/完本 PDF**。目标是一话一话地小说化，而不是摘要。

## 何时用 / 何时不用

**用**：漫画转小说；漫画场景/人物/台词结构化；几百话批量处理；完本查设定与人物逻辑矛盾。

**不用**：PDF 有文本层（`pdftotext` 更快）；只要剧情摘要；只要翻译（不是改写）。

## 六条铁律

1. **纯图 PDF 没有文本层**。先 `page.get_text()` 探一下，全空就是纯图，别调 `pdftotext`。
2. **转录与写作分两步**。绝不让模型"看着图直接写小说"——必然编造、漏台词、无法定位错误。
3. **台词逐字**。方言字、语气词、错别字原样保留，不改写、不翻译、不"润色"。
4. **不编造**。原图没有的人物、能力、前情不写；不确定标 `uncertain`。
5. **正文禁分镜词**：画面、镜头、分镜、这一格、格子、读者、对话框、旁白框。
6. **每话必写 `state`**。年龄、外观、生死、位置是跨话审计的唯一依据，省了就查不出矛盾。

## 流程

| 阶段 | 做什么 | 谁做 | 产物 |
|---|---|---|---|
| S0 | 建清单：解析文件名、上/中/下去重、剔非正文 | `scripts/build_manifest.py` | `manifest.csv` |
| S0b | **合本 PDF 拆章**：按书签或手写页表切分 | `scripts/split_book.py` | `chNNN_标题.pdf` + `chapter-index.csv` |
| S1 | 拆页：原生 JPEG、长条切片、低清放大、页段截取 | `scripts/prep_pages.py` | `pages/p0001.jpg` |
| S2 | 圣经：人物/势力/术法/地名/方言 | agent（`prompts/05-bible.md`） | `bible.md` `glossary.csv` |
| S2.5 | **联网考据**：核准人物、时间线、术语 | agent（`prompts/07-web-research.md`） | `refs.md` `claims.csv` |
| S3 | 页脚本：逐页识读成 JSON | 视觉 agent（`prompts/01-page-script.md`） | `page_script/pNNNN.json` |
| S4 | 章脉络：合页成场、裁说话人、抽台词、写 `state` | agent（`prompts/02-chapter-outline.md`） | `outline.json` |
| S5 | 写正文 | agent（`prompts/03-prose.md`） | `draft.md` |
| S6 | 单话质检 | `scripts/check_prose.py` + agent（`prompts/04-qa.md`） | `qa.json` |
| S6.5 | **全本一致性审计**：年龄/建模/死亡/时间线 | `scripts/check_consistency.py` + agent（`prompts/06-consistency-audit.md`） | `audit/consistency.md` |
| S7 | 汇编：目录、合本、docx、统计 | `scripts/assemble.py` | `book.md` / `book.docx` |

细节见 `references/pipeline.md`；字段见 `references/schemas.md`；文风见 `references/style-guide.md`；
设计依据见 `references/research.md`。

## 快速开始

```bash
# A) 单话 PDF 目录
python scripts/build_manifest.py --dir pdf --out manifest.csv
python scripts/prep_pages.py --pdf "pdf/001：第一话 上.pdf" --out ch001/pages

# B) 一册装几十话的合本 PDF
python scripts/split_book.py --pdf book.pdf --out chapters --dry-run   # 先确认边界
python scripts/split_book.py --pdf book.pdf --out chapters
python scripts/build_manifest.py --dir chapters --out manifest.csv

# B2) 合本没书签：手写 chapter-map.csv（chapter,title,start,end），再 --map chapter-map.csv

# C) 只处理合本里的一段，不拆文件
python scripts/prep_pages.py --pdf book.pdf --out ch042/pages --first-page 120 --last-page 168
```

之后 S2–S6 由 agent 按 `prompts/` 执行，一话一个 agent。全部写完再跑：

```bash
python scripts/check_prose.py --draft ch001/draft.md --outline ch001/outline.json \
       --bible bible.md --pages 29 --out ch001/qa.json
python scripts/check_consistency.py --work . --bible bible.md \
       --out audit/consistency.md --json audit/consistency.json
python scripts/assemble.py --work . --out book --title "书名"
```

## 配置

`<work>/config.json`：

```json
{
  "language": "zh",
  "pov": "third-limited",
  "tense": "past",
  "length_per_page": [120, 180],
  "dialect": "keep",
  "banned_words": ["画面", "镜头", "分镜", "这一格", "格子", "读者", "对话框", "旁白框"],
  "output": ["md", "docx"],
  "title_format": "第X回 {title}",
  "scene_break": "◇",
  "reading_direction": "ltr"
}
```

- `dialect`: `keep`（推荐）/ `light` / `none`。
- `pov`: `third-limited` / `third-omniscient` / `first`。
- `length_per_page`: 一话字数 = 页数 × 区间。

## 目录约定

```
<work>/
├─ pdf/  或  book.pdf
├─ chapters/                S0b 拆出的单话 PDF
├─ manifest.csv
├─ bible.md  glossary.csv    S2
├─ refs.md   claims.csv      S2.5
├─ config.json
├─ audit/consistency.md      S6.5
├─ progress.csv
└─ ch001/
   ├─ pages/                S1
   ├─ page_script/           S3
   ├─ outline.json           S4（含 state）
   ├─ draft.md               S5
   └─ qa.json                S6
```

## 验收线

- 台词覆盖 ≥ 95%（`check_prose.py`）
- 禁词 0 次
- 字数 ∈ 页数 × `length_per_page`
- 命名 100% 在 `bible.md` 白名单内
- 一致性：`check_consistency.py` 无 `error`；`warn` 逐条有结论（改文/补圣经/标合理）

## 一致性审计怎么用

`state` 是审计的燃料。S4 每话写：

```json
"state": {"year": 3, "flashback": false,
          "cast": {"阿禾": {"age": 14, "status": "alive", "look": "束发，旧棉袍", "place": "山道"}}}
```

脚本查得出来的：时间倒流、年龄倒退或不随时长增长、死人复活、外观与圣经差异过大、未入册人名。
脚本查不出来的：换装是否合理、术法是否凭空出现、称谓是否前后一致——交给 agent 按
`prompts/06-consistency-audit.md` 判，每条必须给页码证据。

## 常见坑

- **整回版可能是残片**：同一回有"整回"和"上/中/下"时按页数选全，别默认选整回。
- **合本没书签**：`split_book.py` 会直接报错并提示写 `chapter-map.csv`，不要硬按固定页数切。
- **长条页**：高/宽 > 2.6 必须切片，片间留 10–15% 重叠，否则台词断在半句。
- **低清页**：宽 < 1000 px 放大到 1100+ 再识读。
- **水印**：平台水印记 `sign` 类忽略，不写进正文。
- **同名不同世**：跨时代角色用 `名(时代)` 作主键，否则圣经会合并成一个人。
- **说话人**：气泡尾巴判断不了填 `unknown`，交 S4 用上下文裁决，S3 别硬猜。
- **年龄别猜**：`state.age` 不确定就省略；错一个年龄，整条审计线全歪。

## 联网检索

S2.5 用公开资料核准设定，**每条都要 URL**，可信度分 `official` / `wiki` / `fan`。
优先级：原图 > 官方 > 百科 > 粉丝贴。找不到写"未找到"，不编。
refs 里的后文剧透只用于校验，不要提前写进当前话。

## 成本

每页 ≈ 1.5k 视觉 token。1000 页 ≈ 150 万 token 识读；写作与审计另计。
规模大时：**页级缓存**（产物存在即跳过）+ **按话并行**（4–8 路）。

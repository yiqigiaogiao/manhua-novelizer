---
name: manhua-novelizer
description: Convert image-only Chinese comic (manhua) PDFs into structured panel scripts and then literary Chinese prose. Handles chapter manifests, page-image extraction with long-strip tiling, per-page vision transcription to JSON, chapter outlines, novelization, and automated QA (dialogue coverage, banned words, length, names). Use when adapting manga/manhua/comic chapters into a novel, or when extracting scene/character/dialogue data from comic PDFs.
license: MIT
---

# Manhua Novelizer · 漫画小说化

把"只有图、没有文本层"的中文漫画 PDF，变成**可核对的分镜 JSON**，再写成**小说正文**。

适用于：国漫/日漫/条漫的 PDF 或图片集；目标是"每一话的小说化改写"，而不是摘要。

## 何时用 / 何时不用

**用**：用户要把漫画转成小说、要漫画的场景/人物/台词结构化数据、要批量处理几百话。

**不用**：PDF 本身有文本层（直接 `pdftotext` 更快）；只要剧情摘要（用 summarize 类流程即可）；只要翻译（不要改写）。

## 五条铁律

1. **纯图 PDF 没有文本层**。先探测：`page.get_text()` 全空就是纯图。不要浪费时间调 `pdftotext`/`pypdf`。
2. **转录与写作必须分两步**。绝不能让模型"看着图直接写小说"——必然编造、必然漏台词、出错无法定位。
3. **台词逐字转录**。方言字、语气词、错别字原样保留，不改写、不翻译、不"润色"。
4. **不编造**。原图没有的人物、能力、前情一律不写；不确定就标 `uncertain`。
5. **正文禁止分镜术语**：画面、镜头、分镜、这一格、格子、读者、对话框、旁白框。

## 流程

| 阶段 | 做什么 | 谁做 | 产物 |
|---|---|---|---|
| S0 | 建清单：解析文件名、识别上/中/下、去重、剔非正文 | `scripts/build_manifest.py` | `manifest.csv` |
| S1 | 拆页：抽原生 JPEG、长条页切片、低清放大 | `scripts/prep_pages.py` | `pages/p0001.jpg` |
| S2 | 建圣经：人物/势力/术法/地名/方言词表 | agent（`prompts/05-bible.md`） | `bible.md` `glossary.csv` |
| S3 | 页脚本：逐页识读成 JSON | 视觉 agent（`prompts/01-page-script.md`） | `page_script/pNNNN.json` |
| S4 | 章脉络：合页成场、裁决说话人、抽台词/伏笔 | agent（`prompts/02-chapter-outline.md`） | `outline.json` |
| S5 | 写正文：小说化 | agent（`prompts/03-prose.md`） | `draft.md` |
| S6 | 质检：台词覆盖/禁词/长度/命名 + 抽页复核 | `scripts/check_prose.py` + agent（`prompts/04-qa.md`） | `qa.json` |
| S7 | 汇编：目录、合本、docx | `scripts/assemble.py` | `book.md` / `book.docx` |

细节见 `references/pipeline.md`；JSON 字段见 `references/schemas.md`；文风与禁词见 `references/style-guide.md`。

## 快速开始

```bash
# 0) 放进工作目录：<work>/pdf/*.pdf
python scripts/build_manifest.py --dir pdf --out work/manifest.csv

# 1) 逐文件拆页（并行跑，一个 PDF 一个进程）
python scripts/prep_pages.py --pdf "pdf/001：第一话 上.pdf" --out work/ch001/pages

# 2) 之后 S2–S6 由 agent 按 prompts/ 执行，每话一个 agent
# 3) 质检与汇编
python scripts/check_prose.py --draft work/ch001/draft.md --outline work/ch001/outline.json \
       --bible work/bible.md --pages 29 --out work/ch001/qa.json
python scripts/assemble.py --work work --out book
```

## 配置

在 `<work>/config.json` 里定改编参数（脚本与提示词都会读）：

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
  "scene_break": "◇"
}
```

- `dialect`: `keep`（台词全保留，推荐）/ `light`（只留语气词）/ `none`（全部普通话化）。
- `pov`: `third-limited` / `third-omniscient` / `first`.
- `length_per_page`: 决定一话字数 = 页数 × 区间。

## 目录约定

```
<work>/
├─ pdf/                     原始 PDF
├─ manifest.csv             S0 产物
├─ bible.md  glossary.csv   S2 产物（只增不改）
├─ config.json
└─ ch001/
   ├─ pages/p0001.jpg        S1 产物
   ├─ page_script/p0001.json S3 产物
   ├─ outline.json           S4
   ├─ draft.md               S5
   └─ qa.json                S6
```

## 验收线

- 台词覆盖 ≥ 95%（`check_prose.py` 自动算）
- 禁词 0 次
- 忠实度：抽 3 页原图对照，无编造（agent 复核）
- 字数 ∈ 页数 × `length_per_page`
- 命名 100% 在 `bible.md` 白名单内

## 常见坑

- **整回版可能是残片**：同一回同时有"整回"和"上/中/下"时，按页数选全的那套，别默认选整回。
- **长条页**：高/宽 > 2.6 必须切片，切片间留 10–15% 重叠，否则台词会断在半句。
- **低清页**：宽 < 1000 px 放大到 1100+ 再识读，否则小字必糊。
- **水印**：平台水印记 `sign` 类忽略，不要写进正文。
- **同名不同世**：跨时代角色用 `名(时代)` 作主键，否则圣经会合并成一个人。
- **说话人**：气泡尾巴判断不了就填 `unknown`，交给 S4 用上下文裁决，S3 不要硬猜。

## 成本

每页 ≈ 1.5k 视觉 token。1000 页 ≈ 150 万 token 识读；写作另计。几百话的规模必须做**页级缓存**（S3 产物存在就跳过）与**按话并行**（4–8 路）。

参考来源与设计依据见 `references/research.md`。

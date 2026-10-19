# 流水线规范（S0–S7）

> 每个阶段都必须**落盘**。下游只读上游的产物，不读上游的对话。

---

## S0 · 建清单

**输入**：一个装满 PDF 的目录。
**输出**：`manifest.csv`。

```bash
python scripts/build_manifest.py --dir pdf --out manifest.csv
```

做什么：

1. 按文件名解析①序号 ②第X回/话 ③上/中/下 ④标题。
2. 分类：`正篇` / `番外`（X.5 回）/ `非正文`（公告、请假、通知、预告、目录页、季终小结）。
3. 同一回存在多个文件时，**按总页数选全的那套**：
   - 整回 26 页 vs 上 28 + 下 29 页 → 选分卷（整回是残片）。
   - 整回 39 页 vs 上 41 + 中 28 + 下 31 页 → 选分卷。
   - 只有整回 → 选整回。
4. 记录每页的原始像素宽高、页数、体积、页高宽比（标记长条页）。

产物列：`seq, chapter, half, part, subtitle, kind, pages, mb, px, tall, canonical, dup_group, dup_note, file`。

**卡点**：若 `canonical` 全是 `N` 或某回页数明显异常（如"下"只有 1 页），停下来人工确认缺页。

---

## S1 · 拆页

**输入**：单个 PDF。
**输出**：`pages/p0001.jpg`，长条页为 `p0001_t1.jpg`…，外加 `pages.json`。

```bash
python scripts/prep_pages.py --pdf "pdf/001.pdf" --out ch001/pages [--min-width 1100]
```

规则：

1. **优先抽内嵌 JPEG**（`doc.extract_image`），零重编码，保住文字锐度；抽不到才按 200 DPI 渲染。
2. 每页只有一张图时直接抽；一页多图或矢量页 → 渲染。
3. 宽 < `--min-width`（默认 1100）用 Lanczos 放大。低清页放大后仍可读，但模糊字要进 `uncertain`。
4. 高/宽 > `--tile-ratio`（默认 2.6）视为长条页：按 1.55:1 切横带，相邻带重叠 12%。
5. 命名必须稳定：页码 4 位补零，`p0007.jpg` / `p0007_t3.jpg`。

**为什么要切片**：视觉模型会把整图缩到长边约 1500 px，一张 900×14000 的长条缩完每格只剩几十像素，字全糊。切片后每片接近 1:1.5，字才够大。

---

## S2 · 系列圣经

**输入**：前 3–6 话的页脚本（或页图）。
**输出**：`bible.md`、`glossary.csv`。**只增不改**。

必填字段（没依据就留空，不要编）：

- 人物：`名`、`别名`、`身份`、`外貌`、`首次出场`、`状态`
- 势力/门派、术法/器物、地名、时间线、方言词表

要点：

1. 别名合并到主名；正文统一用主名。
2. 跨时代/分身角色用 `名(时代)` 作主键。
3. 每条尽量带首次出场话号；查不到写 `待核实`。
4. 每 10 话增量更新一次，冲突条目加删除线并注明"第 X 话修正"。

提示词：`prompts/05-bible.md`。

---

## S3 · 页脚本（核心）

**输入**：一页图（或一片）。
**输出**：`page_script/pNNNN.json`，每页一个文件。

```json
{
  "chapter": 1, "part": "上", "page": 12,
  "layout": "3格：整宽 / 左右分栏 / 整宽",
  "panels": [{
    "id": "p12-1", "order": 1,
    "bbox": [0.03, 0.02, 0.97, 0.31],
    "shot": "中景", "angle": "平视",
    "scene": "正殿（室内·白日）",
    "characters": [{"name": "陈松", "face": "正面", "expression": "得意", "action": "举起令牌"}],
    "visual": "老道士指间夹着残缺的黑色令牌，身后弟子只剩剪影",
    "text": [{"type": "speech", "speaker": "陈松", "text": "只有咱们这一门噻！", "confidence": 0.95}],
    "notes": "令牌有螺旋纹，缺一角"
  }],
  "page_summary": "陈松向弟子展示镇派令牌",
  "uncertain": []
}
```

铁律：

1. **阅读顺序**：中文漫画先上后下、同行先左后右（老式港漫右起需另配 `rtl`）。
2. **逐字转录**：方言、语气词、错别字原样保留。
3. **气泡归属**看尾巴；判断不了填 `unknown`，不要猜。
4. `type` 五类：`speech` / `thought` / `narration` / `sfx` / `sign`（招牌、字幕、印章、水印）。
5. 看不清用 `?` 占位，进 `uncertain`。
6. **本阶段禁止润色**，只记录客观内容。

成本控制：

- 每页约 1.5k 视觉 token；4 页一批比 1 页一批省 30% 上下文开销。
- 产物存在即跳过——这是唯一可靠的省钱手段。
- 失败（JSON 解析不了）把报错回灌重试 ≤2 次，然后写 `needs_human` 继续。

提示词：`prompts/01-page-script.md`。

---

## S4 · 章脉络

**输入**：一话全部 `page_script/*.json`。
**输出**：`outline.json`。

做四件事：

1. 合并同场景连续页为 `scenes`（地点/时间/视角不变就算同场）。
2. `beats` 写**因果**，不写流水账：不是"他抬手/他说话/他放下"，而是"他用令牌压服质疑的弟子"。每场 3–6 条。
3. **裁决 `unknown`** 说话人：结合称呼、语气、上下文；仍不能定就保留并列进 `uncertain`。
4. 抽 `quotes`（关键台词，5–20 条，逐字保留）供 S6 对账；标 `threads`（新埋伏笔/推进旧线/收线）。

还必须写 `continuity`：一句话说明"接上话哪里、人物在哪、身上什么状态"，供 S5 衔接、S6 校验。

提示词：`prompts/02-chapter-outline.md`。

---

## S5 · 写正文

**输入**：`outline.json` + `bible.md` + 上一话结尾 500 字（只用于衔接）。
**输出**：`draft.md`（带 front matter）。

- 字数目标 = 页数 × `config.length_per_page`。
- 文风、禁词、分段规则见 `references/style-guide.md`。
- **只吃 outline，不回看原图**。看原图写作 = 重蹈"直接看图写"的覆辙。

提示词：`prompts/03-prose.md`。

---

## S6 · 质检

**输入**：`draft.md`、`outline.json`、`bible.md`、页图（抽 3 页）。
**输出**：`qa.json`。

```bash
python scripts/check_prose.py --draft ch001/draft.md --outline ch001/outline.json \
       --bible bible.md --pages 29 --out ch001/qa.json
```

脚本自动做的四项：

| 检查 | 算法 | 合格线 |
|---|---|---|
| 台词覆盖 | 每条 quote 与正文做模糊匹配（difflib，忽略标点） | ≥ 0.95 |
| 禁词 | 正则匹配 `config.banned_words` | 0 次 |
| 长度 | 中文字符计数的区间判断 | 页数×[100,220] |
| 命名 | 从"X说/X道/X问"抽候选名，比对 `bible.md` 白名单 | 无未知名 |

agent 做的两项：

5. **忠实度**：抽首场、高潮、结尾三页原图，只问三件事——有没有原图没有的情节/人物/能力？有没有把旁白当台词？有没有张冠李戴？有则列出并改写。
6. **连续性**：与上一话 `continuity` 对照（位置、伤势、时间、称呼）。

修补原则：**只改出问题的段落**，不整话重写；补台词时宁可加"他说"，也不删原句；忠实度问题优先于文采。

提示词：`prompts/04-qa.md`。

---

## S7 · 汇编

```bash
python scripts/assemble.py --work . --out book
```

- 读所有 `ch*/draft.md` 的 front matter，按话号排序。
- 生成 `book/book.md`（含目录）、`book/book.docx`（若装了 python-docx）、`book/stats.csv`。
- front matter 里的 `场景`/`人物` 汇总成 `book/index.csv`，就是你要的"每话场景与人物表"。

---

## 并行与断点

- **一话一个 agent**，话与话互不依赖（圣经只读）。
- 4–8 路并发；再高容易触发限流，且不好排查。
- 断点判据：产物文件存在即完成。重跑先 `if exists: skip`。
- `progress.csv` 记 `chapter,stage,status,updated`，中断后从缺口继续。

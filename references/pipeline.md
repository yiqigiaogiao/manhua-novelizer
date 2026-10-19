# 流水线规范（S-1 – S8）

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

## S0b · 合本 PDF 拆章

一册装几十话、或"完本"PDF 时，先拆章，再进 S0/S1：

```bash
python scripts/split_book.py --pdf book.pdf --out chapters --dry-run   # 先看边界
python scripts/split_book.py --pdf book.pdf --out chapters             # 真拆
```

- **有书签**：按 `--toc-regex` 取边界，默认匹配 `第X回/话`、`番外`、`序章`、`终章`。
- **无书签**：自己写 `chapter-map.csv`（`chapter,title,start,end`），加 `--map chapter-map.csv`。
- 输出 `chNNN_标题.pdf` + `chapter-index.csv`，并报告**未被覆盖的页**（封面、广告、目录页）。
- 切完直接 `python scripts/build_manifest.py --dir chapters`，下游完全不用改。

`insert_pdf` 复制原始图像对象，不二次压缩；但会丢掉原书签，`chapter-index.csv` 就是新目录。

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
6. 只想处理合本里的一段：`--first-page 120 --last-page 180`（1 起、含端点）。输出沿用**原书页号**（`p0120.jpg`），便于回溯。
7. **图片目录**：`--images 目录` 直接读 jpg/png/webp，按文件名自然排序后同样放大、切片、编号。
8. **双页扫描**：`--split-spread` 把宽高比 > 1.15 的图拆成左右两半；`--direction rtl` 时右半先读（日漫台版常见），`ltr` 时左半先读。
   拆完再跑 `detect_order.py`，方向判定会准得多——整张跨页直接检测很容易误判为 ltr。

**为什么要切片**：视觉模型会把整图缩到长边约 1500 px，一张 900×14000 的长条缩完每格只剩几十像素，字全糊。切片后每片接近 1:1.5，字才够大。

---

## S1.5 · 阅读顺序（拆页之后、转录之前）

顺序错了，台词归属和动作因果都会错位。

```bash
python scripts/detect_order.py --pages work/ch001/pages --work work     # 检测并建议
python scripts/detect_order.py --set rtl --work work                    # 人工覆盖（ltr / rtl / ttb）
```

判据（给出方向 + 置信度 + 依据，不黑盒）：

- 竖排文字气泡多 → 倾向 `rtl`（日式漫画）
- 横排文字气泡多 → 倾向 `ltr`
- 页面高/宽 > 2.6 → `ttb`（纵向条漫）
- 上半页气泡整体偏右 → 倾向 `rtl`

置信度 < 0.6 时不要直接采信；人工确认流程见 `prompts/08-reading-order.md`。
结果写入 `config.json` 的 `work.reading_direction`，S3 转录按它排 `order`。

**跨页扫描必须在检测前拆开**。实测一本日漫台版：整张跨页送检得到 `ltr 0.51`（错），
用 `--split-spread --direction rtl` 拆成 182 个半页后再检测得到 `rtl 0.68`（对）。
拆页顺序与检测结论要一致，否则 S3 会把整页台词归属排反。

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

## S-1 · 叙事风格配置（前置任务，必做）

在正式改编前先回答：**这部作品怎么讲故事？**

提示词：`prompts/00-style-analysis.md`；规范：`references/style-config.md`。

- 输入：开篇 3–5 话的页图/页脚本、`bible.md`、用户提供的资料。
- 输出：`work/style.json`（八维度：节奏、情绪、对白、画面转译、信息揭示、描写密度、特有习惯、禁止破坏）+ `style.md`。
- 每条结论必须给原作依据；资料不足标 `尚未确认`，不凭空假设。
- 用户确认（`python scripts/style_config.py --action confirm`）之前，不批量写作。
- 修改后自动快照到 `style_history/`，写作一律读新版。

配置是判断依据，不是套版：整体偏慢的作品，战斗场仍应快；常用留白的作品，不是每场都留白。

---

## S2.5 · 联网考据

动笔前用公开资料核准设定，减少"看图猜设定"的错误。

提示词：`prompts/07-web-research.md`。产物：

- `refs.md`：作品信息、人物表、时间线、设定名词，每条带 URL 与可信度。
- `claims.csv`：`claim,subject,value,source,confidence,note`。

优先级：**原图 > 官方 > 百科 > 粉丝贴**。冲突写进 `refs.md` 的"争议"节，正文不要写死。

用途有两个：S3/S5 判断人物身份与术语；S6.5 提供"外部事实"做交叉验证。

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

还必须写 `state`：`year`（故事内年份序号）、`flashback`、`cast.<名>.{age,status,look,place}`。
这是 S6.5 全本审计的唯一输入——没有它，年龄与"建模"变化根本查不出来。

提示词：`prompts/02-chapter-outline.md`。

---

## S5 · 写正文

**输入**：`outline.json` + `style.md` + `bible.md` + 上一话结尾 300 字（只用于衔接）。
**输出**：`draft.md`（带 front matter）。

- **不设字数目标**。篇幅由这一话的事件密度与节奏决定，不由页数决定。
- **不设禁用词表**。用词服务于原作风格；只保留"正文不写分镜说明语言"这一条原则。
- 先判断每个场景的功能（推进／停顿／反转／铺垫／收束），再决定写多写少。
- 对白逐字保留语义、语气、停顿、口癖、方言；短句不扩写。
- **只吃 outline 与 style，不回看原图**。看原图写作 = 重蹈"直接看图写"的覆辙。

提示词：`prompts/03-prose.md`。

---

## S6 · 质检（只看忠实）

**输入**：`draft.md`、`outline.json`、`bible.md`、页图（抽 3 页）。
**输出**：`qa.json`。

```bash
python scripts/check_prose.py --draft ch001/draft.md --outline ch001/outline.json --bible bible.md --out ch001/qa.json
```

脚本自动做的两项：

| 检查 | 算法 | 合格线 |
|---|---|---|
| 台词覆盖 | 每条 quote 与正文做模糊匹配（difflib，忽略标点） | ≥ 0.95 |
| 命名提示 | 从"X说/X道/X问"抽候选名，比对 `bible.md` | 仅提示，不判失败 |

**不查字数，不查禁词。**

agent 做的四项：

1. **事件完整性**：`outline.scenes[].beats` 是否逐条落地（合并可以，漏关键因果不行）。
2. **忠实度**：抽首场、高潮、结尾三页原图，问——有没有原图没有的情节/人物/能力？有没有把旁白当台词？有没有张冠李戴？有没有把没说出口的话写成说出口？
3. **声音一致性**：口癖、句长、称呼、方言是否与前一话一致。
4. **风格执行**：对照 `style.md` 逐场判断，不机械套用。

修补原则：**只改出问题的段落**，不整话重写；补台词时宁可加"他说"，也不删原句；忠实度问题优先于文采。

提示词：`prompts/04-qa.md`。

---

## S6.5 · 全本一致性审计

单话质检查不出"跨话矛盾"，这一步专治：

```bash
python scripts/check_consistency.py --work . --bible bible.md \
       --out audit/consistency.md --json audit/consistency.json
```

机器查五类：

| 类型 | 判据 | 级别 |
|---|---|---|
| `time` | `year` 倒退且没标 `flashback` | warn |
| `ageing` | 时间前进 N 年，年龄不涨/倒退 | error / warn |
| `death` | 已标 `dead` 的角色在后话又活着出现 | error |
| `look` | 本话外观与 bible 基准差异过大，或前后话突变 | warn / info |
| `names` | 出场人物不在 bible | warn |

agent 再按 `prompts/06-consistency-audit.md` 做六类语义判定：**年龄/成长、外貌/建模、死亡/退场、
时间线、称谓/关系、能力/设定**。它负责机器判不了的部分——比如"换了皮甲"是剧情合理还是画错。

处置：`error` 必修；`warn` 逐条判定（改正文 / 补 bible / 标合理变化）；`info` 记入 bible。

---

## S6.9 · 成书闸门

并行写多话时，写作 agent 的收尾写入会和成书抢同一个文件。**成书前必须过这道闸门**：

```bash
python scripts/check_ready.py --work . --check-qa
# 退出码 0 才允许进入 S7
```

判据（任一不满足就拒绝）：

1. 每一话都有 `draft.md`；
2. `draft.md` 最后修改距今 ≥ `--quiet-minutes`（默认 10）——还在写就别急着拼；
3. `--check-qa` 时 `qa.json` 存在且不早于 `draft.md`——防止用旧质检结果。

`--require` 可以追加必备文件，例如 `--require draft.md outline.json page_script.json`。

## S7 · 成书与清理

开口前先统一引号（台版/日式原稿常用「」，正文要求“”）：

```bash
python scripts/normalize_quotes.py --work . --check   # 先看有多少
python scripts/normalize_quotes.py --work .           # 改「」→“”、『』→‘’
```

```bash
python scripts/assemble.py --work . --out build --title "书名" --cleanup
```

- 读所有 `ch*/draft.md` 的 front matter，按话号排序。
- 导出 `build/book.md`、`book.docx`（需 python-docx）、`book.epub`、`book.mobi`（内置写出器，不依赖 calibre）。
- 生成 `cover.png`（优先用第一话首页，没有页图时画标题卡）。
- `stats.csv`：每话字数；`index.csv`：每话场景与人物。
- `--cleanup` 或 `python scripts/clean_pages.py --work .` 删除中间页图（jpg/png），`--keep` 可保留某一话。

---

## 并行与断点

- **一话一个 agent**，话与话互不依赖（圣经只读）。
- 4–8 路并发；再高容易触发限流，且不好排查。
- 断点判据：产物文件存在即完成。重跑先 `if exists: skip`。
- `progress.csv` 记 `chapter,stage,status,updated`，中断后从缺口继续。

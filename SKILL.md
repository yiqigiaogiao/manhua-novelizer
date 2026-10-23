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
pip install zhconv                  # 推荐：繁体原稿的台词覆盖不做繁简归一会失真
python scripts/build_manifest.py --help
```

**形态**：这是一个 skill——`SKILL.md` + `prompts/` + `references/` + `scripts/`。
脚本负责确定性的工作（拆页、质检、审计、成书、清理），写作由 agent 读提示词执行；不需要安装成包，也不需要 API。

## 流程

| 阶段 | 做什么 | 命令 / 执行者 | 产物 |
|---|---|---|---|
| S0 | 建清单：解析文件名、上/中/下去重、剔非正文 | `python scripts/build_manifest.py --dir pdf` | `manifest.csv` |
| **S0c** | **话级覆盖清单**：登记源里**每一话**（及每一卷、每一篇番外） | `python scripts/build_chapter_map.py --src 源目录 --out chapter-map.csv --volumes "1:1-5,2:6-10"` | `chapter-map.csv` |
| S0b | 合本拆章：按书签或页表切分 | `python scripts/split_book.py --pdf book.pdf --out chapters` | `chNNN_*.pdf` |
| S1 | 拆页：原生图抽取、长条切片、低清放大、jpg/png；也支持图片目录与**双页扫描拆分** | `python scripts/prep_pages.py --pdf x.pdf --out ch001/pages`<br>`python scripts/prep_pages.py --images 卷目录 --out ch001/pages --split-spread --direction rtl` | `pages/p0001.jpg` |
| S1.5 | **阅读顺序**：左起 / 右起 / 条漫，可人工覆盖 | `python scripts/detect_order.py --pages ch001/pages` | 写入 `config.json` |
| **S-1** | **叙事风格配置**（八维度，需用户确认） | agent + `prompts/00-style-analysis.md` | `style.json` `style.md` |
| **S-0** | **全书脊柱**：低清通读全本，写主线/人物弧/时间线/母题/节奏表 | agent + `prompts/00b-spine.md` | `spine.md` |
| S2 | 圣经：人物/势力/术法/地名/方言 | agent + `prompts/05-bible.md` | `bible.md` |
| S2.5 | 联网考据 | agent + `prompts/07-web-research.md` | `refs.md` |
| S3 | 页脚本：逐页识读成 JSON（**必经，不抽样**）。**每格必须记 `story_role`/`change`/`knows_after`/`beat`** —— 这是剧情语义，没有它下游必然写成场景串烧 | 视觉 agent + `prompts/01-page-script.md` | `page_script.json` |
| S3-alt | **廉价转录**：本地 OCR 出文字，文本模型整理（零视觉 token） | `python scripts/ocr_pages.py` + `prompts/01b-page-script-from-ocr.md` | `ocr.json` → `page_script.json` |
| S4 | 章脉络：合页成场、裁说话人、写 state；**只做索引，不产出句子**；beats 写因果链，每场带 `hook_in`/`hook_out`；**`reading` 剧情理解块必填**（S5 骨架 + S6.7 核对基准） | agent + `prompts/02-chapter-outline.md` | `outline.json` |
| S5 | 写正文：先读 `outline.reading` 建立剧情理解，再逐场照 `change` 写。**按场景分段落盘**（`draft_seg_NNN.md`），写完一段落一盘，合并再拼回 `draft.md` | agent + `prompts/03-prose.md` + `python scripts/draft_progress.py --work . --ch ch001 --merge` | `draft.md` |
| S6 | 质检：**台词覆盖必须 100%**（`--min-coverage` 默认 1.0）+ **转录完整性**（`page_script.json` 对白格 vs `outline.quotes`）+ 事件完整性 + 忠实度 | `python scripts/check_prose.py` + agent + `prompts/04-qa.md` | `qa.json` |
| **S6.1** | **统一引号**：`「」→“”`（在 S6.2 之前，否则 check_immersion 对「」稿给假绿灯） | `python scripts/normalize_quotes.py --work .` | 原地改写 draft |
| **S6.2** | **沉浸质检**：表情/动作密度、纯对白连排、概括句 | `python scripts/check_immersion.py --work .` | 退出码 0 才继续 |
| **S6.7** | **原图复检**：拿还没删的页图逐场核对正文——抓"描述与画面不一致"和"原作画面表达力丢失" | agent + `prompts/07-image-verify.md` | `verify.json` |
| **S6.75** | **按复检结论改写**：只改 `verify.json` 点到的问题，不做无关重写 | agent + `prompts/075-revise-from-verify.md` | 改 `draft.md` + 追加 `revisions` |
| **S6.7b** | **复检闸门**：没 verify.json、没读原图、major/minor 未修订 → 拦住 | `python scripts/check_verify.py --work .` | 退出码 0 才继续 |
| S6.5 | 全本一致性审计（年龄/建模/死亡/时间线/称谓），对照 spine。**输入不完整时直接标 `WARN/ERROR: 输入不完整，结果不可信` 并非零退出**（`--lenient` 放行）；正文出现「回忆/往事/当年」但 `state` 没标 `flashback` 主动提示 | `python scripts/check_consistency.py` + `prompts/06-consistency-audit.md` | `audit/consistency.md` |
| **S6.8** | **覆盖闸门**：源里几话，就必须有几话写完、几话出书 | `python scripts/check_coverage.py --map chapter-map.csv --work . --books 出书目录` | 退出码 0 才继续 |
| **S6.9** | **成书闸门**：所有话写完、过复检、静置 N 分钟、质检未过期、覆盖完整、**阅读方向已人工确认**（置信度 ≥ 0.6 或 `confirmed: true`） | `python scripts/check_ready.py --work . --check-qa --chapter-map chapter-map.csv` | 退出码 0 才继续 |
| S7 | 成书：md/docx/epub/mobi + PNG 封面 | `python scripts/assemble.py --chapter-map chapter-map.csv` | `book.*` |
| **S8** | **全本合并**：把各卷合成一部完整小说（含跨卷对账） | `python scripts/merge_books.py --books 出书目录 --out 全本 --formats md docx epub` | `全本.*` |
| **S9** | **清理页图**：**确认完整后才下这个指令**。默认只报不删；`--confirm` 才真删 | `python scripts/clean_pages.py --work . --dry-run` → `--confirm` | 释放磁盘 |

> **S6.7/S6.75 是治"粗糙"的正主，不是可选项。**
> 实测：逐页忠实、台词 100% 覆盖的稿子仍然能走样——因为 S3/S4/S5 全程
> 没有一步拿着原图和正文对着看。剧情理解靠 `reading` 重建、格间过渡靠
> `change` 推断，两者都会失真，只有拿图核能发现。
> 页脚本的原图在 S6.7 之前**不许删**（见 S9）。

> **S9 的清理是显式人工动作，不再是流水线自动步。**
> 页图是 S6.7 复检的事实源：删了，"描述与画面不一致"就永远没机会核对。
> 所以 `clean_pages.py` **默认只报不删**，必须 `--confirm` 才真删；
> `assemble.py` 成功后也不再自动清。
> `--after-verify` 可只删已过复检的章，没过复检的章留着还能补核。

> **S6.9 不可跳过。** 并行写多话时，写作 agent 的收尾写入会和成书抢同一个文件——
> 实测出现过 4 次"成书后又被改写"，每次都靠人工比对 mtime 才发现。
> `check_ready.py` 把这个判断变成一条命令：缺文件、还在改、质检过期，任一命中就拒绝成书。

> **S6.8 更不可跳过：它拦的是"整本少话"这种最贵的漏。**
> `check_ready.py` 只检查 **work 里已经存在** 的 `ch*`——源里压根没建目录的话，
> 不会变成任何一条 problem，闸门一路全绿，最后少掉十几话才发现。
> 实测：整本 78 话只写了 60 话，闸门每次都报 ready。
> 根因是没有任何一步拿 **源** 当基准。S0c 的 `chapter-map.csv` 就是这个基准，
> S6.8 拿它对账，缺一话就红。
> 源里整卷含多话时，用 `--volumes "1:1-5,2:6-10"` 声明每卷覆盖哪些话；
> 源里本来就有单话目录时（`第06话`…`第78话`），话号是现成的，不用声明。
> **另外：整卷并不等于全部话。** 有的作品整卷只到话 70，剩下的 71–78 只以单话形式存在——
> 不看源目录结构就以为"卷数×5=话数"，必然漏。

> **S8 全本合并的关键是"怎么从 book.md 里把话切回来"。**
> 三个实测过的坑，`merge_books.py` 全部规避：
> 1. **不能按 `---` 切**——正文里大量用 `---` 做分场线，会把一话拦腰切成两块
>    （第04卷第17话、第15卷第76话都中招），块数与 stats.csv 对不上。
> 2. **不能把每个 `## ` 都当章节**——正文小节也用 `## `
>    （第04卷第19话的「一/二/三」分节、月刊番外的「## 篇名」）。
>    正确做法是拿**目录标题做锚点**：目录第 N 项的标题在正文块里按序定位，
>    两个锚点之间的所有块（含小节）都归该话。
> 3. **锚点匹配要做繁简归一**——stats.csv 可能写「前日譚」（繁），
>    book.md 块首是「前日谭」（简），逐字比较失败会让整个锚点机制放弃。
> `merge_books.py` 对账不过（块数对不上、跨卷重复）会**拒绝合并**，宁可报错也不悄悄丢话。

**全局层与局部层是并列的，不能互相替代**：`spine.md` 管"全书不矛盾"，
`page_script.json` 管"每一页都在场"，章节 1:1 管"完整还原"。详见 `references/global-local.md`。

**光有具体场景不等于小说。** 实测发现：逐页忠实、台词 100% 覆盖的稿子，
仍可能"只是把场景描写搬上台"——含对白的段落里 **89–99% 没有任何表情或动作穿插**，
人物只有台词没有脸，场景之间没有推力。这是 AI 味的另一个主要来源。

**但解法不是加配额。** 早期版本要求"动作段 ≥35%""每 300 字一处微动作"，
结果稿件被填满编出来的手指、喉结和肩膀——**这本身也是 AI 味，而且更糟**。
现在改成两条无配额规则：

- **表情/神态：有依据才写。** 页脚本写了就写，没写就别编；
  写出来的每个动作都要能回到页脚本找到出处，找不到就删。
- **因果：每场结束时，处境必须和开场时不一样。** 用一个具体的现场细节
  把这一场接到上一场的后果上，而不是用叙述句做连接。

由 S4 的 `hook_in`/`hook_out` 与 S5 的因果链、表情依据规则共同负责，
S6.2 负责拦住元语言与概括句。

**光有规则还不够，必须有一次拿图核对。** 上面这些规则都在"没有完整画面"的条件下执行：
S3 记的是静态格、S4 重建因果、S5 照 change 推断过渡——每一环都会失真。
实测最典型的三类走样：

1. **描述与画面不一致**：正文写"把令牌拍在桌上"，画面上是"滑落、俯身去接"。
   这不是文笔问题，实打实是事实错误，而 S6 的台词覆盖率、S6.2 的沉浸度都查不出来。
2. **剧情理解偏差**：把一场"托付"读成"争执"，后面整章的情绪都跟着歪。
   根因是 S3 只记了"画面里有什么"，没记"这一格让什么变了、谁知道了什么"。
3. **原作表达力丢失**：原作末格用全景把代价压在构图上、一句台词都没有，
   正文写成了"他低头看着裂纹"——那一格的力量没了。

对应的三处改动：

- **S3 增加剧情语义字段** `story_role` / `change` / `knows_after` / `beat`，让页脚本不再是静态照片。
- **S4 增加 `reading` 剧情理解块**（这一话在讲什么、谁要什么、状态差了什么、
  画面担当在哪），S5 必须先读它再动笔。
- **S6.7 + S6.75 + S6.7b**：拿原图逐场核对正文，按结论定点改写，闸门拦住未核/未改的章。
  **因此页图在 S6.7 之前不许删**（S9 改为显式人工确认）。

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

- 成书格式：`md` / `docx` / `epub` / `mobi`（MOBI 由内置 PalmDOC 写出器生成，不依赖 calibre）+ `cover.png`。
  **本地阅读器（Kindle 设备 / KOReader / Calibre）可读取**；内置写出器不做压缩，体积偏大，
  **未经 Kindle 邮件推送验证**——推送请先用 calibre 转一遍：`ebook-convert book.epub book.mobi`。
- 页图支持 `jpg`（默认）与 `png`：`python scripts/prep_pages.py --format png`。
- **页图不自动删。** 成书后页图仍在 `chNNN/pages/`——它们是 S6.7 复检的依据，
  也是你日后回头核对的唯一证据。确认全书无误后，再显式下清理指令
  （**这是唯一的删除入口；`assemble.py` 没有 `--cleanup`，也不会删页图**）：

  ```bash
  python scripts/clean_pages.py --work . --dry-run            # 先看会删多少、省多少
  python scripts/clean_pages.py --work . --confirm            # 确认无误，真删
  python scripts/clean_pages.py --work . --confirm --after-verify  # 只删过了复检的章
  python scripts/clean_pages.py --work . --confirm --keep ch001/pages  # 留某一话
  ```
- 封面标题卡按平台探测中文字体（`MHN_COVER_FONT` 环境变量可覆盖，见 README「封面字体」）；
  一个都没找到就只出底色封面，不会崩。
- **中间页图会占几百 MB 到几 GB**，确认全书无误后由人显式删：
  `python scripts/clean_pages.py --work . --confirm`（**唯一删除入口，`assemble.py` 不删页图**）；
  `--keep ch001/pages` 可保留某一话，`--dry-run` 先看会删多少。

## 质量闸门

| 检查 | 合格线 | 谁做 |
|---|---|---|
| 台词覆盖（原文对白逐字落地） | **100%**（`--min-coverage` 默认 1.0） | `python scripts/check_prose.py` |
| **转录完整性**（`page_script.json` 的对白格 vs `outline.quotes`） | **不缺记** | `python scripts/check_prose.py` |
| 事件完整性（beats 是否落地） | 无关键遗漏 | agent |
| 忠实度（抽 3 页对照原图） | 无编造 | agent |
| **话级覆盖（源里几话都写了、都出书了）** | **无缺失、无重复** | `python scripts/check_coverage.py` |
| 一致性（年龄/建模/死亡/时间线） | 0 error | `python scripts/check_consistency.py` |
| **阅读方向已人工确认**（置信度 ≥ 0.6 或 `confirmed: true`） | **已确认** | `detect_order.py` + `check_ready.py` |

**没有字数线，没有禁词线。**

> **繁体原稿必须装 `zhconv`**（`pip install zhconv`）。不装时 `check_prose.py` 的
> `normalize()` 只剔非中英数字符、不做繁简归一，台版/港版原稿的台词覆盖会失真——
> 要么漏判（繁体对白在简体正文里找不到），要么靠 `difflib` 0.8 兜底误放/误杀。
> `merge_books.py` 那边早就强调繁简归一，这道最关键的闸门不能例外。

## 目录约定

```
<work>/
├─ pdf/ 或 book.pdf
├─ chapters/                 S0b 产物
├─ manifest.csv              S0（文件级）
├─ chapter-map.csv           S0c（话级：源里到底有几话）★覆盖闸门的基准
├─ style.json  style.md  style_history/    S-1
├─ spine.md                                 S-0
├─ bible.md  glossary.csv                  S2
├─ refs.md   claims.csv                    S2.5
├─ config.json
├─ audit/consistency.md                    S6.5
├─ build/                    S7（book.md/docx/epub/mobi, cover.png）
└─ ch001/
   ├─ pages/                S1（★ S6.7 原图复检完成后才允许删）
   ├─ page_script.json       S3
   ├─ outline.json           S4（含 state + reading）
   ├─ draft.md               S5
   ├─ qa.json                S6
   ├─ verify.json            S6.7（图对文核对 + S6.75 的 revisions）
   ├─ ps_p0001.json…          S3 单页转录（自愈的最小验收单元）
   └─ digest.md              可选：分场摘要，供 S5 翻阅
```

---

## S3 转录编排：agent 挂掉必须能自动补位（硬要求）

> "一个子 agent 挂掉，后续会自动补上"——这不是可选的健壮性，是流程的**基本形态**。

**实测教训**：整段式转录（一个 agent 读 20+ 页、最后一次性写一个 `page_script.json`）
命中率极低。agent 报告"Page 20 read. Proceeding to final page 21."然后失联——
**已读的 20 页全部丢失，因为要等尾声才落盘**。一轮派 15 个 agent，全部无产出。

### 四条设计原则

| 原则 | 做法 | 理由 |
|---|---|---|
| **小段** | 每 3 页一段任务 | 粒度小到 agent 在上下文耗尽前就能完成并落盘 |
| **单页文件** | 每读一页立刻写 `ps_pNNNN.json` | 中断不丢已读页——自愈的前提 |
| **以文件为验收** | 重跑扫磁盘已存在的页，只跑缺失的 | agent 说"写好了"不可信，文件在才算完成 |
| **双层重试** | agent 内重试 + 外层按缺失页补跑 | 一段失败不必重跑整话 |

### 编排脚本骨架（workflow 工具）

```javascript
// 3 页一段；批内并发 4、批间串行（全并发会把 agent 拖垮）
const segs = [];
for (let s = 1; s <= TOTAL; s += 3) segs.push({ start: s, end: Math.min(s + 2, TOTAL) });

async function one(seg) {
  const prompt = buildPrompt(seg);   // 必须明确列出：读哪几页 + 每页写哪个文件
  for (let att = 1; att <= 3; att++) {
    const r = await agent(prompt, {
      label: `${CH} p${seg.start}-${seg.end} try${att}`,
      schema: { type: 'object',
                properties: { written: { type: 'array', items: { type: 'integer' } } },
                required: ['written'], additionalProperties: false }
    });
    if (r && Array.isArray(r.written) && r.written.length > 0)
      return { seg, ok: true, written: r.written, att };
  }
  return { seg, ok: false, written: [], att: 3 };
}

let out = [], BATCH = 4;
for (let i = 0; i < segs.length; i += BATCH)
  out = out.concat(await parallel(segs.slice(i, i + BATCH).map(s => () => one(s))));

const missing = [];
for (let p = 1; p <= TOTAL; p++)
  if (out.flatMap(o => o.written).indexOf(p) < 0) missing.push(p);
return { pages_written: TOTAL - missing.length, missing };  // missing 立刻再跑一轮补位
```

### 验收与合并

```bash
# 看写到哪了、缺哪几页（自愈的输入）
python scripts/transcribe_progress.py --work work --ch ch001

# ps_pNNNN.json × N  ->  chNNN/page_script.json（S4 的输入）
```

**不要在 agent 提示词里让它"最后汇总成一个文件"**——汇总会诱导攒盘，
把自愈的前提毁掉。汇总交给合并脚本。

实测效果（《极度恐慌》ch001，22 页）：8 段里 7 段一次成功，缺 p4–6；
补位跑一轮即补齐，共 19+3=22 页，`change`/`story_role` 字段均正常落盘。

---

## S5 正文写作：同样要能自愈（别让半截稿骗过 check_ready）

S3 早就改成"小段 + 单页落盘 + 文件验收 + 双层重试"了，但 S5 写正文曾经
是**一话一个 draft.md**：agent 写一半挂掉，磁盘上就留半截稿，而半截稿和
完成稿长得一模一样——`check_ready.py` 的静置检查只看 mtime，分不出
"写完了"还是"写到一半断了"。几百话批量时，S5 是比 S3 更大的失败面。

照搬 S3 的模式，`scripts/draft_progress.py` 提供支撑：

```bash
# 看写到哪了、缺哪几段（自愈的输入）
python scripts/draft_progress.py --work work --ch ch001

# 所有段齐了，才合并成 draft.md（原子写：临时文件 -> os.replace，不会留半截稿）
python scripts/draft_progress.py --work work --ch ch001 --merge
```

编排约定：

- **按场景分段**：`outline.json` 的 `scenes[]` 每场一段，文件 `draft_seg_001.md`、
  `draft_seg_002.md`…… 与 `scenes` 下标一一对应。
- **写完一段就落盘**：中断只丢当前这一段，前面全在。空文件不算完成。
- **以文件为验收**：重跑扫磁盘已存在的段，只跑缺失的。
- **合并再拼 `draft.md`**：段落不齐 `merge` 直接拒绝（不会把半截稿当完成稿）；
  原子写保证 `draft.md` 要么完整要么不存在。`draft.md` 比所有段都新时 `merge`
  默认跳过，保护人工修改，要强制覆盖加 `--force`。
- **让写作 agent 逐段写 `draft_seg_NNN.md`，不要让它最后汇总成一个 `draft.md`**——
  汇总会诱导攒盘，把自愈前提毁掉。合并交给 `draft_progress.py --merge`。

## 常见坑

- **整回版可能是残片**：同回有"整回"和"上/中/下"时按页数选全。
- **合本没书签**：`scripts/split_book.py` 会报错并提示写 `chapter-map.csv`。
- **长条页**：高/宽 > 2.6 必须切片，片间留 10–15% 重叠。
- **低清页**：宽 < 1000 px 放大到 1100+ 再识读。
- **同名不同世**：跨时代角色用 `名(时代)` 作主键。
- **跨叙事层误报**：回忆/往事要给 `state.timeline = "flashback"`，否则死亡与年龄检查会误判。
- **别用字数判断好坏**：写得短可能是原作就短；写得长可能是把留白填满了。
- **路径里带方括号会打瞎 glob**：中文下载目录常见「【完】」「[扫描]」这类名字，
  `glob`/`fnmatch` 会把方括号当字符类，一条都匹配不到。脚本里用
  `_shared.list_dirs()`（`os.scandir` + 字面前后缀），不要用 `glob`。
- **整卷 ≠ 全部话**：先看源目录结构再估总量。有的作品整卷只到话 70，
  剩下的只以单话目录存在。用 S0c 登记，别用"卷数×5"去猜。

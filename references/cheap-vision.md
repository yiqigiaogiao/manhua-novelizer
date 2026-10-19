# 降低读图成本：开源方案与分级策略

> 现状：让视觉模型逐页读图，每页约 1.2k–1.8k token。第 1 卷 182 页 ≈ **27 万视觉 token**，
> 这还只是转录，不含后续写作。这是整条流水线最贵的一步。

## 一、先把账算清

| 方案 | 视觉 token | 文本 token | 相对成本 | 丢失的信息 |
|---|---|---|---|---|
| T3 视觉模型逐页读（当前） | ≈27 万 | 少 | 1.0× | 无 |
| T2 本地视觉模型（Ollama） | 0（本地算力） | 少 | 电费 | 精度略降 |
| T1 OCR + 低分辨率缩略图 | ≈2 万 | ≈8 万 | ≈0.15× | 构图/光影细节 |
| T0 纯 OCR | 0 | ≈6 万 | ≈0.05× | 动作、表情、构图、拟声位置 |

结论：**对话密集的页面用 OCR，视觉关键的页面才用视觉模型**。按页分流，通常能省 70–85%。

## 二、可用的开源项目

| 项目 | 做什么 | 语言 | 备注 |
|---|---|---|---|
| [magi](https://github.com/ragavsachdeva/magi) | 检测人物/文字块/分格、**给分格排序**、人物聚类、文字归属到说话人、OCR | 日漫为主 | 就是 "From Panels to Prose" 那篇论文的官方实现；结构化能力最全，可直接产出 transcript |
| [comic-text-detector](https://github.com/dmMaze/comic-text-detector) | 文字块 + 气泡检测（ONNX） | 语言无关 | 轻量、CPU 可跑，适合先切气泡再 OCR |
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | 中/繁/日 OCR，含竖排方向分类 | 多语 | 中文漫画首选；模型较大 |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | PaddleOCR 的 ONNX 轻量版 | 多语 | 无需 torch，pip 即装，CPU 友好 |
| [manga-ocr](https://github.com/kha-white/manga-ocr) | 日漫整气泡 OCR | 仅日文 | 中文用不上 |
| [Kumiko](https://github.com/manga109/Kumiko) | 日漫文字检测+OCR | 仅日文 | 同上 |
| [Qwen2.5-VL](https://github.com/QwenLM/Qwen2.5-VL) / [MiniCPM-V](https://github.com/OpenBMB/MiniCPM-V) | 本地视觉模型 | 多语 | 8B 级可跑消费级显卡；Ollama 直接拉 |

分工建议：

```
页图 ──► comic-text-detector（切气泡/文字块）
      ──► RapidOCR 或 PaddleOCR（识别文字，含竖排）
      ──► magi（分格排序 + 文字归属说话人）
      ──► 结构化 JSON ──► 文本模型写 page_script
```

只在两类页面上补视觉模型：**整页无字/拟声为主的动作页**、**跨页大格与关键揭示页**。

## 三、三级流水线（本项目已留接口）

### T0：纯 OCR（最省）

```bash
python scripts/ocr_pages.py --pages work/ch001/pages --out work/ch001/ocr.json --direction rtl
```

产出：

```json
{"pages":[{"page":1,"lines":[{"text":"这里是第二开拓局！","bbox":[0.62,0.08,0.95,0.22],"conf":0.93}]}]}
```

再用 `prompts/01b-page-script-from-ocr.md` 让**文本模型**把它整理成 `page_script.json`：
有台词、有位置、有阅读顺序，但没有动作与表情描述——`visual` 一律留空，不许编。

代价：正文会明显偏"对话流"，动作与空间感变弱。适合对话密集、画面信息少的作品。

### T1：OCR + 低分辨率缩略图（推荐默认）

每页额外附一张 **400px 宽的缩略图**（约 100–150 token），只用来判断"这一页在发生什么"：

- 有几个人、大概什么动作、是室内还是舱外；
- 不要求读字（字由 OCR 负责）。

成本约为 T3 的 15%，质量能到 T3 的七八成。

### T2：本地视觉模型

```bash
ollama pull qwen2.5vl:7b     # 或 minicpm-v
```

把 `prompts/01-page-script.md` 里的模型换成 ollama 的本地端点即可。零 token 费，慢，精度略降。

### T3：API 视觉模型（当前做法）

只在 T1 标出的"关键页"上跑：战斗、跨页、无对白但信息量大的页面。

## 四、怎么判断该用哪一级

用脚本先做一次**页面分诊**（不需要模型）：

- 文字块面积占比 > 25% → 对话页，走 T0/T1；
- 文字块 < 5% 且画面有大幅动作线 → 关键页，走 T3；
- 整页近白或近黑 → 过场页，T0 即可。

`scripts/ocr_pages.py` 会顺带输出每页的文字覆盖率，可直接拿来分诊。

## 五、质量红线

无论用哪一级，以下三条不变：

1. **台词逐字**：OCR 结果必须人工或模型二次校对，错字率高于 3% 就不能用。
2. **不编视觉**：没看图就不许写 `visual`；宁可留空，让正文靠对白推进。
3. **说话人归属**：OCR 只给位置，归属要靠尾巴方向或上下文；判不了就 `unknown`。

## 六、当前仓库的支持程度

- `scripts/ocr_pages.py`：已提供，依赖 `rapidocr-onnxruntime` 或 `paddleocr`；未安装时给出明确提示。
- `prompts/01b-page-script-from-ocr.md`：纯文本转录提示词，配合 T0/T1 使用。
- `prompts/01-page-script.md`：T2/T3 的视觉转录提示词（原路径不变）。

## 八、实测记录（2026-10-19 希德尼娅第 2 卷，8 个并行 agent）

**最贵的错误：agent 自己裁图放大重读。**

第 2 卷开跑时，4 个 agent 遇到竖排小字读不清，开始自己写 `_crop.py` 裁图：
一页裁成 3–5 块，每块单独 read_image。`_crops/` 到 `_crops5/` 铺满目录，
23 页的段落跑了 70 分钟还没落盘。

**根因不是模型，是提示词有歧义**：原提示词只说"看不清用 `?` 占位"，
没说"不许重读"。于是 agent 把 `?` 当成必须解决的问题，而不是可接受的交付。

**修法**（已写进 `prompts/01-page-script.md` 第 5、10 条）：

```
一页只读一次；不许裁图、不许放大局部、不许重读。
看不清就记 ?，不要试图解决它。
```

**教训**：并行 agent 的数量是显性成本，"每个 agent 多走几步"是隐性成本。
后者不看账单发现不了——只能靠产物落盘速度判断。23 页一段 **超过 20 分钟没落盘就该怀疑**。

> 实测记录（本机 Python 3.13）：
> 1. `pip install rapidocr-onnxruntime` 下载超时（14.9MB 只到 3.4MB）；
> 2. 重试装上了，但 `import rapidocr_onnxruntime` 直接触发 access violation（0xC0000005）——
>    onnxruntime 对 Python 3.13 支持不全。已卸载，避免污染环境。
## 六、当前仓库的支持程度

- `scripts/ocr_pages.py`：已提供，依赖 `rapidocr-onnxruntime` 或 `paddleocr`；未安装时给出明确提示。
- `prompts/01b-page-script-from-ocr.md`：纯文本转录提示词，配合 T0/T1 使用。

## 七、实测记录（希德尼娅第 1 卷 p19，2026-10-19）

### 装得上的关键

1. **onnxruntime 1.31.0 是坏 wheel**——`import` 直接 access violation（0xC0000005）。
   降到 **1.20.1** 即正常。这是崩溃的真正原因，与 Python 版本无关。
2. Python 3.13 + rapidocr 1.4.4 同样崩；用 `uv venv --python 3.12` 建独立环境最稳。
3. opencv 5.0 无问题，不用降。

一条命令搞定：

```bash
uv venv --python 3.12 _ocr_env
uv pip install --python _ocr_env/Scripts/python.exe rapidocr-onnxruntime "onnxruntime==1.20.1"
```

### 识别质量

简中/繁体印刷体识别良好（"偷米了。""會被做成肥料""等一下，""16" 均正确，conf 0.87–1.00），
**但竖排文字会被切成多个碎片**：

```
conf=0.99 x=618-647 | 人類。
conf=0.94 x=646-677 | 靠之外的
conf=0.99 x=679-710 | 我来没見過
```

同一气泡的三列竖排，被切成 3 个 box，每列内部还可能再碎。

### 竖排不能简单合并

试过按列聚类（16 碎片 → 7 列），但出现**跨气泡错误合并**：
不同气泡的两列因为 x 接近被并成一句，产生了原句没有的台词。
**错误合并 = 编造台词，比拆碎更糟。**

所以竖排日漫/台漫的正确姿势是：

```
comic-text-detector 先切气泡 ──► 每个气泡内 OCR ──► 气泡作为最小单位
```

没有气泡检测时，宁可输出碎片让文本模型重组，也不要脚本硬合。

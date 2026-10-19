# 调研与设计依据

做这个 skill 之前查过的现存方案，以及它们各自贡献了什么、为什么不能直接用。

## 现存方案

| 方案 | 类型 | 能用的部分 | 局限 |
|---|---|---|---|
| [Anthropic `pdf` skill](https://github.com/anthropics/skills)（`skills/pdf/SKILL.md`） | 官方 skill | PDF 处理规范：拆页、抽图、扫描件转图再 OCR、`pdfimages`/`pypdfium2` 的用法 | 面向**有文本层**的文档；其核心路径 `extract_text()` 对纯图 PDF 返回空 |
| [cosmisum](https://github.com/sammwyy/cosmisum) | 开源工程 | 最接近的流水线骨架：PDF→页图→切格→OCR→LLM 分块→输出；token 上限下的均匀分块策略 | 只做到"摘要/标签/分类"，没有小说化；OCR 用 Tesseract，中文彩漫识别率不够 |
| [From Panels to Prose (arXiv 2503.23344)](https://arxiv.org/abs/2503.23344) | 论文 | 方法论：Magiv3 做分格/人物/气泡/尾巴/OCR 的结构化理解，再接 VLM 生成文学叙述；并证明"直接让 VLM 看图讲故事"质量差 | 面向日漫 + 视障朗读；语言与文风不是中文小说 |
| [manga-ocr](https://github.com/kha-white/manga-ocr) | OCR 模型 | 整气泡一次识别（不分行）、竖横混排鲁棒 | 只支持日文 |
| [comic-script-generator](https://github.com/AveQY/comic-script-generator) | skill（反向） | 分镜字段设计：画面描述、镜头角度、角色对话——直接搬进 `page_script` schema | 方向相反（文→分镜） |
| [novel_to_comic](https://github.com/aiskyhub/novel_to_comic) | skill（反向） | skill 的打包方式：阶段目录 + 提示词 + 验收清单 | 方向相反 |

**结论**：没有可直接用的"中文国漫 → 小说"skill。自建，但站在三样东西上：cosmisum 的工程骨架、Panels to Prose 的两段式、Anthropic pdf skill 的拆页规范。

## 由调研得出的四个设计决定

1. **两段式（转录 → 写作）**。Panels to Prose 的核心结论：结构化理解是叙述质量的前提。直接看图写，模型会把"没画的东西"补进去。
2. **逐页 JSON 落盘**。cosmisum 是整篇切块喂 LLM，出错无法定位；页级 JSON 可逐条对账、可缓存、可断点。
3. **视觉直读 > 传统 OCR**。中文彩漫有手写体、艺术字、气泡压图、方言字，Tesseract 错误率高；现代视觉模型直读 + 置信度标注更实用。manga-ocr 的"整气泡一次识别"思路仍然适用。
4. **可机检的验收**：台词覆盖与人物白名单写成脚本，事件完整性、忠实度、声音一致性交给 agent 抽页复核——纯靠人读几百话不现实。v0.3 起取消字数与禁词检查：它们衡量的是"像不像某种文体"，而不是"忠不忠实于原作"。

## 实测数据（一个真实案例的量级）

一批 311 个 PDF、4.33 GB 的中文彩漫：

- 每页 = 1 张 JPEG，**767 页级文本层全空**，`pdftotext` 与 `pypdf.extract_text()` 均为 0 字符。
- 去重后 285 个文件 / 6980 页，约 7000 张图。
- 原生宽 900–1418 px，其中 162 个文件首页 < 1000 px，最小 413 px。
- 11 页是长条（最高 900×13830），必须切片。
- 95 组同回多文件，"整回版"有残片（26 页 vs 28+29 页），必须按页数选全。
- 台词带明显方言（川渝腔），批量改写会丢人物口音。

这些数字决定了默认参数：`--min-width 1100`、`--tile-ratio 2.6`、重叠 12%、页级缓存、按话并行。

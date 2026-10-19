# Manhua Novelizer · 漫画小说化 Skill

把**只有图、没有文本层**的中文漫画 PDF，批量转成小说正文。

```
PDF 页图 ──► 页脚本 JSON ──► 章脉络 ──► 小说正文 ──► 质检
             (逐格转录)      (合并成场)   (文学化)     (台词覆盖/禁词/长度)
```

## 为什么不是"让模型直接看图写"

实测：直接看图写作会（1）编造没画的情节，（2）漏掉 20–40% 台词，（3）把旁白当台词，（4）无法定位错误在第几页。
所以流程强制拆成两段：**先转录成可核对的 JSON，再只吃 JSON 写作**，质检才能逐条对账。

## 安装

任选其一（skill 就是一份带 `SKILL.md` 的目录）：

```bash
# Claude Code / 兼容 skills 的 agent
git clone https://github.com/<you>/manhua-novelizer ~/.claude/skills/manhua-novelizer

# DSH
git clone https://github.com/<you>/manhua-novelizer ~/.dsh/skills/manhua-novelizer

# 其它 agent：把目录放进其 skills 搜索路径，或直接把 SKILL.md 当提示词喂给 agent
```

依赖：

```bash
pip install pymupdf pillow          # 必需（拆页）
pip install python-docx             # 可选（导出 docx）
```

## 用法

```bash
mkdir -p mywork/pdf && cp *.pdf mywork/pdf/
cd mywork

python ../manhua-novelizer/scripts/build_manifest.py --dir pdf --out manifest.csv
python ../manhua-novelizer/scripts/prep_pages.py --pdf "pdf/001：第一话 上.pdf" --out ch001/pages
```

然后让 agent 读 `SKILL.md`，按 S2–S6 逐话执行（`prompts/` 下是五份可直接使用的提示词）。

最后：

```bash
python ../manhua-novelizer/scripts/check_prose.py --draft ch001/draft.md \
       --outline ch001/outline.json --bible bible.md --pages 29 --out ch001/qa.json
python ../manhua-novelizer/scripts/assemble.py --work . --out book
```

## 目录结构

```
manhua-novelizer/
├─ SKILL.md                 主入口（agent 先读这个）
├─ references/
│  ├─ pipeline.md           八个阶段的完整规范
│  ├─ schemas.md            page_script / outline / qa / config 的 JSON schema
│  ├─ style-guide.md        文风、禁词、改编参数
│  └─ research.md           调研来源与设计依据
├─ prompts/
│  ├─ 01-page-script.md     逐页转录
│  ├─ 02-chapter-outline.md 章脉络
│  ├─ 03-prose.md           小说正文
│  ├─ 04-qa.md              质检与修补
│  └─ 05-bible.md           系列圣经
├─ scripts/
│  ├─ build_manifest.py     S0
│  ├─ prep_pages.py         S1
│  ├─ check_prose.py        S6（自动项）
│  └─ assemble.py           S7
└─ examples/                合成示例（非真实作品，仅演示字段）
```

## 已知限制

- 视觉转录质量取决于页图分辨率；宽 < 700 px 的源图建议先超分再识读。
- `check_prose.py` 的命名白名单是启发式的（靠"说/道/问"前后两三个字），会有噪声，最终仍需 agent 复核。
-  faithfulness（忠实度）无法纯脚本判定，`qa.json` 里留 `manual` 字段给 agent。
- 不处理竖排右起的老式排版（如港漫），需要时可加 `--rtl` 扩展阅读顺序。

## License

MIT

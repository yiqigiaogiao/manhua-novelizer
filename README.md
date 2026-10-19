# Manhua Novelizer · 漫画小说化 Skill

把**只有图、没有文本层**的中文漫画 PDF，批量转成小说正文；单话版和"一册装几十话"的合本都能处理。

```
PDF 页图 ──► 页脚本 JSON ──► 章脉络(+state) ──► 小说正文 ──► 单话质检
             (逐格转录)       (合并成场)        (文学化)      (台词/禁词/长度)
                                                              │
                                         全本一致性审计 ◄─────┘
                                    (年龄/建模/死亡/时间线)
```

## 为什么不是"让模型直接看图写"

实测：直接看图写作会（1）编造没画的情节，（2）漏掉 20–40% 台词，（3）把旁白当台词，（4）无法定位错误在第几页。
所以强制两段式：**先转录成可核对的 JSON，再只吃 JSON 写作**，质检才能逐条对账。

## 新增能力（v0.2）

| 能力 | 怎么用 |
|---|---|
| **多章 / 合本 PDF** | `split_book.py` 按 PDF 书签或 `chapter-map.csv` 切成单话；没书签也能手工给页表 |
| **页段直取** | `prep_pages.py --first-page 120 --last-page 168`，不拆文件也能只做一段 |
| **全本一致性审计** | `check_consistency.py` + agent：查年龄倒退、时间倒流、死者复现、外观/建模漂移、未入册人名 |
| **联网考据** | `prompts/07-web-research.md`：把人物、时间线、术语核准成 `refs.md` + `claims.csv`，每条带 URL |

## 安装

```bash
# Claude Code / 兼容 skills 的 agent
git clone <repo> ~/.claude/skills/manhua-novelizer

# DSH
git clone <repo> ~/.dsh/skills/manhua-novelizer
```

依赖：

```bash
pip install pymupdf pillow      # 必需
pip install python-docx         # 可选，导出 docx
```

## 用法

### 1. 单话 PDF

```bash
mkdir -p mywork/pdf && cp *.pdf mywork/pdf/ && cd mywork
python ../manhua-novelizer/scripts/build_manifest.py --dir pdf --out manifest.csv
python ../manhua-novelizer/scripts/prep_pages.py --pdf "pdf/001：第一话 上.pdf" --out ch001/pages
```

### 2. 一册装几十话的合本 PDF

```bash
python ../manhua-novelizer/scripts/split_book.py --pdf book.pdf --out chapters --dry-run
python ../manhua-novelizer/scripts/split_book.py --pdf book.pdf --out chapters
python ../manhua-novelizer/scripts/build_manifest.py --dir chapters --out manifest.csv
```

没有书签时，写一个 `chapter-map.csv`：

```csv
chapter,title,start,end
1,皓光当空,1,29
2,阴阳仙君,30,78
```

再 `--map chapter-map.csv`。

### 3. 让 agent 干 S2–S6

把 `SKILL.md` 交给 agent（或放进 skills 目录），它按 `prompts/` 逐话执行：
圣经 → 联网考据 → 页脚本 → 章脉络 → 正文 → 质检。

### 4. 全本质检与合本

```bash
python ../manhua-novelizer/scripts/check_prose.py --draft ch001/draft.md \
       --outline ch001/outline.json --bible bible.md --pages 29 --out ch001/qa.json

python ../manhua-novelizer/scripts/check_consistency.py --work . --bible bible.md \
       --out audit/consistency.md --json audit/consistency.json

python ../manhua-novelizer/scripts/assemble.py --work . --out book --title "书名"
```

## 一致性审计查什么

`state` 由 S4 每话产出：

```json
"state": {"year": 3, "flashback": false,
          "cast": {"阿禾": {"age": 14, "status": "alive", "look": "束发，旧棉袍"}}}
```

| 机器查 | 判据 |
|---|---|
| 时间倒流 | `year` 倒退且未标 `flashback` |
| 年龄 | 时间前进 N 年，年龄不涨或倒退 |
| 死亡 | 已标 `dead` 的角色在后话又活着出现 |
| 外观/建模 | 与 bible 基准差异过大，或前后话突变 |
| 人名 | 出场人物不在 bible |

机器判不了的（换装是否合理、术法是否凭空出现、称谓是否一致）由 agent 按
`prompts/06-consistency-audit.md` 判，每条必须给页码证据。

## 目录结构

```
manhua-novelizer/
├─ SKILL.md                  主入口（agent 先读这个）
├─ references/
│  ├─ pipeline.md            S0–S7 + S0b/S2.5/S6.5 完整规范
│  ├─ schemas.md             page_script / outline / state / qa / config / chapter-map
│  ├─ style-guide.md         文风、禁词、改编参数
│  └─ research.md            调研来源与设计依据
├─ prompts/
│  ├─ 01-page-script.md      逐页转录
│  ├─ 02-chapter-outline.md  章脉络（含 state）
│  ├─ 03-prose.md            小说正文
│  ├─ 04-qa.md               单话质检
│  ├─ 05-bible.md            系列圣经
│  ├─ 06-consistency-audit.md 全本一致性审计
│  └─ 07-web-research.md     联网考据
├─ scripts/
│  ├─ build_manifest.py      S0
│  ├─ split_book.py          S0b 合本拆章
│  ├─ prep_pages.py          S1
│  ├─ check_prose.py         S6
│  ├─ check_consistency.py   S6.5
│  └─ assemble.py            S7
└─ examples/                 合成示例（非真实作品）
```

## 已知限制

- 视觉转录质量取决于页图分辨率；宽 < 700 px 的源图建议先放大再识读。
- `check_prose.py` 的命名白名单是启发式（靠"说/道/问"前后几个字），有噪声，最终仍需 agent 复核。
- 忠实度无法纯脚本判定，`qa.json` 里留 `manual` 字段给 agent。
- `check_consistency.py` 只做机械判定；"外貌变化是否合理"这类必须人来判。
- 不处理竖排右起的老式排版（港漫），需要时可加 `reading_direction: rtl` 扩展阅读顺序。
- `split_book.py` 依赖 PDF 书签；没有书签就必须给 `chapter-map.csv`。

## License

MIT

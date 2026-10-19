# 示例

这里的数据都是**合成的**（人物、台词、剧情均为演示虚构），不含任何真实作品内容。

| 文件 | 对应阶段 | 用途 |
|---|---|---|
| `config-example.json` | 全流程 | 改编参数 |
| `chapter-map-example.csv` | S0b | 合本 PDF 无书签时的章节页表 |
| `page-script-example.json` | S3 | 页脚本字段长什么样 |
| `outline-example.json` | S4 | 章脉络字段（含 `state`） |
| `bible-example.md` | S2 | 设定圣经格式 |
| `draft-example.md` | S5 | 正文格式（含 front matter） |
| `consistency-report-example.md` | S6.5 | 全本审计报告长什么样 |

自检一遍（应当通过）：

```bash
mnv qa --draft draft-example.md --outline outline-example.json --bible bible-example.md
```

一致性审计需要多话的 `outline.json`，示例目录只有一话，跑出来应当是 0 error：

```bash
mkdir -p /tmp/audit/ch001 && cp outline-example.json /tmp/audit/ch001/
mnv audit --work /tmp/audit --bible bible-example.md
```

导出成书（含 mobi 与 PNG 封面）：

```bash
mkdir -p /tmp/book/ch001 && cp draft-example.md /tmp/book/ch001/
mnv build --work /tmp/book --out /tmp/book/build --title "示例"
```

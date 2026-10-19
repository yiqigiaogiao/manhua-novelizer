# 示例

这里的数据都是**合成的**（人物、台词、剧情均为演示虚构），不含任何真实作品内容。

| 文件 | 对应阶段 | 用途 |
|---|---|---|
| `config-example.json` | 全流程 | 改编参数 |
| `page-script-example.json` | S3 | 页脚本字段长什么样 |
| `outline-example.json` | S4 | 章脉络字段长什么样 |
| `bible-example.md` | S2 | 设定圣经格式 |
| `draft-example.md` | S5 | 正文格式（含 front matter） |

自检一遍（应当通过）：

```bash
python ../scripts/check_prose.py \
  --draft draft-example.md \
  --outline outline-example.json \
  --bible bible-example.md \
  --pages 2
```

# JSON Schema

四个数据契约：`page_script`、`outline`、`qa`、`config`。

---

## 1. page_script（S3 产物，每页一个）

```json
{
  "chapter": 1,
  "part": "上",
  "page": 12,
  "layout": "3格：整宽 / 左右分栏 / 整宽",
  "panels": [
    {
      "id": "p12-1",
      "order": 1,
      "bbox": [0.03, 0.02, 0.97, 0.31],
      "shot": "中景",
      "angle": "平视",
      "scene": "正殿（室内·白日）",
      "characters": [
        {
          "name": "陈松",
          "face": "正面",
          "expression": "得意",
          "action": "指间夹着令牌举起"
        }
      ],
      "visual": "老道士举着残缺的黑色令牌，身后四名弟子只剩剪影",
      "text": [
        {
          "type": "speech",
          "speaker": "陈松",
          "text": "只有咱们这一门噻！",
          "confidence": 0.95,
          "partial": false
        }
      ],
      "notes": "令牌有螺旋纹，缺一角"
    }
  ],
  "page_summary": "陈松向弟子展示镇派令牌",
  "uncertain": []
}
```

| 字段 | 类型 | 约束 |
|---|---|---|
| `chapter` | int | 话号；番外用小数（72.5） |
| `part` | string | `上`/`中`/`下`/`""` |
| `page` | int | 1 起，与文件名一致 |
| `layout` | string | 自然语言描述格线布局 |
| `panels[].id` | string | `p{page}-{order}` |
| `panels[].order` | int | 阅读顺序，从 1 连续 |
| `panels[].bbox` | [float×4] | 归一化 `[x0,y0,x1,y1]`，左上为 0,0 |
| `panels[].shot` | enum | 大远景/远景/全景/中景/近景/特写/大特写 |
| `panels[].angle` | enum | 平视/俯视/仰视/斜角 |
| `panels[].scene` | string | 地点 + 室内外 + 昼夜/天气；判断不出就只写能确定的 |
| `panels[].characters[].name` | string | 优先 `bible.md` 的名字；否则外貌指代 |
| `panels[].visual` | string | 客观描述，不写"气氛紧张"这类评价 |
| `panels[].text[].type` | enum | speech / thought / narration / sfx / sign |
| `panels[].text[].speaker` | string\|null | 判断不了填 `"unknown"` |
| `panels[].text[].text` | string | **逐字**，看不清用 `?` 占位 |
| `panels[].text[].confidence` | float | 0–1；< 0.8 会被 S6 重点抽检 |
| `panels[].text[].partial` | bool | 长条页切片时被切断的半句 |
| `uncertain` | string[] | 所有不确定项，逐条写清楚 |

---

## 2. outline（S4 产物，每话一个）

```json
{
  "chapter": 143,
  "title": "日月炼果",
  "pages": 57,
  "scenes": [
    {
      "id": "s1",
      "place": "三真法门·正殿",
      "time": "白日",
      "pov": "陈松",
      "beats": ["陈松向弟子展示令牌", "弟子质疑令牌残缺", "陈松当场演示威力"],
      "pages": [1, 2, 3],
      "transition": "硬切到后山"
    }
  ],
  "cast": [
    {"name": "陈松", "role": "本话主视角"},
    {"name": "皓光", "role": "被提及"}
  ],
  "quotes": [
    {"page": 5, "speaker": "陈松", "text": "只有咱们这一门噻！"}
  ],
  "threads": {
    "opened": ["令牌为何残缺"],
    "advanced": ["主角身世"],
    "closed": []
  },
  "continuity": "接上话结尾：主角仍在山中，左肩带伤",
  "state": {
    "year": 3,
    "flashback": false,
    "cast": {
      "陈松": {"age": 62, "status": "alive", "look": "灰白短须，藏青道袍", "place": "正殿"}
    }
  },
  "uncertain": ["第 12 页一句台词两处模糊"]
}
```

约束：

- `beats` 必须是因果句（"因为…所以…"/"用…压服…"），不能是"他抬手/他说话"的流水账。
- `quotes` 是 S6 的对账依据，**逐字**，5–20 条。
- `continuity` 必填一句话。
- `state` 必填，字段见下节。

---

## 3. qa（S6 产物，每话一个）

v0.3 起**不再有字数与禁词检查**，只保留忠实度。

```json
{
  "chapter": 143,
  "words": 4820,
  "checks": {
    "quote_coverage": {"pass": true, "value": 0.97, "missing": []},
    "name_whitelist": {"pass": true, "suspects": [], "advisory": true},
    "events": {"pass": true, "missing_beats": []},
    "faithfulness": {"pass": true, "issues": []},
    "voice": {"pass": true, "issues": []},
    "style": {"pass": true, "issues": []}
  },
  "fixes": ["s2 补回漏掉的台词"],
  "verdict": "pass"
}
```

- `quote_coverage` 与 `name_whitelist` 由 `mnv qa` 生成；其余由 agent 按 `prompts/04-qa.md` 填写。
- 合格线：`quote_coverage ≥ 0.95`、`events.pass`、`faithfulness.pass`。
- `words` 仅作记录，**不作为合格条件**。

---

## 4. config（每项目一个，v2）

```json
{
  "version": 2,
  "work": {
    "language": "zh",
    "reading_direction": "ltr",
    "nonstory_regex": "预告|公告|请假|通知|复刊|小结|获奖|目录|版权|后记",
    "strip_suffix": ""
  },
  "adaptation": {
    "pov": "third-limited",
    "tense": "past",
    "dialect": "keep",
    "forbid_meta_language": true,
    "style_config": "style.json"
  },
  "output": {
    "formats": ["md", "docx", "epub", "mobi"],
    "cover": true,
    "page_format": "jpg",
    "cleanup_after_build": true
  }
}
```

| 字段 | 取值 | 说明 |
|---|---|---|
| `adaptation.pov` | `third-limited` / `third-omniscient` / `first` | 视角 |
| `adaptation.tense` | `past` / `present` | 时态 |
| `adaptation.dialect` | `keep` / `light` / `none` | 台词方言保留程度 |
| `adaptation.style_config` | 文件名 | 叙事风格配置路径 |
| `output.formats` | `md` `docx` `epub` `mobi` | 成书格式 |
| `output.page_format` | `jpg` / `png` | 中间页图格式 |
| `work.reading_direction` | `ltr` / `rtl` | 老式港漫用 `rtl` |

**已移除**：`length_per_page`（字数上下限）、`banned_words`（禁用词表）。

---

## 4b. style（叙事风格配置，S-1 产物）

```json
{
  "version": 1,
  "confirmed": true,
  "source": "第1-10话 原图与对白",
  "updated_at": "2026-10-19T14:00:00",
  "dimensions": {
    "rhythm": {"label": "叙事节奏", "summary": "…", "evidence": ["第9话 …"], "status": "已确认"},
    "emotion": {"label": "情绪表达方式", "summary": "…", "evidence": [], "status": "尚未确认"},
    "dialogue": {"label": "对白特征", "summary": "…", "evidence": [], "status": "已确认"},
    "visual": {"label": "画面转译方式", "summary": "…", "evidence": [], "status": "已确认"},
    "reveal": {"label": "信息揭示策略", "summary": "…", "evidence": [], "status": "已确认"},
    "density": {"label": "段落与描写密度", "summary": "…", "evidence": [], "status": "已确认"},
    "signature": {"label": "作品特有的表达习惯", "summary": "…", "evidence": [], "status": "已确认"},
    "forbidden": {"label": "禁止破坏的特征", "summary": "…", "evidence": [], "status": "已确认"}
  }
}
```

`status` ∈ `已确认` / `待确认` / `尚未确认`。资料不足必须标 `尚未确认`，不得凭空假设。

---

## 5. state（outline.json 的一部分，S6.5 的输入）

```json
"state": {
  "year": 3,
  "flashback": false,
  "cast": {
    "陈松": {"age": 62, "status": "alive", "look": "灰白短须，藏青道袍", "place": "正殿"},
    "阿禾": {"age": 14, "status": "alive", "look": "束发，旧棉袍", "place": "山道"}
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `year` | number | 故事内年份**序号**，全书写同一把尺子（主线第 3 年就写 3） |
| `flashback` | bool | 本话是闪回时为 `true`，审计会放行时间倒退 |
| `cast.<名>.age` | number | 故事内年龄；不确定就省略，不要猜 |
| `cast.<名>.status` | enum | `alive` / `dead` / `absent` |
| `cast.<名>.look` | string | 本话实际外观：发型、衣着、疤痕、武器、体型（抓"建模改了"靠它） |
| `cast.<名>.place` | string | 本话所在位置 |

---

## 6. chapter-map.csv（多章合本 PDF 的手工切分表）

PDF 没有书签时，用它告诉 `split_book.py` 章节边界：

```csv
chapter,title,start,end
1,皓光当空,1,29
2,阴阳仙君,30,78
3,千年之谣,79,120
3.5,番外 闲话,121,160
```

- `start` / `end` 是 1 起的页号，**含端点**。
- 允许留空 `chapter`（按顺序编号）；不允许重叠。
- 切分后 `split_book.py` 会输出 `chapter-index.csv` 和"未被覆盖的页"清单。

---

## 7. consistency.json（S6.5 机器报告）

```json
{
  "chapters": 164,
  "issues": [
    {"severity": "error", "kind": "ageing", "chapter": 2,
     "message": "阿禾 年龄从 12 倒退到 11（时间前进 5 年）", "character": "阿禾"},
    {"severity": "warn", "kind": "look", "chapter": 37,
     "message": "阿禾 的外貌与圣经基准差异较大（相似度 0.25）",
     "character": "阿禾", "bible": "束发，旧棉袍", "now": "短发，皮甲"}
  ]
}
```

`kind` 取值：`time` / `ageing` / `death` / `look` / `names` / `state`。
`severity`：`error`（必须改）/ `warn`（需判断）/ `info`（记录即可）。

---

## 8. refs.md / claims.csv（S2.5 联网考据）

`claims.csv`：

```csv
claim,subject,value,source,confidence,note
陈松在第40回死亡,陈松,死亡,https://…,wiki,与第41回回忆不冲突
```

`confidence` 只用三档：`official` / `wiki` / `fan`。优先级：原图 > official > wiki > fan。

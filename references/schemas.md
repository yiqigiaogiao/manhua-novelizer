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
  "uncertain": ["第 12 页一句台词两处模糊"]
}
```

约束：

- `beats` 必须是因果句（"因为…所以…"/"用…压服…"），不能是"他抬手/他说话"的流水账。
- `quotes` 是 S6 的对账依据，**逐字**，5–20 条。
- `continuity` 必填一句话。

---

## 3. qa（S6 产物，每话一个）

```json
{
  "chapter": 143,
  "checks": {
    "quote_coverage": {"pass": true, "value": 0.97, "missing": []},
    "name_whitelist": {"pass": true, "unknown": []},
    "banned_words": {"pass": true, "hits": []},
    "length": {"pass": true, "value": 4820, "range": [3000, 5400]},
    "faithfulness": {"pass": true, "manual": true, "issues": []},
    "continuity": {"pass": true, "issues": []}
  },
  "fixes": ["s2 补回漏掉的台词"],
  "score": 92
}
```

扣分规则：每缺 1 条台词 −3；禁词每处 −2；编造每处 −10；连续性冲突 −5；长度越界 −5。

合格线：`quote_coverage ≥ 0.95`、`banned_words.hits` 为空、`faithfulness.pass = true`、`score ≥ 80`。

---

## 4. config（每项目一个）

```json
{
  "language": "zh",
  "pov": "third-limited",
  "tense": "past",
  "length_per_page": [120, 180],
  "dialect": "keep",
  "banned_words": ["画面", "镜头", "分镜", "这一格", "格子", "读者", "对话框", "旁白框"],
  "output": ["md", "docx"],
  "title_format": "第X回 {title}",
  "scene_break": "◇",
  "reading_direction": "ltr"
}
```

| 字段 | 取值 | 说明 |
|---|---|---|
| `pov` | `third-limited` / `third-omniscient` / `first` | 视角 |
| `tense` | `past` / `present` | 时态 |
| `length_per_page` | `[min, max]` | 一话字数 = 页数 × 区间 |
| `dialect` | `keep` / `light` / `none` | 台词方言保留程度 |
| `reading_direction` | `ltr` / `rtl` | 老式港漫用 `rtl` |

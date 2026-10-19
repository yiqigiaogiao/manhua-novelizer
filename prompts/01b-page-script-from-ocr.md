# S3-alt · 用 OCR 结果整理页脚本（文本模型，零视觉 token）

> 配合 `references/cheap-vision.md` 的 T0/T1 使用。你没有看图，所以**不许编视觉**。

## 输入

- `work/chNNN/ocr.json`：每页的 OCR 行，含文字与归一化 bbox，已按阅读顺序排好
- `work/bible.md`
- 可选：`work/chNNN/pages/thumb/pNNNN.jpg`（400px 缩略图，只用来判断"这一页大概在发生什么"）

## 输出

`work/chNNN/page_script.json`：

```json
{"chapter":1,"pages":[
  {"page":1,"layout":"","panels":[
    {"order":1,"shot":"","angle":"","scene":"","characters":[],
     "visual":"","text":[{"type":"speech","speaker":"unknown","text":"这里是第二开拓局！"}],
     "notes":"bbox 0.62-0.95 / 0.08-0.22"}
  ],"page_summary":"舰内广播"}
]}
```

## 规则

1. **只写 OCR 里有的字**。错字、缺字、乱码：原样保留并在 `notes` 标 `ocr`。
2. **`visual` 留空**，除非看了缩略图且能明确判断（如"舱内，三人"）。不要根据台词反推画面。
3. **`scene` 只在缩略图能确认时填**（室内/舱外/街道），否则留空。
4. **`speaker` 默认 `unknown`**。OCR 不给归属；bible 里有人名、且台词明显在称呼对方时，可谨慎填。
5. **分格**：没有分格检测时，按 OCR 行的 y 间距粗分段落，`layout` 写 `"按行分组，非精确分格"`。
6. 拟声/状声字若 OCR 成乱码，记进 `notes`，不要硬猜。

## 分诊建议

`ocr.json` 里每页有 `coverage`（文字覆盖面积比）：

- `coverage > 0.25` → 对话页，OCR 足够；
- `0.05 < coverage < 0.25` → 对话+少量画面，建议补缩略图；
- `coverage < 0.05` → 很可能是动作页或无对白页，**这一页必须走视觉模型**，OCR 帮不上。

## 交付

写出 `page_script.json` 即可。回报：页数、OCR 行数、其中 `visual` 为空的页数、建议补视觉模型的页号列表。

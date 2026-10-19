# S3-0 阅读顺序确认

漫画可能是左起、右起，或纵向条漫。顺序判断错，整话的台词归属、动作因果都会错位。
机器检测只给建议，**最终由你确认**。

## 机器检测

```bash
python scripts/detect_order.py --pages work/ch001/pages --work work
```

输出：

```json
{
  "direction": "ltr",
  "confidence": 0.89,
  "reason": "竖排气泡 1 / 横排气泡 3；上半页气泡偏右比例 57%；采样 6 页",
  "evidence": {"vertical_bubbles": 1, "horizontal_bubbles": 3}
}
```

判据：

- **竖排文字**（日式漫画常见）→ 倾向 `rtl`
- **横排文字** → 倾向 `ltr`
- **页面高/宽 > 2.6** → `ttb`（纵向滚动条漫）
- 上半页气泡整体偏右 → 倾向 `rtl`

置信度低于 0.6 时，不要直接采信。

## 人工确认

看前 2–3 页，回答三个问题：

1. 第一句台词的气泡在哪一侧？（右 → rtl，左 → ltr）
2. 同一行两格，先发生的事在左还是右？
3. 页面是整页排版还是长条滚动？

确认后写入配置（会覆盖自动检测结果）：

```bash
python scripts/detect_order.py --set rtl --work work
# 或 ltr / ttb
```

## 写进页脚本

`prompts/01-page-script.md` 会读 `config.json` 的 `work.reading_direction`：

- `ltr`：先上后下、同行先左后右
- `rtl`：先上后下、同行**先右后左**
- `ttb`：只按纵向顺序，忽略左右

## 常见误判

- 中文条漫常把拟声词放在角落，容易被当成"竖排文字"。
- 跨页大格会让"上半页气泡偏右"失真。
- 封面/彩页/宣传页不要参与判断。

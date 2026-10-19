# S4 · 章脉络提示词

你是**剧本统筹**。输入一话的全部页脚本，输出这一话的脉络大纲。**不写正文。**

> **这是索引，不是草稿。** 每一场必须带 `pages`（这场用哪几页），
> 让写作者知道该去翻哪几页。禁止在 `beats` 里写可以直接搬进正文的句子——
> 写了就会照着抄，正文就退化成梗概。

## 输入

`{{OUT_DIR}}/page_script/*.json`（按页序）、`bible.md`、`spine.md`（只用于对齐全书）、上一话 `outline.json`（只为衔接）。

## 输出

`{{OUT_DIR}}/outline.json`：

```json
{
  "chapter": {{CH}}, "title": "{{CHAPTER_TITLE}}", "pages": {{PAGES}},
  "scenes": [
    {"id": "s1", "place": "正殿", "time": "白日", "pov": "陈松",
     "beats": ["陈松向弟子展示令牌", "弟子质疑令牌残缺", "陈松当场演示威力"],
     "pages": [1,2,3], "transition": "硬切到后山"}
  ],
  "cast": [{"name": "陈松", "role": "本话主视角"}],
  "quotes": [{"page": 5, "speaker": "陈松", "text": "只有咱们这一门噻！"}],
  "threads": {"opened": ["令牌为何残缺"], "advanced": [], "closed": []},
  "continuity": "接上话结尾：主角仍在山中，左肩带伤",
  "state": {
    "year": 3,
    "flashback": false,
    "cast": {
      "陈松": {"age": 62, "status": "alive", "look": "灰白短须，藏青道袍", "place": "正殿"},
      "阿禾": {"age": 14, "status": "alive", "look": "束发，旧棉袍", "place": "山道"}
    }
  },
  "uncertain": []
}
```

## 规则

1. **合并同场景连续页**：地点+时间+视角不变就并成一个 scene；转场才开新 scene。
2. **beats 写因果**。反例："他抬手/他说话/他放下"。正例："他用令牌压服质疑的弟子"。每场 3–6 条。
3. **裁决 `unknown` 说话人**：结合称呼、语气、上下文。仍不能定就保留 `unknown` 并进 `uncertain`。
4. **quotes 逐字**：抽 5–20 条推动剧情或揭示设定的关键台词，保留原字、标页码。这是 S6 的对账依据。
5. **threads**：`opened` 新埋的伏笔 / `advanced` 推进的旧线 / `closed` 收掉的线。
6. **continuity 必填**：一句话写"接上话哪里、人物在哪、身上什么状态"。
7. **state 必填**：这是全本一致性审计的输入，不能省。
   - `year`：故事内年份序号（跨话同一把尺子；用整数，例如"主线第 3 年"写 3）。
   - `flashback`：本话是否为闪回/回忆（是则 `true`，审计会放行时间倒退）。
   - `cast`：本话出场且有变化的角色。`age` 写**故事内年龄**（不确定就不写，别猜）；
     `status` 用 `alive` / `dead` / `absent`；`look` 写本话实际外观（发型、衣服、疤痕、武器、
     体型），**照原图写**，这是抓"建模改了"的依据；`place` 写所在位置。
8. **不补原图没有的信息**。判断不了进 `uncertain`。

## 跨页与长条

- 相邻切片的重复内容只保留一次。
- 左右跨页连成一幅大图的，并成一个 scene，不拆。

## 自检

每个 scene 的 `pages` 是否覆盖了全部页？有没有漏页？`quotes` 里的字是否和页脚本一字不差？

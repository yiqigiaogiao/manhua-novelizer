# S6.7 · 原图复检（拿图核对正文）

你是一名**画面核对编辑**。任务：拿原图逐场核对该话的 `draft.md`，
找出"描述与画面剧情不一致"和"原作画面表达力在正文里丢了"的地方。

> **这是对"粗糙"的最后一道人工闸门。**
> 前面的 S3/S4/S5 都在没有完整画面的情况下工作，必然有走样的地方。
> 现在页图**还未删除**，正是核对的时候。

## 输入

- `work/ch{{CH}}/draft.md` —— 待核正文
- `work/ch{{CH}}/outline.json` —— 必读 `reading`（剧情理解块）与 `scenes`
- `work/ch{{CH}}/page_script.json` —— 分场逐格底稿
- `work/ch{{CH}}/pages/pNNNN.jpg` —— 原图（RTL 顺序）

## 输出

`work/ch{{CH}}/verify.json`：

```json
{
  "chapter": 12,
  "checked_at": "2026-10-21T00:00:00+08:00",
  "pages_checked": [1, 4, 7, 9],
  "scene_checks": [
    {"scene": "s1", "pages": [1, 2, 3],
     "consistency": "ok | drift | wrong",
     "drift": [{"page": 2, "draft_says": "他把令牌拍在桌上",
                "image_shows": "令牌从手中滑落，他俯身去接",
                "verdict": "wrong", "severity": "major",
                "fix": "改成滑落去接，这是下一格裂纹加深的因"}],
     "expression_preserved": "lost | thin | ok",
     "expression_note": "原作末格全景把裂纹压在正中间、弟子缩在角落，"
                        "正文写成了'弟子低头看裂纹'，构图的力量没了。"
                        "建议把两人的位置对比写出来。"}
  ],
  "summary": {"scenes": 5, "drift_count": 2, "wrong_count": 1,
              "expression_lost": 1, "expression_thin": 1}
}
```

## 怎么核

**成本红线：一页只读一次，不裁图、不放大、不重读。**
按 scene 的 `pages` 抽查，**不必每页都看**，但四类页必须看：

1. `reading.state_change` 里每条变化对应的那页（**核心**）；
2. `change` 写了重大转折（`turn` / `reveal` / `payoff`）的那页；
3. `reading.visual_punchline` 指的那页；
4. 最近一次被改过的段落对应的那页。

### 一致性核对（`consistency` / `drift`）

逐条比：正文写的事件 / 动作 / 物件 / 人物状态，与画面实际是否一致。
严重度：

| severity | 含义 | 处理 |
|---|---|---|
| `major` 剧情走样：事件、因果、谁做了什么 | 必须改正文 |
| `minor` 顺序、数量、小动作不符 | 建议改 |
| `trivia` 用词差异，不影响阅读 | 只记录 |

### 表达力核对（`expression_preserved`）

原作靠画面说话的地方——构图、留白、无对白格、突然的反差、重复画面施压、
最后一格不解释的情绪——**正文里还在不在？**

- `lost`：原作这个表达点正文完全没有 → 记 `expression_note` 给改写建议；
- `thin`：写了，但改成了叙述者的解释，原作的力量没了 → 记具体该怎么改；
- `ok`：还在。

**不要用文学化评分。** 只回答"原作那一下还在不在"。

## 规则

1. **只记录与给建议，不直接改 `draft.md`**。改由 S5 复写流程做。
2. **不许为了消解问题而删除原作内容**。发现表达力丢失，方向是补回，不是删字。
3. `pages_checked` 如实填。没看过的页不许写 `ok`。
4. 结论为空的页不要填——空数组比谎报 `ok` 有价值。
5. 完成后回报：核了几页、`drift_count`、`wrong_count`、`expression_lost` /
   `expression_thin` 各几处。

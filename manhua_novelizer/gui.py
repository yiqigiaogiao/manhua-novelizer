# -*- coding: utf-8 -*-
"""Tkinter 图形界面：不写命令行也能跑完整条流水线。"""
from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import build, config, consistency, manifest, pages, qa, style


class App(tk.Tk):
    def __init__(self, work: str = "work"):
        super().__init__()
        self.title("漫画转小说 · Manhua Novelizer")
        self.geometry("980x680")
        self.work = os.path.abspath(work)
        os.makedirs(self.work, exist_ok=True)
        self.queue: queue.Queue = queue.Queue()
        self._build_ui()
        self.after(120, self._drain)

    # ---------- UI ----------
    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="工作目录").pack(side="left")
        self.work_var = tk.StringVar(value=self.work)
        ttk.Entry(top, textvariable=self.work_var, width=70).pack(side="left", padx=6)
        ttk.Button(top, text="选择", command=self._pick_work).pack(side="left")
        ttk.Button(top, text="初始化", command=self._init).pack(side="left", padx=4)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=6)
        self.pipeline_tab = ttk.Frame(nb, padding=8)
        self.style_tab = ttk.Frame(nb, padding=8)
        nb.add(self.pipeline_tab, text="流水线")
        nb.add(self.style_tab, text="叙事风格配置")
        self._build_pipeline()
        self._build_style()

        self.log = tk.Text(self, height=12, wrap="word")
        self.log.pack(fill="both", expand=False, padx=8, pady=(0, 8))
        self.log.configure(state="disabled")

    def _build_pipeline(self) -> None:
        f = self.pipeline_tab
        row1 = ttk.Frame(f)
        row1.pack(fill="x", pady=4)
        ttk.Button(row1, text="① 建章节清单", command=self._manifest).pack(side="left", padx=3)
        ttk.Button(row1, text="② 拆页（选 PDF）", command=self._pages).pack(side="left", padx=3)
        ttk.Button(row1, text="②b 合本拆章", command=self._split).pack(side="left", padx=3)
        ttk.Button(row1, text="⑤ 单话质检（全部）", command=self._qa_all).pack(side="left", padx=3)

        row2 = ttk.Frame(f)
        row2.pack(fill="x", pady=4)
        ttk.Button(row2, text="⑥ 一致性审计", command=self._audit).pack(side="left", padx=3)
        ttk.Button(row2, text="⑦ 成书（md/docx/epub/mobi）", command=self._build).pack(side="left", padx=3)
        ttk.Button(row2, text="清理中间页图", command=self._clean).pack(side="left", padx=3)
        ttk.Button(row2, text="打开工作目录", command=self._open_work).pack(side="left", padx=3)

        hint = ("流程：清单 → 拆页 → 交给 agent 做风格分析/页脚本/脉络/正文 → 质检 → 审计 → 成书。\n"
                "「叙事风格配置」标签页里生成的 style.json 是所有写作步骤的前置输入。")
        ttk.Label(f, text=hint, foreground="#666").pack(fill="x", pady=(10, 0))

    def _build_style(self) -> None:
        f = self.style_tab
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Button(bar, text="载入", command=self._style_load).pack(side="left", padx=2)
        ttk.Button(bar, text="保存", command=self._style_save).pack(side="left", padx=2)
        ttk.Button(bar, text="确认配置", command=self._style_confirm).pack(side="left", padx=2)
        ttk.Button(bar, text="导出 style.md", command=self._style_render).pack(side="left", padx=2)
        ttk.Label(bar, text="  八个维度：节奏/情绪/对白/画面转译/信息揭示/描写密度/特有习惯/禁止破坏").pack(side="left")

        self.style_text = tk.Text(f, wrap="word")
        self.style_text.pack(fill="both", expand=True, pady=6)
        self._style_load()

    # ---------- helpers ----------
    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "json":
                    self._log(json.dumps(payload, ensure_ascii=False, indent=1))
        except queue.Empty:
            pass
        self.after(120, self._drain)

    def _run_bg(self, fn, label: str) -> None:
        def runner():
            self.queue.put(("log", f"▶ {label} 开始…"))
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("log", f"✗ {label} 失败：{exc}"))
            else:
                self.queue.put(("log", f"✓ {label} 完成"))
        threading.Thread(target=runner, daemon=True).start()

    def _pick_work(self) -> None:
        path = filedialog.askdirectory(initialdir=self.work)
        if path:
            self.work = path
            self.work_var.set(path)

    def _init(self) -> None:
        self.work = self.work_var.get()
        config.init_work(self.work)
        style.save_style(self.work, style.load_style(self.work), snapshot=False)
        self._log(f"已初始化：{self.work}")
        self._style_load()

    def _open_work(self) -> None:
        os.startfile(self.work)  # noqa: S606

    # ---------- pipeline ----------
    def _manifest(self) -> None:
        pdf_dir = filedialog.askdirectory(title="选择 PDF 目录")
        if not pdf_dir:
            return
        out = os.path.join(self.work, "manifest.csv")

        def job():
            self.queue.put(("json", manifest.run(pdf_dir, out)))
        self._run_bg(job, "建章节清单")

    def _pages(self) -> None:
        pdf = filedialog.askopenfilename(title="选择 PDF", filetypes=[("PDF", "*.pdf")])
        if not pdf:
            return
        out = filedialog.askdirectory(title="页图输出目录") or os.path.join(self.work, "ch001", "pages")

        def job():
            result = pages.process(pdf, out)
            self.queue.put(("json", {"pages": len(result["pages"]), "out": out}))
        self._run_bg(job, "拆页")

    def _split(self) -> None:
        pdf = filedialog.askopenfilename(title="选择合本 PDF", filetypes=[("PDF", "*.pdf")])
        if not pdf:
            return
        out = os.path.join(self.work, "chapters")

        def job():
            self.queue.put(("json", split.run(pdf, out)))
        self._run_bg(job, "合本拆章")

    def _qa_all(self) -> None:
        def job():
            import glob
            rows = []
            for outline in sorted(glob.glob(os.path.join(self.work, "ch*", "outline.json"))):
                folder = os.path.dirname(outline)
                draft = os.path.join(folder, "draft.md")
                if not os.path.isfile(draft):
                    continue
                qa_path = os.path.join(folder, "qa.json")
                result = qa.run(draft, outline, os.path.join(self.work, "bible.md"), qa_path)
                rows.append({"ch": result.get("chapter"),
                             "coverage": result["checks"]["quote_coverage"]["value"],
                             "words": result["words"]})
                self.queue.put(("json", rows[-1]))
            self.queue.put(("json", {"checked": len(rows)}))
        self._run_bg(job, "单话质检")

    def _audit(self) -> None:
        def job():
            result = consistency.run(self.work, os.path.join(self.work, "bible.md"),
                                     os.path.join(self.work, "audit", "consistency.md"),
                                     os.path.join(self.work, "audit", "consistency.json"))
            result.pop("issues", None)
            result.pop("markdown", None)
            self.queue.put(("json", result))
        self._run_bg(job, "一致性审计")

    def _build(self) -> None:
        title = tk.simpledialog.askstring("书名", "输入书名", initialvalue="漫画小说化") if hasattr(tk, "simpledialog") else "漫画小说化"
        out = os.path.join(self.work, "build")

        def job():
            cfg = config.load_config(self.work)
            formats = (cfg.get("output") or {}).get("formats") or ["md", "docx", "epub", "mobi"]
            result = build.run(self.work, out, title or "漫画小说化", formats)
            self.queue.put(("json", result))
        self._run_bg(job, "成书")

    def _clean(self) -> None:
        if not messagebox.askyesno("确认", "将删除 work 下所有 jpg/png 中间页图，正文与 JSON 保留。继续？"):
            return

        def job():
            self.queue.put(("json", pages.cleanup(self.work)))
        self._run_bg(job, "清理页图")

    # ---------- style ----------
    def _style_load(self) -> None:
        st = style.load_style(self.work)
        self.style_text.delete("1.0", "end")
        self.style_text.insert("1.0", json.dumps(st, ensure_ascii=False, indent=2))

    def _style_save(self) -> None:
        try:
            data = json.loads(self.style_text.get("1.0", "end"))
        except json.JSONDecodeError as exc:
            messagebox.showerror("JSON 错误", str(exc))
            return
        style.save_style(self.work, data)
        self._log("风格配置已保存（旧版本已快照到 style_history/）")

    def _style_confirm(self) -> None:
        st = style.load_style(self.work)
        st["confirmed"] = True
        style.save_style(self.work, st)
        self._log("风格配置已确认；后续写作将读取此版本")

    def _style_render(self) -> None:
        st = style.load_style(self.work)
        out = os.path.join(self.work, "style.md")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(style.render_markdown(st))
        self._log(f"已导出：{out}")


def main(work: str = "work") -> None:
    App(work).mainloop()


if __name__ == "__main__":
    main()

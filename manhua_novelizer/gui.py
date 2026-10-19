# -*- coding: utf-8 -*-
"""图形界面：深色桌面风格，左侧导航 + 卡片式流水线 + 日志控制台。"""
from __future__ import annotations

import glob
import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from . import __version__, build, config, consistency, manifest, pages, qa, reading_order, split, style

# ---------------- 主题 ----------------
BG = "#0f1115"
SIDEBAR = "#12151b"
CARD = "#171a21"
CARD_HOVER = "#1c2029"
INPUT = "#1e222b"
BORDER = "#262b36"
TEXT = "#e6e8ee"
MUTED = "#8b93a7"
ACCENT = "#4f7cff"
ACCENT_DIM = "#2b3a66"
OK = "#3ddc97"
WARN = "#f0b94a"
ERR = "#ff6b6b"

FONT = "Microsoft YaHei UI"
MONO = "Consolas"


class Card(tk.Frame):
    """一张步骤卡片：编号 + 标题 + 说明 + 按钮 + 状态。"""

    def __init__(self, master, index: str, title: str, desc: str, action, button="执行"):
        super().__init__(master, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        self.action = action
        inner = tk.Frame(self, bg=CARD)
        inner.pack(fill="both", expand=True, padx=14, pady=11)

        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text=index, bg=ACCENT_DIM, fg="#cfe0ff", font=(MONO, 10, "bold"),
                 width=3, pady=2).pack(side="left")
        tk.Label(head, text=title, bg=CARD, fg=TEXT, font=(FONT, 12, "bold")).pack(side="left", padx=10)

        tk.Label(inner, text=desc, bg=CARD, fg=MUTED, font=(FONT, 9), justify="left",
                 wraplength=320, anchor="w").pack(fill="x", pady=(6, 8))

        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x")
        self.btn = tk.Button(row, text=button, command=self._click, bg=ACCENT, fg="white",
                             activebackground="#6b90ff", activeforeground="white",
                             relief="flat", bd=0, padx=14, pady=4, cursor="hand2",
                             font=(FONT, 9))
        self.btn.pack(side="left")
        self.status = tk.Label(row, text="", bg=CARD, fg=MUTED, font=(FONT, 9))
        self.status.pack(side="left", padx=10)

    def _click(self):
        self.action(self)

    def set_status(self, text: str, color: str = MUTED):
        self.status.configure(text=text, fg=color)


class App(tk.Tk):
    def __init__(self, work: str = "work"):
        super().__init__()
        self._dpi()
        self.title("漫画转小说 · Manhua Novelizer")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(1240, sw - 120), min(860, sh - 140)
        self.geometry(f"{w}x{h}+{max(20, (sw - w) // 2)}+24")
        self.minsize(1000, 680)
        self.configure(bg=BG)
        self.work = os.path.abspath(work)
        os.makedirs(self.work, exist_ok=True)
        self.queue: queue.Queue = queue.Queue()
        self.cards: dict[str, Card] = {}

        self._layout()
        self._show_page("pipeline")
        self.after(100, self._drain)

    # ---------- 基础 ----------
    def _dpi(self):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    def _layout(self):
        # 顶栏
        top = tk.Frame(self, bg=SIDEBAR, height=58)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)
        tk.Label(top, text="  Mn", bg=ACCENT, fg="white", font=(MONO, 13, "bold"),
                 padx=6, pady=3).pack(side="left", padx=(16, 8), pady=14)
        tk.Label(top, text="漫画转小说", bg=SIDEBAR, fg=TEXT, font=(FONT, 13, "bold")).pack(side="left")
        tk.Label(top, text=f"v{__version__}", bg=SIDEBAR, fg=MUTED, font=(MONO, 9)).pack(side="left", padx=8)

        right = tk.Frame(top, bg=SIDEBAR)
        right.pack(side="right", padx=16)
        self.work_label = tk.Label(right, text=self._short(self.work), bg=SIDEBAR, fg=MUTED, font=(MONO, 9))
        self.work_label.pack(side="left", padx=8)
        self._ghost(right, "选择目录", self._pick_work).pack(side="left", padx=4)
        self._ghost(right, "初始化", self._init).pack(side="left", padx=4)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # 侧栏
        side = tk.Frame(body, bg=SIDEBAR, width=196)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        self.nav_buttons = {}
        for key, label in (("pipeline", "流水线"), ("style", "叙事风格"), ("about", "关于")):
            b = tk.Button(side, text="  " + label, anchor="w", bg=SIDEBAR, fg=MUTED,
                          activebackground=CARD, activeforeground=TEXT, relief="flat", bd=0,
                          padx=18, pady=12, cursor="hand2", font=(FONT, 10),
                          command=lambda k=key: self._show_page(k))
            b.pack(fill="x")
            self.nav_buttons[key] = b
        tk.Label(side, text="漫画 → 分镜 → 小说", bg=SIDEBAR, fg="#4a5060",
                 font=(FONT, 8)).pack(side="bottom", pady=16)

        self.pages = {}
        self.pages["pipeline"] = self._build_pipeline(body)
        self.pages["style"] = self._build_style(body)
        self.pages["about"] = self._build_about(body)

        # 日志
        log_wrap = tk.Frame(self, bg=BG)
        log_wrap.pack(fill="x", side="bottom")
        head = tk.Frame(log_wrap, bg=BG)
        head.pack(fill="x", padx=16, pady=(6, 2))
        tk.Label(head, text="运行日志", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left")
        tk.Button(head, text="清空", command=self._clear_log, bg=BG, fg=MUTED,
                  activebackground=BG, activeforeground=TEXT, relief="flat", bd=0,
                  cursor="hand2", font=(FONT, 8)).pack(side="right")
        self.log = tk.Text(log_wrap, height=3, bg="#0b0d11", fg="#c9d1e0", insertbackground=TEXT,
                           relief="flat", bd=0, padx=12, pady=8, font=(MONO, 9), wrap="word")
        self.log.pack(fill="x", padx=16, pady=(0, 10))
        self.log.tag_configure("ok", foreground=OK)
        self.log.tag_configure("err", foreground=ERR)
        self.log.tag_configure("dim", foreground="#6b7385")
        self.log.configure(state="disabled")

    def _ghost(self, master, text, command):
        return tk.Button(master, text=text, command=command, bg=CARD, fg=TEXT,
                         activebackground=CARD_HOVER, activeforeground=TEXT, relief="flat",
                         bd=0, padx=12, pady=4, cursor="hand2", font=(FONT, 9))

    # ---------- 页面 ----------
    def _show_page(self, key: str):
        for name, frame in self.pages.items():
            frame.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        for name, btn in self.nav_buttons.items():
            active = name == key
            btn.configure(bg=CARD if active else SIDEBAR,
                          fg=TEXT if active else MUTED,
                          font=(FONT, 10, "bold") if active else (FONT, 10))

    def _build_pipeline(self, parent) -> tk.Frame:
        outer = tk.Frame(parent, bg=BG)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scroll = tk.Frame(canvas, bg=BG)
        window = canvas.create_window((0, 0), window=scroll, anchor="nw")
        scroll.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))

        def _wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        bar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview,
                           bg=BG, troughcolor=BG, bd=0, width=10, relief="flat")
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        tk.Label(scroll, text="流水线", bg=BG, fg=TEXT, font=(FONT, 17, "bold")).pack(anchor="w", padx=24, pady=(14, 2))
        tk.Label(scroll, text="从 PDF 到成书，按顺序点；写作步骤交给 agent，读 SKILL.md 与 prompts/",
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w", padx=24, pady=(0, 10))

        grid = tk.Frame(scroll, bg=BG)
        grid.pack(fill="x", padx=18)
        items = [
            ("01", "建章节清单", "扫描 PDF 目录，识别话号、上/中/下、番外与非正文", self._manifest, "选择目录"),
            ("02", "拆页", "抽原生图像、长条切片、低清放大；支持 jpg / png", self._pages, "选择 PDF"),
            ("03", "合本拆章", "一个 PDF 装几十话时，按书签或页表切开", self._split, "选择 PDF"),
            ("04", "阅读顺序", "自动判断左起 / 右起 / 条漫，可手动覆盖", self._order, "检测"),
            ("05", "单话质检", "台词是否逐字落地；不查字数、不查禁词", self._qa_all, "全部质检"),
            ("06", "一致性审计", "年龄、外观、生死、时间线跨话核对", self._audit, "开始审计"),
            ("07", "成书", "md / docx / epub / mobi + PNG 封面", self._build, "导出"),
            ("08", "清理页图", "删除中间 jpg/png，正文与 JSON 保留", self._clean, "清理"),
        ]
        for i, (idx, title, desc, fn, label) in enumerate(items):
            card = Card(grid, idx, title, desc, fn, label)
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=4)
            self.cards[idx] = card
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        bar = tk.Frame(scroll, bg=BG)
        bar.pack(fill="x", padx=24, pady=12)
        self.order_hint = tk.Label(bar, text="阅读顺序：未检测", bg=BG, fg=MUTED, font=(FONT, 9))
        self.order_hint.pack(side="left")
        return outer

    def _build_style(self, parent) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG)
        tk.Label(frame, text="叙事风格配置", bg=BG, fg=TEXT, font=(FONT, 18, "bold")).pack(anchor="w", padx=24, pady=(20, 2))
        tk.Label(frame, text="八维度；确认后才批量写作。每次保存会把旧版快照到 style_history/",
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w", padx=24, pady=(0, 12))

        body = tk.Frame(frame, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        left = tk.Frame(body, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="y", padx=(0, 12))
        tk.Label(left, text="维度状态", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(anchor="w", padx=14, pady=(12, 6))
        self.dim_labels = {}
        for key, label in style.DIMENSIONS:
            row = tk.Frame(left, bg=CARD)
            row.pack(fill="x", padx=14, pady=3)
            dot = tk.Label(row, text="●", bg=CARD, fg="#3a4150", font=(FONT, 9))
            dot.pack(side="left")
            tk.Label(row, text=label, bg=CARD, fg=TEXT, font=(FONT, 9)).pack(side="left", padx=6)
            self.dim_labels[key] = dot
        tk.Frame(left, bg=CARD, height=8).pack()

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self.style_text = tk.Text(right, bg="#0b0d11", fg="#c9d1e0", insertbackground=TEXT,
                                  relief="flat", bd=0, padx=12, pady=10, font=(MONO, 9), wrap="none")
        self.style_text.pack(fill="both", expand=True)

        bar = tk.Frame(right, bg=BG)
        bar.pack(fill="x", pady=8)
        for text, cmd in (("载入", self._style_load), ("保存", self._style_save),
                          ("确认配置", self._style_confirm), ("导出 style.md", self._style_render)):
            self._ghost(bar, text, cmd).pack(side="left", padx=(0, 6))

        self._style_load()
        return frame

    def _build_about(self, parent) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG)
        tk.Label(frame, text="关于", bg=BG, fg=TEXT, font=(FONT, 18, "bold")).pack(anchor="w", padx=24, pady=(20, 10))
        text = ("漫画转小说工具（Manhua Novelizer）\n\n"
                "把只有图、没有文本层的漫画 PDF，转成分镜 JSON，再按原作叙事风格写成小说，\n"
                "最后做全本一致性审计并导出 md / docx / epub / mobi。\n\n"
                "写作本身由 agent 按 SKILL.md 与 prompts/ 执行；本程序负责拆页、质检、审计、成书与清理。\n\n"
                "不设字数上下限，不设禁用词表；判断标准是是否忠实于原作的事件、人物与叙事效果。")
        tk.Label(frame, text=text, bg=BG, fg=MUTED, justify="left", font=(FONT, 10)).pack(anchor="w", padx=24)
        return frame

    # ---------- 日志 ----------
    def _log(self, text: str, tag: str | None = None):
        self.log.configure(state="normal")
        stamp = time.strftime("%H:%M:%S")
        self.log.insert("end", f"[{stamp}] ", "dim")
        self.log.insert("end", text + "\n", tag or "")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _drain(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "ok":
                    self._log(payload, "ok")
                elif kind == "err":
                    self._log(payload, "err")
                elif kind == "json":
                    self._log(json.dumps(payload, ensure_ascii=False))
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _run(self, card: Card | None, label: str, fn):
        if card:
            card.set_status("运行中…", WARN)
            card.btn.configure(state="disabled")

        def runner():
            try:
                result = fn()
                if card:
                    self.after(0, lambda: card.set_status("完成", OK))
                if result is not None:
                    self.queue.put(("ok", f"{label} 完成"))
            except Exception as exc:  # noqa: BLE001
                if card:
                    self.after(0, lambda: card.set_status("失败", ERR))
                self.queue.put(("err", f"{label} 失败：{exc}"))
            finally:
                if card:
                    self.after(0, lambda: card.btn.configure(state="normal"))
        threading.Thread(target=runner, daemon=True).start()

    # ---------- 动作 ----------
    def _pick_work(self):
        path = filedialog.askdirectory(initialdir=self.work)
        if path:
            self.work = path
            self.work_label.configure(text=self._short(path))
            self._log(f"工作目录切换为 {path}")

    def _init(self):
        config.init_work(self.work)
        style.save_style(self.work, style.load_style(self.work), snapshot=False)
        self._log("工作目录已初始化")
        self._style_load()

    def _manifest(self, card):
        d = filedialog.askdirectory(title="选择 PDF 目录")
        if not d:
            return
        out = os.path.join(self.work, "manifest.csv")
        self._run(card, "建清单", lambda: manifest.run(d, out))

    def _pages(self, card):
        pdf = filedialog.askopenfilename(title="选择 PDF", filetypes=[("PDF", "*.pdf")])
        if not pdf:
            return
        out = os.path.join(self.work, "ch001", "pages")
        self._log(f"拆页 → {out}")
        self._run(card, "拆页", lambda: pages.process(pdf, out))

    def _split(self, card):
        pdf = filedialog.askopenfilename(title="选择合本 PDF", filetypes=[("PDF", "*.pdf")])
        if not pdf:
            return
        out = os.path.join(self.work, "chapters")
        self._run(card, "合本拆章", lambda: split.run(pdf, out))

    def _order(self, card):
        folder = os.path.join(self.work, "ch001", "pages")
        if not os.path.isdir(folder):
            d = filedialog.askdirectory(title="选择页图目录")
            if not d:
                return
            folder = d

        def job():
            result = reading_order.detect(folder)
            reading_order.apply(self.work, result["direction"])
            self.after(0, lambda: self.order_hint.configure(
                text=f"阅读顺序：{result['direction'].upper()}（置信度 {result['confidence']:.0%}）"))
            return result
        self._run(card, "阅读顺序检测", job)

    def _qa_all(self, card):
        def job():
            rows = []
            for outline in sorted(glob.glob(os.path.join(self.work, "ch*", "outline.json"))):
                draft = os.path.join(os.path.dirname(outline), "draft.md")
                if not os.path.isfile(draft):
                    continue
                res = qa.run(draft, outline, os.path.join(self.work, "bible.md"),
                             os.path.join(os.path.dirname(outline), "qa.json"))
                rows.append({"ch": res.get("chapter"),
                             "coverage": res["checks"]["quote_coverage"]["value"]})
                self.queue.put(("json", rows[-1]))
            self.queue.put(("ok", f"共质检 {len(rows)} 话"))
            return rows
        self._run(card, "单话质检", job)

    def _audit(self, card):
        def job():
            res = consistency.run(self.work, os.path.join(self.work, "bible.md"),
                                  os.path.join(self.work, "audit", "consistency.md"),
                                  os.path.join(self.work, "audit", "consistency.json"))
            res.pop("issues", None)
            res.pop("markdown", None)
            return res
        self._run(card, "一致性审计", job)

    def _build(self, card):
        out = os.path.join(self.work, "build")

        def job():
            cfg = config.load_config(self.work)
            formats = (cfg.get("output") or {}).get("formats") or ["md", "docx", "epub", "mobi"]
            title = os.path.basename(self.work.rstrip("\\/")) or "漫画小说化"
            return build.run(self.work, out, title, formats)
        self._run(card, "成书", job)

    def _clean(self, card):
        if not messagebox.askyesno("确认", "删除工作目录下所有 jpg/png 中间页图？正文与 JSON 会保留。"):
            return
        self._run(card, "清理页图", lambda: pages.cleanup(self.work))

    # ---------- 风格 ----------
    def _style_load(self):
        st = style.load_style(self.work)
        self.style_text.delete("1.0", "end")
        self.style_text.insert("1.0", json.dumps(st, ensure_ascii=False, indent=2))
        for key, dot in getattr(self, "dim_labels", {}).items():
            item = st["dimensions"].get(key) or {}
            filled = bool(item.get("summary")) and item.get("status") != "尚未确认"
            dot.configure(fg=OK if filled else "#3a4150")

    def _style_save(self):
        try:
            data = json.loads(self.style_text.get("1.0", "end"))
        except json.JSONDecodeError as exc:
            messagebox.showerror("JSON 错误", str(exc))
            return
        style.save_style(self.work, data)
        self._log("风格配置已保存（旧版本已快照）", "ok")
        self._style_load()

    def _style_confirm(self):
        st = style.load_style(self.work)
        st["confirmed"] = True
        style.save_style(self.work, st)
        self._log("风格配置已确认，后续写作将读取此版本", "ok")

    def _style_render(self):
        st = style.load_style(self.work)
        out = os.path.join(self.work, "style.md")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(style.render_markdown(st))
        self._log(f"已导出 {out}", "ok")

    @staticmethod
    def _short(path: str, limit: int = 46) -> str:
        return path if len(path) <= limit else "…" + path[-(limit - 1):]


def main(work: str = "work") -> None:
    App(work).mainloop()


if __name__ == "__main__":
    main()

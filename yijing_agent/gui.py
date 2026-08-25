"""图形界面（Tkinter，Python 标准库，无额外依赖）。

    python -m yijing_agent.gui
打包版为 yijing-agent-gui.exe（PyInstaller --windowed）。

界面只做输入输出与线程调度；起卦/排盘/选文/结论走 service 门面，
大模型解读与追问在工作线程执行，结果经队列回主线程刷新。
"""

import calendar
import json
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk

from . import config, lunar, service, topic
from .llm import InterpreterError
from .trigrams import ZHI

_TITLE = "算命 Agent —— 有典可依、可复现（卦断事，盘论人）"
_METHODS = {"时间起卦": "time", "铜钱法": "coin", "姓名字占": "zi"}
_SHICHEN_CHOICES = ["未知"] + [z + "时" for z in ZHI]
# 出生年份下拉范围：今年（北京时间）起倒排至 1920（cnlunar 支持下限之内）
_YEAR_CHOICES = [""] + [str(y) for y in range(lunar.now_beijing().year, 1919, -1)]
_MONTH_CHOICES = [""] + [str(m) for m in range(1, 13)]


def _parse_birth(year, month, day, shichen, gender):
    """下拉选值 → (datetime, gender)，或 None（全部留空）。填而不全抛 ValueError。"""
    if not (year or month or day) and shichen == "未知" and not gender:
        return None
    if not (year and month and day) or shichen == "未知" or not gender:
        raise ValueError("紫微排盘需出生年、月、日、时辰、性别五项齐全；"
                         "时辰未知则无法排盘（可全部留空，改用易经事引擎）")
    hour = ZHI.index(shichen[0]) * 2
    try:
        return datetime(int(year), int(month), int(day), hour), gender
    except ValueError:
        raise ValueError(f"公历中无此日期：{year}年{month}月{day}日") from None


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=8)
        self.root = root
        root.title(_TITLE)
        root.geometry("980x720")
        self.session = None
        self._q = queue.Queue()
        self._busy = False
        self._run_token = None    # 本次起卦标识：旧线程结果不入新一卦
        self._build()
        self.after(100, self._poll)

    # ── 界面搭建 ────────────────────────────────────────────────────

    def _build(self):
        self.pack(fill="both", expand=True)

        row1 = ttk.Frame(self)
        row1.pack(fill="x")
        ttk.Label(row1, text="所问之事：").pack(side="left")
        self.question = ttk.Entry(row1)
        self.question.pack(side="left", fill="x", expand=True, padx=4)
        self.question.bind("<Return>", lambda e: self.run())
        self.topic_box = ttk.Combobox(
            row1, values=["自动判类"] + [n for _k, n in topic.CATEGORIES],
            width=8, state="readonly")
        self.topic_box.current(0)
        self.topic_box.pack(side="left", padx=(4, 0))
        self.method = ttk.Combobox(row1, values=list(_METHODS), width=8,
                                   state="readonly")
        self.method.current(0)
        self.method.pack(side="left", padx=4)
        self.method.bind("<<ComboboxSelected>>", self._method_changed)
        ttk.Label(row1, text="之字：").pack(side="left")
        self.zi_entry = ttk.Entry(row1, width=8)
        self.zi_entry.configure(state="disabled")   # 仅字占用（如姓名）
        self.zi_entry.pack(side="left", padx=(0, 4))
        self.run_btn = ttk.Button(row1, text="起卦 / 排盘", command=self.run)
        self.run_btn.pack(side="left")

        row2 = ttk.Frame(self)
        row2.pack(fill="x", pady=(6, 0))
        ttk.Label(row2, text="生辰（公历；命理类排盘、问事时合参用，可留空）：").pack(side="left")
        self.birth_y = ttk.Combobox(row2, values=_YEAR_CHOICES, width=6,
                                    state="readonly")
        self.birth_y.current(0)
        self.birth_y.pack(side="left")
        ttk.Label(row2, text="年").pack(side="left")
        self.birth_m = ttk.Combobox(row2, values=_MONTH_CHOICES, width=3,
                                    state="readonly")
        self.birth_m.current(0)
        self.birth_m.pack(side="left")
        ttk.Label(row2, text="月").pack(side="left")
        self.birth_d = ttk.Combobox(row2, values=self._day_choices(), width=3,
                                    state="readonly")
        self.birth_d.current(0)
        self.birth_d.pack(side="left")
        ttk.Label(row2, text="日").pack(side="left")
        self.birth_y.bind("<<ComboboxSelected>>", self._update_days)
        self.birth_m.bind("<<ComboboxSelected>>", self._update_days)
        ttk.Label(row2, text="　时辰：").pack(side="left")
        self.shichen = ttk.Combobox(row2, values=_SHICHEN_CHOICES, width=6,
                                    state="readonly")
        self.shichen.current(0)
        self.shichen.pack(side="left")
        ttk.Label(row2, text="　性别：").pack(side="left")
        self.gender = ttk.Combobox(row2, values=["", "男", "女"], width=4,
                                   state="readonly")
        self.gender.current(0)
        self.gender.pack(side="left")
        self.both_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="卦盘并占（命理问＋生辰时两断并陈）",
                        variable=self.both_var).pack(side="left", padx=(10, 0))
        ttk.Button(row2, text="设置（API Key）…",
                   command=self.open_settings).pack(side="right")

        self.out = scrolledtext.ScrolledText(
            self, wrap="none", state="disabled",
            font=("SimSun", 12), height=28)
        self.out.pack(fill="both", expand=True, pady=6)
        xbar = ttk.Scrollbar(self, orient="horizontal", command=self.out.xview)
        self.out.configure(xscrollcommand=xbar.set)
        xbar.pack(fill="x")

        row3 = ttk.Frame(self)
        row3.pack(fill="x", pady=(6, 0))
        ttk.Label(row3, text="追问：").pack(side="left")
        self.fu_entry = ttk.Entry(row3, state="disabled")
        self.fu_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.fu_entry.bind("<Return>", lambda e: self.ask_followup())
        self.fu_btn = ttk.Button(row3, text="追问", command=self.ask_followup,
                                 state="disabled")
        self.fu_btn.pack(side="left")

        self.status = ttk.Label(self, text="※ " + service.DISCLAIMER,
                                foreground="#666666")
        self.status.pack(fill="x", pady=(4, 0))

    def _day_choices(self):
        """当前所选年、月下的合法日数；年或月未选时给 1–31。"""
        y, m = self.birth_y.get(), self.birth_m.get()
        n = calendar.monthrange(int(y), int(m))[1] if y and m else 31
        return [""] + [str(d) for d in range(1, n + 1)]

    def _update_days(self, _event=None):
        days = self._day_choices()
        cur = self.birth_d.get()
        self.birth_d.configure(values=days)
        if cur not in days:            # 如 31 日遇小月：清空令用户重选
            self.birth_d.set("")

    def _method_changed(self, _event=None):
        on = _METHODS[self.method.get()] == "zi"
        self.zi_entry.configure(state="normal" if on else "disabled")

    # ── 输出辅助 ────────────────────────────────────────────────────

    def _clear(self):
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.configure(state="disabled")

    def _append(self, text):
        self.out.configure(state="normal")
        self.out.insert("end", text + "\n")
        self.out.see("end")
        self.out.configure(state="disabled")

    def _set_status(self, text):
        self.status.configure(text=text)

    def _set_busy(self, busy):
        self._busy = busy
        self.run_btn.configure(state="disabled" if busy else "normal")

    def _enable_followup(self, on):
        state = "normal" if on else "disabled"
        self.fu_entry.configure(state=state)
        self.fu_btn.configure(state=state)

    # ── 主流程 ──────────────────────────────────────────────────────

    def run(self):
        if self._busy:
            return
        question = self.question.get().strip()
        if not question:
            messagebox.showinfo(_TITLE, "请先输入所问之事。")
            return
        try:
            birth = _parse_birth(self.birth_y.get(), self.birth_m.get(),
                                 self.birth_d.get(), self.shichen.get(),
                                 self.gender.get())
        except ValueError as e:
            messagebox.showwarning(_TITLE, str(e))
            return
        method = _METHODS[self.method.get()]
        chars = self.zi_entry.get().strip() if method == "zi" else ""
        if method == "zi" and not chars:
            messagebox.showinfo(_TITLE, "字占请输入所占之字（两三字，如姓名）。")
            return
        chosen = self.topic_box.get()
        override = {n: k for k, n in topic.CATEGORIES}.get(chosen)
        self._clear()
        self._enable_followup(False)
        self.session = None
        cfg = config.load()
        self._run_token = token = object()
        self._set_busy(True)
        self._set_status("推演中（判类·起卦/排盘·选文）……")
        threading.Thread(
            target=self._prepare_worker,
            args=(token, question, method, chars, birth, override, cfg,
                  self.both_var.get()),
            daemon=True).start()

    def _prepare_worker(self, token, question, method, chars, birth, override,
                        cfg, both):
        """判类（规则→占者判类）与全部确定性步骤在工作线程完成，不卡界面。"""
        try:
            tp = service.resolve_topic(
                question, cfg=cfg if cfg["api_key"] else None,
                override=override)
            session = service.prepare(
                question, method=method, chars=chars,
                birth_dt=birth[0] if birth else None,
                gender=birth[1] if birth else None, tp=tp, both=both)
            self._q.put(("prepared", token, session, cfg))
        except service.RefusalError as e:
            self._q.put(("refused", token, str(e)))
        except ValueError as e:                   # 字占之字不合法等，如实回显
            self._q.put(("refused", token, str(e)))
        except Exception as e:                    # 判类网络异常等不砸界面
            self._q.put(("refused", token, f"出错：{e}"))

    def _interpret_worker(self, session, cfg):
        try:
            text, attempts = session.interpret(cfg)
            self._q.put(("interp_ok", session, text, attempts, cfg["model"]))
        except InterpreterError as e:
            detail = "\n".join(f"  - {err}" for err in e.errors)
            self._q.put(("interp_err", session,
                         f"〔解读不可用〕{e}\n{detail}".rstrip()))
        except Exception as e:                    # 网络等异常不砸界面
            self._q.put(("interp_err", session, f"〔解读不可用〕{e}"))

    def _finish_output(self):
        if self.session is not None:
            self._append("")
            self._append(self.session.repro_text())
            self._append("")
            self._append("※ " + service.DISCLAIMER)

    # ── 追问 ────────────────────────────────────────────────────────

    def ask_followup(self):
        if self._busy or self.session is None:
            return
        ask = self.fu_entry.get().strip()
        if not ask:
            return
        cfg = config.load()
        self.fu_entry.delete(0, "end")
        self._append(f"追问：{ask}")
        self._set_busy(True)
        self._enable_followup(False)
        self._set_status("追问回答生成中（引文将逐字校验）……")
        threading.Thread(target=self._followup_worker,
                         args=(self.session, cfg, ask), daemon=True).start()

    def _followup_worker(self, session, cfg, ask):
        try:
            text = session.followup(cfg, ask)
            self._q.put(("fu_ok", session, text))
        except service.RefusalError as e:
            self._q.put(("fu_ok", session, str(e)))
        except InterpreterError as e:
            detail = "\n".join(f"  - {err}" for err in e.errors)
            self._q.put(("fu_err", session,
                         f"〔追问回答不可用〕{e}\n{detail}".rstrip()))
        except Exception as e:
            self._q.put(("fu_err", session, f"〔追问回答不可用〕{e}"))

    # ── 线程结果回收 ────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                msg = self._q.get_nowait()
                kind = msg[0]
                if kind in ("prepared", "refused"):
                    if msg[1] is not self._run_token:   # 已开新一卦
                        continue
                    if kind == "refused":
                        self._append(msg[2])
                        self._set_busy(False)
                        self._set_status("※ " + service.DISCLAIMER)
                        continue
                    _, _, session, cfg = msg
                    self.session = session
                    self._append(session.body_text())
                    self._append("")
                    if not cfg["api_key"]:
                        self._append("（未配置 OpenRouter API Key：点右上「设置」"
                                     "填入后可获得占断与讲释。当前为仅原文与"
                                     "定例的输出。）")
                        self._finish_output()
                        self._set_busy(False)
                        self._set_status("※ " + service.DISCLAIMER)
                        continue
                    self._set_status(f"占断生成中（{cfg['model']}，"
                                     "引文将逐字校验）……")
                    threading.Thread(target=self._interpret_worker,
                                     args=(session, cfg), daemon=True).start()
                    continue
                session = msg[1]
                if session is not self.session:   # 已开新一卦，丢弃旧结果
                    continue
                if kind == "interp_ok":
                    _, _, text, attempts, model = msg
                    self._append(text)     # 含占断存证（模型、次数、SHA-256）
                    self._finish_output()
                    self._enable_followup(True)
                elif kind == "interp_err":
                    self._append(msg[2])
                    self._append("已降级为仅原文与结论的输出。")
                    self._finish_output()
                elif kind == "fu_ok":
                    self._append(msg[2])
                    self._append("")
                    self._enable_followup(True)
                elif kind == "fu_err":
                    self._append(msg[2])
                    self._enable_followup(True)
                self._set_busy(False)
                self._set_status("※ " + service.DISCLAIMER)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    # ── 设置对话框 ──────────────────────────────────────────────────

    def open_settings(self):
        path = config.default_path()
        current = dict(config.TEMPLATE)
        try:
            for cand in config._candidates():
                if cand.exists():
                    path = cand
                    current.update(json.loads(cand.read_text("utf-8")))
                    break
        except (OSError, json.JSONDecodeError):
            pass

        win = tk.Toplevel(self.root)
        win.title("设置：OpenRouter")
        win.transient(self.root)
        win.grab_set()
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="API Key（openrouter.ai/keys 创建，形如 sk-or-v1-…）：")\
            .grid(row=0, column=0, sticky="w")
        key_e = ttk.Entry(frm, width=58)
        key_e.insert(0, current.get("api_key", ""))
        key_e.grid(row=1, column=0, sticky="we", pady=(0, 6))
        ttk.Label(frm, text="模型 ID（OpenRouter 上任意模型）：")\
            .grid(row=2, column=0, sticky="w")
        model_e = ttk.Entry(frm, width=58)
        model_e.insert(0, current.get("model", config.DEFAULT_MODEL))
        model_e.grid(row=3, column=0, sticky="we", pady=(0, 6))
        ttk.Label(frm, text=f"保存位置：{path}", foreground="#666666")\
            .grid(row=4, column=0, sticky="w")

        def save():
            data = {"api_key": key_e.get().strip(),
                    "model": model_e.get().strip() or config.DEFAULT_MODEL,
                    "base_url": current.get("base_url", config.DEFAULT_BASE_URL)}
            try:
                path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    "utf-8")
            except OSError as e:
                messagebox.showerror(_TITLE, f"保存失败：{e}", parent=win)
                return
            win.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="保存", command=save).pack(side="right", padx=4)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="right")


def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.3)
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

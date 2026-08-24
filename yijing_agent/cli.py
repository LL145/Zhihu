"""命令行入口。

用法示例：
    python -m yijing_agent -q "近期换工作是否合适"
    python -m yijing_agent -q "……" --method coin
    python -m yijing_agent -q "……" --when "2026-08-24 15:30" --no-llm
"""

import argparse
import sys
from datetime import datetime

from . import casting, config, redline, report, selection, topic, verdict
from .knowledge import KnowledgeBase
from .llm import InterpreterError, followup, interpret


def _ensure_utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _parse_when(s):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise SystemExit(f"无法解析时间: {s}（格式: YYYY-MM-DD HH:MM）")


def _followup_loop(cfg, kb, question, cast, sel, vd, first_result, tp):
    """多轮追问：不重新起卦，仍以本次所据经文与结论为据。仅在交互终端提供。"""
    try:
        if sys.stdin is None or not sys.stdin.isatty():
            return
    except (AttributeError, ValueError):
        return
    print()
    print("── 追问（同卦续问，不重新起卦；直接回车结束） " + "─" * 6)
    history = []
    while True:
        try:
            ask = input("追问：").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not ask:
            break
        refusal = redline.check(ask)
        if refusal:
            print(refusal)
            continue
        try:
            fu, _ = followup(cfg, kb, question, cast, sel, vd, first_result,
                             history, ask, tp)
        except InterpreterError as e:
            print(f"〔追问回答不可用〕{e}")
            for err in e.errors:
                print(f"  - {err}")
            continue
        print(report.render_followup(fu))
        history.append((ask, fu))


def main(argv=None):
    _ensure_utf8_stdout()
    p = argparse.ArgumentParser(prog="yijing_agent", description="易经事引擎：有典可依、可复现的问事占断")
    p.add_argument("-q", "--question", help="所问之事（不传则进入交互输入）")
    p.add_argument("--method", choices=["time", "coin"], default="time",
                   help="起卦法：time=梅花易数时间起卦（默认，完全确定）；coin=铜钱法")
    p.add_argument("--when", help="指定起卦时刻 YYYY-MM-DD HH:MM（默认当前时刻；用于复现）")
    p.add_argument("--salt", default="", help="铜钱法附加盐（同刻同问再占时区分用）")
    p.add_argument("--no-llm", action="store_true", help="不调用大模型，仅输出原文与结论")
    args = p.parse_args(argv)

    interactive = args.question is None
    question = args.question
    if not question:
        try:
            question = input("所问之事：").strip()
        except (EOFError, KeyboardInterrupt):
            return 1
    if not question:
        print("未输入问题。")
        return 1

    refusal = redline.check(question)
    if refusal:
        print(refusal)
        return 0

    tp = topic.classify(question)
    when = _parse_when(args.when) if args.when else datetime.now()
    kb = KnowledgeBase()

    if args.method == "time":
        cast = casting.cast_meihua(when)
    else:
        cast = casting.cast_coin(question, when, args.salt)

    ben_id = kb.id_of(cast.ben_binary)
    zhi_id = kb.id_of(cast.zhi_binary)
    sel = selection.select(kb, cast.method, ben_id, zhi_id, cast.moving)
    primary = sel.primary
    vd = verdict.decide(primary.cite_id, kb.citation(primary.cite_id)["text"])

    print()
    print(f"所问：{question}")
    print(report.render_topic(tp))
    print()
    print(report.render_cast(kb, cast))
    print()
    print(report.render_readings(kb, sel))
    print()
    print(report.render_verdict(vd))
    print()

    cfg = config.load()
    if args.no_llm:
        pass
    elif not cfg["api_key"]:
        path, created = config.ensure_file()
        if created:
            print(f"（已生成配置文件：{path}\n"
                  f"  用记事本打开它，把 api_key 换成你的 OpenRouter API Key，"
                  f"model 可换成任意 OpenRouter 模型 ID，保存后重新运行即可获得大模型解读。）")
        else:
            print(f"（尚未填写 OpenRouter API Key：请编辑 {path} 的 api_key 字段，"
                  f"或设置环境变量 OPENROUTER_API_KEY。当前以无解读模式输出。）")
    else:
        try:
            result, attempts = interpret(cfg, kb, question, cast, sel, vd, tp)
            print(report.render_interpretation(result))
            note = f"（模型：{cfg['model']}；第 {attempts} 次生成通过逐字校验）"
            print(note)
            _followup_loop(cfg, kb, question, cast, sel, vd, result, tp)
        except InterpreterError as e:
            print(f"〔解读不可用〕{e}")
            for err in e.errors:
                print(f"  - {err}")
            print("已降级为仅原文与结论的输出。")
    print()
    print(report.render_repro(cast))
    print()
    print("※ " + report.DISCLAIMER)
    if interactive and getattr(sys, "frozen", False):  # 双击运行 exe 时不闪退
        try:
            input("\n（回车退出）")
        except (EOFError, KeyboardInterrupt):
            pass
    return 0

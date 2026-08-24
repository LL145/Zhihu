"""命令行入口（双引擎：卦断事，盘论人）。

用法示例：
    python -m yijing_agent -q "近期换工作是否合适"
    python -m yijing_agent -q "……" --method coin
    python -m yijing_agent -q "……" --when "2026-08-24 15:30" --no-llm
    python -m yijing_agent -q "我今年运势如何" --birth 2000-09-14 --birth-time 午 --gender 男

命格/时运类问题在提供生辰（出生日期 + 时辰 + 性别）时走紫微命引擎；
未提供则仍以事引擎就当下之势作断并提示局限。其余问题一律走事引擎。
"""

import argparse
import re
import sys
from datetime import datetime

from . import casting, config, lunar, redline, report, selection, topic, verdict
from .knowledge import KnowledgeBase
from .llm import InterpreterError, followup, interpret
from .trigrams import ZHI
from .ziwei import chart as zchart
from .ziwei import llm as zllm
from .ziwei import report as zreport
from .ziwei import selection as zselection
from .ziwei.knowledge import ZiweiKB


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


def _parse_birth_date(s):
    m = re.fullmatch(r"(\d{4})[-./年 ](\d{1,2})[-./月 ](\d{1,2})日?", s.strip())
    if not m:
        raise SystemExit(f"无法解析出生日期: {s}（格式: YYYY-MM-DD）")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _parse_birth_hour(s):
    """时辰名（子…亥）或钟点（HH / HH:MM）→ 小时数。晚子时不换日由排盘处理。"""
    s = s.strip().rstrip("时")
    if s in ZHI:
        return ZHI.index(s) * 2
    m = re.fullmatch(r"(\d{1,2})(?::\d{1,2})?", s)
    if m and 0 <= int(m.group(1)) <= 23:
        return int(m.group(1))
    raise SystemExit(f"无法解析出生时辰: {s}（时辰名如「午」，或钟点如 11:30）")


def _is_tty():
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _resolve_birth(args, allow_prompt):
    """→ (datetime, gender) 或 None（信息不全）。缺时辰无法排盘（DESIGN §7.1）。"""
    birth, btime, gender = args.birth, args.birth_time, args.gender
    if allow_prompt and _is_tty() and not (birth and btime and gender):
        print("（此问属命理，可依生辰以紫微命引擎作答；直接回车跳过则仍以易经事引擎论当下之势。）")
        try:
            birth = birth or input("  出生日期（公历 YYYY-MM-DD）：").strip()
            if birth:
                btime = btime or input("  出生时辰（时辰名如「午」，或钟点如 11:30；未知请回车）：").strip()
            if birth and btime:
                gender = gender or input("  性别（男/女）：").strip()
        except (EOFError, KeyboardInterrupt):
            return None
    if not (birth and btime and gender):
        return None
    y, m, d = _parse_birth_date(birth)
    hour = _parse_birth_hour(btime)   # 时辰由整点小时唯一确定，分钟不参与
    return datetime(y, m, d, hour), gender


def _followup_loop(redline_check, ask_fn, render_fn):
    """多轮追问：不重新起卦/排盘。仅在交互终端提供。"""
    if not _is_tty():
        return
    print()
    print("── 追问（就本次结果续问，不重新起卦排盘；直接回车结束） " + "─" * 6)
    history = []
    while True:
        try:
            ask = input("追问：").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not ask:
            break
        refusal = redline_check(ask)
        if refusal:
            print(refusal)
            continue
        try:
            fu = ask_fn(history, ask)
        except InterpreterError as e:
            print(f"〔追问回答不可用〕{e}")
            for err in e.errors:
                print(f"  - {err}")
            continue
        print(render_fn(fu))
        history.append((ask, fu))


def _llm_block(cfg, run_interpret, run_followup):
    """解读 + 追问的公共流程；缺 key 时给配置提示。"""
    if not cfg["api_key"]:
        path, created = config.ensure_file()
        if created:
            print(f"（已生成配置文件：{path}\n"
                  f"  用记事本打开它，把 api_key 换成你的 OpenRouter API Key，"
                  f"model 可换成任意 OpenRouter 模型 ID，保存后重新运行即可获得大模型解读。）")
        else:
            print(f"（尚未填写 OpenRouter API Key：请编辑 {path} 的 api_key 字段，"
                  f"或设置环境变量 OPENROUTER_API_KEY。当前以无解读模式输出。）")
        return
    try:
        result, attempts = run_interpret()
        print(report.render_interpretation(result))
        print(f"（模型：{cfg['model']}；第 {attempts} 次生成通过逐字校验）")
        _followup_loop(redline.check,
                       lambda h, a: run_followup(result, h, a)[0],
                       report.render_followup)
    except InterpreterError as e:
        print(f"〔解读不可用〕{e}")
        for err in e.errors:
            print(f"  - {err}")
        print("已降级为仅原文与结论的输出。")


def _run_chart(question, tp, when, birth_dt, gender, no_llm):
    """命引擎路径：排盘 → 规则选文 → 确定性结论 → LLM 解读。"""
    c = zchart.cast(birth_dt, gender)
    zkb = ZiweiKB()
    if tp.key == "fortune":
        sel = zselection.select_fortune(zkb, c, when)
        vd = zselection.decide_fortune(c, when)
    else:
        sel = zselection.select_destiny(zkb, c)
        vd = zselection.decide_destiny(c)

    print()
    print(f"所问：{question}")
    print("引擎：紫微命引擎（盘论人：此问依生辰排盘作答）")
    print(f"类别：{tp.name}")
    print()
    print(zreport.render_chart(c))
    print()
    print(zreport.render_readings(zkb, sel))
    print()
    print(report.render_verdict(vd))
    print()

    cfg = config.load()
    if not no_llm:
        _llm_block(
            cfg,
            lambda: zllm.interpret_chart(cfg, zkb, question, c, sel, vd, tp),
            lambda first, h, a: zllm.followup_chart(
                cfg, zkb, question, c, sel, vd, first, h, a, tp))
    print()
    print(zreport.render_repro(c))
    print()
    print("※ " + report.DISCLAIMER)


def main(argv=None):
    _ensure_utf8_stdout()
    p = argparse.ArgumentParser(
        prog="yijing_agent",
        description="有典可依、可复现的占断：易经事引擎 + 紫微命引擎（卦断事，盘论人）")
    p.add_argument("-q", "--question", help="所问之事（不传则进入交互输入）")
    p.add_argument("--method", choices=["time", "coin"], default="time",
                   help="起卦法：time=梅花易数时间起卦（默认，完全确定）；coin=铜钱法")
    p.add_argument("--when", help="指定起卦/论限时刻 YYYY-MM-DD HH:MM，按北京时间"
                                  "（默认取当前时刻并自动换算为北京时间；用于复现）")
    p.add_argument("--salt", default="", help="铜钱法附加盐（同刻同问再占时区分用）")
    p.add_argument("--birth", help="出生日期（公历 YYYY-MM-DD，命理类问题用，紫微排盘）")
    p.add_argument("--birth-time", help="出生时辰（时辰名如「午」，或钟点如 11:30；缺则无法排盘）")
    p.add_argument("--gender", choices=["男", "女"], help="性别（大限顺逆用）")
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
    when = _parse_when(args.when) if args.when else lunar.now_beijing()

    if tp.engine_hint == "chart":
        birth = _resolve_birth(args, allow_prompt=interactive)
        if birth:
            _run_chart(question, tp, when, birth[0], birth[1], args.no_llm)
            if interactive and getattr(sys, "frozen", False):
                try:
                    input("\n（回车退出）")
                except (EOFError, KeyboardInterrupt):
                    pass
            return 0

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
    print("引擎：易经事引擎（卦断事）")
    print(report.render_topic(tp))
    if tp.engine_hint == "chart":
        print("（欲以紫微命盘作答，请附生辰：--birth 2000-09-14 --birth-time 午 "
              "--gender 男；时辰未知则无法排盘，见 DESIGN §7.1）")
    print()
    print(report.render_cast(kb, cast))
    print()
    print(report.render_readings(kb, sel))
    print()
    print(report.render_verdict(vd))
    print()

    cfg = config.load()
    if not args.no_llm:
        _llm_block(
            cfg,
            lambda: interpret(cfg, kb, question, cast, sel, vd, tp),
            lambda first, h, a: followup(
                cfg, kb, question, cast, sel, vd, first, h, a, tp))
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

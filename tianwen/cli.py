"""命令行入口（单一模式，ALGORITHM.md）。

用法示例：
    python -m tianwen -q "近期换工作是否合适" --name 李明 \
        --birth 2000-09-14 --birth-time 午 --gender 男
    python -m tianwen -q "……" --when "2026-08-24 15:30" --no-llm

输入固定五项：问什么＋姓名＋生日＋出生时辰＋性别。三占同起（时间卦、
姓名卦、紫微盘），吉凶只从主断一处出；输入不全只减少参照（如实说明），
不改变流程。输出结论先行；--full 附卦画与盘面。
"""

import argparse
import re
import sys
from datetime import datetime

from . import config, lunar, redline, report, service, topic
from .llm import InterpreterError
from .trigrams import ZHI


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


def _prompt(label):
    try:
        return input(label).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _resolve_inputs(args, interactive):
    """补齐五项输入 → (name, birth_dt|None, gender|None)。

    交互模式下逐项询问，回车跳过（跳过只减少参照，不碍起卦）。
    """
    name = (args.name or "").strip()
    birth, btime, gender = args.birth, args.birth_time, args.gender
    if interactive and _is_tty():
        if not name:
            name = _prompt("  姓名（两三字，起姓名卦用；回车跳过）：")
        if not (birth and btime and gender):
            print("（生辰供紫微排盘：论秉性禀赋与限运；回车跳过则本次无盘。）")
            birth = birth or _prompt("  出生日期（公历 YYYY-MM-DD）：")
            if birth:
                btime = btime or _prompt("  出生时辰（时辰名如「午」，或钟点如 11:30）：")
            if birth and btime:
                gender = gender or _prompt("  性别（男/女）：")
    if not (birth and btime and gender):
        return name, None, None
    y, m, d = _parse_birth_date(birth)
    hour = _parse_birth_hour(btime)   # 时辰由整点小时唯一确定，分钟不参与
    return name, datetime(y, m, d, hour), gender


def _followup_loop(session, cfg):
    """多轮追问：不重新起卦/排盘。仅在交互终端提供。"""
    if not _is_tty():
        return
    print()
    print("── 追问（就本次结果续问，不重新起卦排盘；直接回车结束） " + "─" * 6)
    while True:
        ask = _prompt("追问：")
        if not ask:
            break
        try:
            print(session.followup(cfg, ask))
        except service.RefusalError as e:
            print(e)
        except InterpreterError as e:
            print(f"〔追问回答不可用〕{e}")
            for err in e.errors:
                print(f"  - {err}")


def _print_key_hint():
    path, created = config.ensure_file()
    if created:
        print(f"（已生成配置文件：{path}\n"
              f"  用记事本打开它，把 api_key 换成你的 OpenRouter API Key，"
              f"model 可换成任意 OpenRouter 模型 ID，保存后重新运行即可获得大模型解读。）")
    else:
        print(f"（尚未填写 OpenRouter API Key：请编辑 {path} 的 api_key 字段，"
              f"或设置环境变量 OPENROUTER_API_KEY。当前结论直取定例断辞。）")


def main(argv=None):
    _ensure_utf8_stdout()
    p = argparse.ArgumentParser(
        prog="tianwen",
        description="有典可依、可复现的占断（单一模式：三占同起，主断唯一；"
                    "流程与逐步典据见 ALGORITHM.md）")
    p.add_argument("-q", "--question", help="所问之事（不传则进入交互输入）")
    p.add_argument("--name", help="姓名（两三字，起姓名卦：论问者之位；可缺）")
    p.add_argument("--birth", help="出生日期（公历 YYYY-MM-DD，紫微排盘用；可缺）")
    p.add_argument("--birth-time", help="出生时辰（时辰名如「午」，或钟点如 11:30；缺则无法排盘）")
    p.add_argument("--gender", choices=["男", "女"], help="性别（大限顺逆、男女命诀用）")
    p.add_argument("--when", help="指定起卦/论限时刻 YYYY-MM-DD HH:MM，按北京时间"
                                  "（默认取当前时刻并自动换算为北京时间；用于复现）")
    p.add_argument("--topic", choices=[name for _k, name in topic.CATEGORIES],
                   help="手动指定问事类别（缺省自动判类：关键词规则优先，"
                        "规则未中且已配模型时由占者判类并标注）")
    p.add_argument("--full", action="store_true", help="附卦画与十二宫盘面")
    p.add_argument("--no-llm", action="store_true", help="不调用大模型，结论直取定例断辞")
    args = p.parse_args(argv)

    interactive = args.question is None
    question = args.question
    if not question:
        question = _prompt("所问之事：")
    if not question:
        print("未输入问题。")
        return 1

    refusal = redline.check(question)
    if refusal:
        print(refusal)
        return 0

    cfg = config.load()
    override = {name: key for key, name in topic.CATEGORIES}.get(args.topic)
    try:
        tp = service.resolve_topic(question,
                                   cfg=None if args.no_llm else cfg,
                                   override=override)
    except service.RefusalError as e:
        print(e)
        return 0

    name, birth_dt, gender = _resolve_inputs(args, interactive)
    when = _parse_when(args.when) if args.when else lunar.now_beijing()
    s = service.prepare(question, name=name, birth_dt=birth_dt, gender=gender,
                        when=when, tp=tp)

    print()
    if args.no_llm or not cfg["api_key"]:
        print(s.render_all(full=args.full))
        if not args.no_llm:
            print()
            _print_key_hint()
    else:
        try:
            text, _attempts = s.interpret(cfg, full=args.full)
            print(text)
            _followup_loop(s, cfg)
        except InterpreterError as e:
            print(f"〔解读不可用〕{e}")
            for err in e.errors:
                print(f"  - {err}")
            print("已降级为定例断辞与原文的输出。")
            print()
            print(s.render_all(full=args.full))

    if interactive and getattr(sys, "frozen", False):  # 双击运行 exe 时不闪退
        try:
            input("\n（回车退出）")
        except (EOFError, KeyboardInterrupt):
            pass
    return 0

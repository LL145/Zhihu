"""双引擎流水线门面：把「路由 → 起卦/排盘 → 选文 → 结论 → 解读 → 追问」
封装成会话对象，供图形界面等前端复用（CLI 保留自身等价流程）。

所有确定性步骤在构造时同步完成；interpret / followup 由调用方决定在
何处执行（GUI 放在工作线程）。红线拦截以 RefusalError 抛出。
"""

from . import casting, lunar, redline, report, selection, topic, verdict
from .knowledge import KnowledgeBase
from .llm import InterpreterError
from .llm import classify_topic as _classify_topic
from .llm import followup as _followup
from .llm import interpret as _interpret
from .ziwei import chart as zchart
from .ziwei import llm as zllm
from .ziwei import report as zreport
from .ziwei import selection as zselection
from .ziwei.knowledge import ZiweiKB

DISCLAIMER = report.DISCLAIMER


class RefusalError(Exception):
    """红线拒答：str(e) 即应向用户展示的拒答文本。"""


def resolve_topic(question, cfg=None, override=None):
    """判类三级：用户指定 > 关键词规则 > 占者判类（规则未中且已配模型）。

    红线先查（抛 RefusalError），故占者判类不会见到拒答类问题。
    override 为类别键（topic.CATEGORIES）；cfg 缺省或无 api_key 则不启用
    占者判类，规则未中照旧归「其他」。
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("未输入问题")
    refusal = redline.check(question)
    if refusal:
        raise RefusalError(refusal)
    if override:
        return topic.by_key(override, source="user")
    tp = topic.classify(question)
    if tp.key == "other" and cfg and cfg.get("api_key"):
        key = _classify_topic(cfg, question)
        if key and key != "other":
            return topic.by_key(key, source="llm")
    return tp


def prepare(question, *, method="time", when=None, salt="", chars="",
            birth_dt=None, gender=None, tp=None, both=False):
    """路由并完成全部确定性步骤，返回会话对象。

    命格/时运类问题且生辰齐备（出生日期时辰 + 性别）→ 紫微命引擎；
    其余 → 易经事引擎。红线问题抛 RefusalError。
    tp 可传入 resolve_topic 的结果（判类三级）；缺省按关键词规则判类。
    chars 为字占（method="zi"）所占之字（如姓名），两三字；不合法抛
    ValueError。both=True 时，命理之问且生辰齐备走卦盘并占（两问两断，
    DualSession）；不满足并占条件则照常路由（开关静默不生效）。
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("未输入问题")
    refusal = redline.check(question)
    if refusal:
        raise RefusalError(refusal)
    tp = tp or topic.classify(question)
    when = when or lunar.now_beijing()
    if tp.engine_hint == "chart" and birth_dt is not None and gender:
        if both:
            return DualSession(question, tp, when, method, salt,
                               birth_dt, gender, chars=chars)
        return ChartSession(question, tp, when, birth_dt, gender)
    return EventSession(question, tp, when, method, salt, birth_dt, gender,
                        chars=chars)


class _Session:
    """公共部分：解读与追问的状态管理。"""

    kind = ""

    def __init__(self, question, tp):
        self.question = question
        self.tp = tp
        self.first_result = None
        self.history = []

    # 子类实现：_interpret_call(cfg) / _followup_call(cfg, ask)

    def interpret(self, cfg):
        """→ (渲染文本＋占断存证, 尝试次数)。校验不过抛 InterpreterError。"""
        result, attempts = self._interpret_call(cfg)
        self.first_result = result
        text = report.render_interpretation(result) + "\n\n" \
            + report.attestation(cfg.get("model", "?"), result, attempts)
        return text, attempts

    def followup(self, cfg, ask):
        """→ 渲染文本。须在 interpret 成功后调用；逐问过红线。"""
        if self.first_result is None:
            raise RuntimeError("须先完成解读方可追问")
        refusal = redline.check(ask)
        if refusal:
            raise RefusalError(refusal)
        result, _ = self._followup_call(cfg, ask)
        self.history.append((ask, result))
        return report.render_followup(result)


class EventSession(_Session):
    """易经事引擎会话。带生辰时命盘作合参语境（§6.2），不出第二结论。"""

    kind = "event"

    def __init__(self, question, tp, when, method, salt,
                 birth_dt=None, gender=None, chart_hint=True, chars=""):
        super().__init__(question, tp)
        self.kb = KnowledgeBase()
        self.chart_hint = chart_hint
        if method == "time":
            self.cast = casting.cast_meihua(when)
        elif method == "zi":
            self.cast = casting.cast_zi(chars)
        else:
            self.cast = casting.cast_coin(question, when, salt)
        ben = self.kb.id_of(self.cast.ben_binary)
        zhi = self.kb.id_of(self.cast.zhi_binary)
        self.sel = selection.select(self.kb, self.cast.method, ben, zhi,
                                    self.cast.moving, tp, question)
        primary = self.sel.primary
        self.vd = verdict.decide(primary.cite_id,
                                 self.kb.citation(primary.cite_id)["text"])
        self.context = None      # 合参语境 (ZiweiKB, ChartSelection)
        if tp.engine_hint == "event" and birth_dt is not None and gender:
            zkb = ZiweiKB()
            csel = zselection.select_context(
                zkb, zchart.cast(birth_dt, gender), tp, question)
            if csel.readings:
                self.context = (zkb, csel)

    def body_text(self, header=True):
        parts = []
        if header:
            parts += [f"所问：{self.question}",
                      "引擎：易经事引擎（卦断事）",
                      report.render_topic(self.tp)]
            if self.tp.engine_hint == "chart" and self.chart_hint:
                parts.append("（欲以紫微命盘作答，请填生辰：出生日期＋时辰＋性别；"
                             "时辰未知则无法排盘）")
            parts.append("")
        parts += [report.render_cast(self.kb, self.cast), "",
                  report.render_readings(self.kb, self.sel), "",
                  report.render_verdict(self.vd)]
        if self.context is not None:
            parts += ["", zreport.render_context(*self.context)]
        return "\n".join(parts)

    def repro_text(self):
        return report.render_repro(self.cast)

    def _interpret_call(self, cfg):
        return _interpret(cfg, self.kb, self.question, self.cast, self.sel,
                          self.vd, self.tp, self.context)

    def _followup_call(self, cfg, ask):
        return _followup(cfg, self.kb, self.question, self.cast, self.sel,
                         self.vd, self.first_result, self.history, ask, self.tp,
                         self.context)


class ChartSession(_Session):
    """紫微命引擎会话。"""

    kind = "chart"

    def __init__(self, question, tp, when, birth_dt, gender):
        super().__init__(question, tp)
        self.zkb = ZiweiKB()
        self.chart = zchart.cast(birth_dt, gender)
        aspect = zselection.detect_aspect(question)[0]   # 问事分宫
        if tp.key == "fortune":
            self.sel = zselection.select_fortune(self.zkb, self.chart, when,
                                                 aspect)
            self.vd = zselection.decide_fortune(self.chart, when)
        else:
            self.sel = zselection.select_destiny(self.zkb, self.chart, aspect)
            self.vd = zselection.decide_destiny(self.chart)

    def body_text(self, header=True):
        parts = []
        if header:
            parts += [f"所问：{self.question}",
                      "引擎：紫微命引擎（盘论人：此问依生辰排盘作答）",
                      f"类别：{self.tp.name}{report.topic_source_label(self.tp)}",
                      ""]
        parts += [zreport.render_chart(self.chart), "",
                  zreport.render_readings(self.zkb, self.sel), "",
                  report.render_verdict(self.vd)]
        return "\n".join(parts)

    def repro_text(self):
        return zreport.render_repro(self.chart)

    def _interpret_call(self, cfg):
        return zllm.interpret_chart(cfg, self.zkb, self.question, self.chart,
                                    self.sel, self.vd, self.tp)

    def _followup_call(self, cfg, ask):
        return zllm.followup_chart(cfg, self.zkb, self.question, self.chart,
                                   self.sel, self.vd, self.first_result,
                                   self.history, ask, self.tp)


class DualSession:
    """卦盘并占（两问两断）：命理之问附生辰且用户要求并占时，
    盘为主照常命断，另以同一问题、同一时刻起卦作事断。

    两份各有定例对照、各自占断、各自存证；两次解读各在各的文本池内
    生成（互不见对方原文），结构上不可能折中——并陈，不合断（§6.3）。
    """

    kind = "dual"

    def __init__(self, question, tp, when, method, salt, birth_dt, gender,
                 chars=""):
        self.question = question
        self.tp = tp
        self.chart = ChartSession(question, tp, when, birth_dt, gender)
        # 卦侧不传生辰：盘已完整在场，不再作合参语境（避免重复入池）
        self.event = EventSession(question, tp, when, method, salt,
                                  chart_hint=False, chars=chars)

    @property
    def first_result(self):
        """任一侧解读成功即可开放追问。"""
        return self.chart.first_result or self.event.first_result

    def body_text(self):
        return "\n".join([
            f"所问：{self.question}",
            "引擎：卦盘并占——两问两断：盘断其势，卦断其事；并陈，不合断",
            f"类别：{self.tp.name}{report.topic_source_label(self.tp)}",
            "",
            "══ 之一 · 盘断其势（紫微命引擎） " + "═" * 14,
            "",
            self.chart.body_text(header=False),
            "",
            "══ 之二 · 卦断其事（易经事引擎） " + "═" * 14,
            "",
            self.event.body_text(header=False),
        ])

    def repro_text(self):
        return (self.chart.repro_text() + "\n\n" + self.event.repro_text())

    def interpret(self, cfg):
        """两侧各自解读；一侧校验不过只降级该侧，两侧俱败才抛错。"""
        parts, errors, attempts_total = [], [], 0
        for label, s in (("盘·占断（论势）", self.chart),
                         ("卦·占断（断事）", self.event)):
            try:
                text, attempts = s.interpret(cfg)
                attempts_total += attempts
                parts.append(f"【{label}】\n{text}")
            except InterpreterError as e:
                errors.append(f"{label}：{e}")
                parts.append(f"【{label}】\n〔解读不可用〕{e}（本侧降级为"
                             "仅原文与定例）")
        if len(errors) == 2:
            raise InterpreterError("并占两侧解读均未通过校验", errors)
        return "\n\n".join(parts), attempts_total

    def followup(self, cfg, ask):
        """追问两侧并答，各在各的文本池内；一侧失败不碍另一侧。"""
        refusal = redline.check(ask)
        if refusal:
            raise RefusalError(refusal)
        parts = []
        for label, s in (("盘", self.chart), ("卦", self.event)):
            if s.first_result is None:
                continue
            try:
                parts.append(f"【{label}】\n" + s.followup(cfg, ask))
            except InterpreterError as e:
                parts.append(f"【{label}】\n〔追问回答不可用〕{e}")
        return "\n\n".join(parts)

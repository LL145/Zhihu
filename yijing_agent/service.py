"""单一模式流水线门面（ALGORITHM.md）。

输入固定五项：问什么＋姓名＋生日＋出生时辰＋性别。三种占法同时起
（时间卦、姓名卦、紫微盘），全部确定性、无随机数；吉凶只从主断一处出
（问具体事→时间卦，问命格/时运且有盘→紫微盘），其余占法只以语境块
（ContextBlock）进入解读层——结构上杜绝自相矛盾（ALGORITHM.md 五）。

输入不全只减少参照，不改变流程形状：姓名不合书例则不起姓名卦并说明
缘由，生辰不全则无盘。所有确定性步骤在构造时同步完成；interpret /
followup 由调用方决定在何处执行（GUI 放在工作线程）。红线拦截以
RefusalError 抛出。
"""

from . import casting, lunar, redline, report, selection, topic, verdict
from .knowledge import KnowledgeBase
from .llm import ContextBlock, InterpreterError
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


def prepare(question, *, name="", birth_dt=None, gender=None, when=None,
            tp=None):
    """完成全部确定性步骤，返回单一模式会话对象（ALGORITHM.md 三）。

    tp 可传入 resolve_topic 的结果（判类三级）；缺省按关键词规则判类。
    红线问题抛 RefusalError。
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("未输入问题")
    refusal = redline.check(question)
    if refusal:
        raise RefusalError(refusal)
    tp = tp or topic.classify(question)
    when = when or lunar.now_beijing()
    return Session(question, tp, when, name, birth_dt, gender)


class Session:
    """单一模式会话：三占同起，主断唯一，语境合参。"""

    def __init__(self, question, tp, when, name, birth_dt, gender):
        self.question = question
        self.tp = tp
        self.when = when
        self.first_result = None
        self.history = []
        self.kb = KnowledgeBase()
        self.zkb = ZiweiKB()

        # 起时间卦（恒起；meihua:1:qi:shijian）
        self.time_cast = casting.cast_meihua(when)

        # 起姓名卦（meihua:1:qi:zishu；不合书例则不起，缘由如实展示）
        self.name = "".join((name or "").split())
        self.name_cast = None
        self.name_note = ""
        if not self.name:
            self.name_note = "未提供姓名，本次不起姓名卦"
        else:
            try:
                self.name_cast = casting.cast_zi(self.name)
            except ValueError as e:
                self.name_note = f"姓名卦未起——{e}"

        # 紫微排盘（《全书·卷一》诸起例；生辰不全则无盘）
        self.chart = None
        self.chart_note = ""
        if birth_dt is not None and gender:
            self.chart = zchart.cast(birth_dt, gender)
        else:
            self.chart_note = "未提供完整生辰（出生日期＋时辰＋性别），本次无紫微盘"

        # 主断路由（约定「卦断事，盘论人」，ALGORITHM.md 四.6）
        self.primary = "chart" if (tp.engine_hint == "chart"
                                   and self.chart is not None) else "event"
        if self.primary == "event":
            ben = self.kb.id_of(self.time_cast.ben_binary)
            zhi = self.kb.id_of(self.time_cast.zhi_binary)
            self.sel = selection.select(self.kb, self.time_cast.method, ben,
                                        zhi, self.time_cast.moving, tp,
                                        question)
            p = self.sel.primary
            self.vd = verdict.decide(p.cite_id,
                                     self.kb.citation(p.cite_id)["text"])
        else:
            aspect = zselection.detect_aspect(question)[0]
            if tp.key == "fortune":
                self.sel = zselection.select_fortune(self.zkb, self.chart,
                                                     when, aspect)
                self.vd = zselection.decide_fortune(self.chart, when)
            else:
                self.sel = zselection.select_destiny(self.zkb, self.chart,
                                                     aspect)
                self.vd = zselection.decide_destiny(self.chart)

        self.contexts = self._build_contexts()

    # ── 语境块（可引不可断，ALGORITHM.md 五） ────────────────────────

    def _cast_items(self, cast):
        """卦的语境文本：动爻爻辞＋小象＋本卦卦辞（紧凑，不铺陈）。"""
        ben = self.kb.id_of(cast.ben_binary)
        pos = cast.moving[0]
        items = []
        for cid in (f"zhouyi:{ben}:yao:{pos}", f"xiaoxiang:{ben}:{pos}",
                    f"zhouyi:{ben}:guaci"):
            c = self.kb.citation(cid)
            items.append((cid, c["source"], c["text"]))
        return items

    def _cast_desc(self, cast):
        ben = self.kb.id_of(cast.ben_binary)
        zhi = self.kb.id_of(cast.zhi_binary)
        pos = cast.moving[0]
        yao_name = self.kb.hexagram(ben)["yao"][pos - 1]["name"]
        ti, yong = selection.tiyong(self.kb, ben, pos)
        return (f"{self.kb.hexagram(ben)['symbol']} {self.kb.full_name(ben)}"
                f" → {self.kb.hexagram(zhi)['symbol']} {self.kb.full_name(zhi)}"
                f"（动爻{yao_name}）｜体{ti}用{yong}")

    def _build_contexts(self):
        blocks = []
        if self.primary == "chart":
            blocks.append(ContextBlock(
                title="时间卦（当下之势）",
                notes=[f"以此问之时起卦（年月日时起例）：{self._cast_desc(self.time_cast)}",
                       "只作当下之势之参，吉凶仍依盘断"],
                items=self._cast_items(self.time_cast)))
        if self.name_cast is not None:
            blocks.append(ContextBlock(
                title="姓名卦（论问者之位）",
                notes=[f"以「{self.name}」字画起卦（一字占至十一字占）："
                       f"{self._cast_desc(self.name_cast)}",
                       "只论问者所处之位与姿态，不出第二个吉凶"],
                items=self._cast_items(self.name_cast)))
        if self.primary == "event" and self.chart is not None:
            csel = zselection.select_context(self.zkb, self.chart, self.tp,
                                             self.question)
            if csel.readings:
                items = []
                for r in csel.readings:
                    c = self.zkb.citation(r.cite_id)
                    items.append((r.cite_id, c["source"], c["text"]))
                    for cid in r.context_ids:
                        ctx = self.zkb.citation(cid)
                        items.append((cid, ctx["source"], ctx["text"]))
                blocks.append(ContextBlock(
                    title="紫微盘（论秉性禀赋）",
                    notes=list(csel.notes) + [r.role for r in csel.readings],
                    items=items))
        return blocks

    # ── 呈现（结论先行，ALGORITHM.md 六） ────────────────────────────

    def header_text(self):
        parts = [f"所问：{self.question}",
                 f"类别：{self.tp.name}{report.topic_source_label(self.tp)}"]
        if self.tp.engine_hint == "chart" and self.chart is None:
            parts.append("（属命理之问而生辰不全：以时间卦就当下之势作断，"
                         "不论终身）")
        if self.name_note:
            parts.append(f"（{self.name_note}）")
        if self.chart_note:
            parts.append(f"（{self.chart_note}）")
        return "\n".join(parts)

    def overview_text(self):
        lines = ["── 卦盘一览 " + "─" * 28]
        tag = "主断" if self.primary == "event" else "参·当下之势"
        lines.append(f"  时间卦（{tag}）：{self._cast_desc(self.time_cast)}")
        if self.name_cast is not None:
            lines.append(f"  姓名卦（参·论问者之位）：「{self.name}」"
                         f"{self._cast_desc(self.name_cast)}")
        if self.chart is not None:
            majors = "、".join(
                s.name + (s.brightness or "")
                for s in self.chart.palaces[0].major()) or "无正曜"
            tag = "主断" if self.primary == "chart" else "语境·论禀赋"
            lines.append(f"  紫微盘（{tag}）：命宫在{self.chart.ming_branch}"
                         f"（{majors}），{self.chart.yinyang}，"
                         f"{self.chart.wuxing_ju}")
        audited = "人工审定" if self.vd["audited"] else "自动提取，待人工审定"
        lines.append(f"  定例断辞（主断侧机断，{audited}）："
                     f"【{self.vd['verdict']}】{self.vd['action']}")
        return "\n".join(lines)

    def evidence_text(self):
        if self.primary == "event":
            return report.render_readings_compact(self.kb, self.sel)
        return zreport.render_readings_compact(self.zkb, self.sel)

    def detail_text(self):
        """卦画与盘面（--full 附录用；默认输出为省篇幅不含）。"""
        parts = [report.render_cast(self.kb, self.time_cast)]
        if self.name_cast is not None:
            parts.append(f"姓名卦「{self.name}」：")
            parts.append(report.render_cast(self.kb, self.name_cast))
        if self.chart is not None:
            parts.append(zreport.render_chart(self.chart))
        return "\n\n".join(parts)

    def repro_text(self):
        parts = [report.render_repro(self.time_cast)]
        if self.name_cast is not None:
            parts.append(report.render_repro(self.name_cast))
        if self.chart is not None:
            parts.append(zreport.render_repro(self.chart))
        return "\n\n".join(parts)

    def degraded_conclusion_text(self):
        """无模型解读时的结论先行：定例断辞之白话＋主断经文为理由。"""
        audited = "人工审定" if self.vd["audited"] else "自动提取，待人工审定"
        kb = self.kb if self.primary == "event" else self.zkb
        c = kb.citation(self.vd["cite_id"])
        text = c["text"].replace("\n", " ")
        note = self.vd["basis"]
        if len(text) > 120:   # 长文（如《论大限》全篇）节引，全文见 corpus
            text = text[:120] + "……"
            note += f"；节引，全文：corpus --cite {self.vd['cite_id']}"
        return "\n".join([
            f"【结论】{self.vd['action']}。",
            f"（定例断辞【{self.vd['verdict']}】，{audited}；"
            "未启用大模型解读，结论直取定例）",
            "",
            f"【理由】主断经文 {c['source']}：「{text}」",
            f"（{note}）",
        ])

    def render_all(self, result=None, model=None, attempts=0, full=False):
        """完整输出（结论先行）：header → 结论/断语/理由/建议 → 一览 →
        所据原文节选 →（--full 卦画盘面）→ 存证 → 凭证 → 免责声明。"""
        parts = [self.header_text(), ""]
        if result is not None:
            parts.append(report.render_interpretation(result))
        else:
            parts.append(self.degraded_conclusion_text())
        parts += ["", self.overview_text(), "", self.evidence_text()]
        if full:
            parts += ["", self.detail_text()]
        if result is not None and model:
            parts += ["", report.attestation(model, result, attempts)]
        parts += ["", self.repro_text(), "", "※ " + DISCLAIMER]
        return "\n".join(parts)

    # ── 解读与追问 ──────────────────────────────────────────────────

    def interpret(self, cfg, full=False):
        """→ (完整渲染文本, 尝试次数)。校验不过抛 InterpreterError。"""
        if self.primary == "event":
            result, attempts = _interpret(
                cfg, self.kb, self.question, self.time_cast, self.sel,
                self.vd, self.tp, self.contexts)
        else:
            result, attempts = zllm.interpret_chart(
                cfg, self.zkb, self.question, self.chart, self.sel, self.vd,
                self.tp, self.contexts)
        self.first_result = result
        return self.render_all(result=result, model=cfg.get("model", "?"),
                               attempts=attempts, full=full), attempts

    def followup(self, cfg, ask):
        """→ 渲染文本。须在 interpret 成功后调用；逐问过红线。"""
        if self.first_result is None:
            raise RuntimeError("须先完成解读方可追问")
        refusal = redline.check(ask)
        if refusal:
            raise RefusalError(refusal)
        if self.primary == "event":
            result, _ = _followup(
                cfg, self.kb, self.question, self.time_cast, self.sel,
                self.vd, self.first_result, self.history, ask, self.tp,
                self.contexts)
        else:
            result, _ = zllm.followup_chart(
                cfg, self.zkb, self.question, self.chart, self.sel, self.vd,
                self.first_result, self.history, ask, self.tp, self.contexts)
        self.history.append((ask, result))
        return report.render_followup(result)

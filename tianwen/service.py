"""单一模式流水线门面（ALGORITHM.md）。

输入固定五项：问什么＋姓名＋生日＋出生时辰＋性别（另有出生地经纬度
可缺）。四样同起（问语卦、时间卦、姓名卦、紫微盘），全部确定性、
无随机数；吉凶只从主断一处出
（问具体事→问语卦[书写来意，以其字占之]，问命格/时运且有盘→紫微盘），
时间卦恒作当下之势之参，其余占法只以语境块
（ContextBlock）进入解读层——结构上杜绝自相矛盾（ALGORITHM.md 五）。
命理主断时另排西洋本命盘（astro/natal.py）：同为生辰确定，只作参照
语境入解读（《占星四书》英译原文可引不可断）；有出生地并排上升中天
与整宫分府，时辰两端跨宫则如实存疑。

输入不全只减少参照，不改变流程形状：姓名不合书例则不起姓名卦并说明
缘由，生辰不全则无盘。所有确定性步骤在构造时同步完成；interpret /
followup 由调用方决定在何处执行（GUI 放在工作线程）。红线拦截以
RefusalError 抛出。
"""

from . import casting, lunar, redline, report, selection, topic, verdict
from .astro import natal as astro_natal
from .knowledge import KnowledgeBase
from .llm import ContextBlock, InterpreterError
from .llm import classify_topic as _classify_topic
from .llm import followup as _followup
from .llm import interpret as _interpret
from .ziwei import chart as zchart
from .ziwei import llm as zllm
from .ziwei import patterns as zpatterns
from .ziwei import report as zreport
from .ziwei import selection as zselection
from .ziwei.knowledge import ZiweiKB

DISCLAIMER = report.DISCLAIMER


class RefusalError(Exception):
    """红线拒答：str(e) 即应向用户展示的拒答文本。"""


def resolve_topic(question, cfg=None, override=None):
    """判类三级：用户指定 > 占者判类（配模型即默认）> 关键词规则回落。

    红线先查（抛 RefusalError），故占者判类不会见到拒答类问题。
    override 为类别键（topic.CATEGORIES）；cfg 缺省或无 api_key 则不启用
    占者判类，径按关键词规则。占者判类失败或判「其他」时同样回落规则
    （判类只定选文框架，失败不致命），规则再未中才归「其他」。
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("未输入问题")
    refusal = redline.check(question)
    if refusal:
        raise RefusalError(refusal)
    if override:
        return topic.by_key(override, source="user")
    if cfg and cfg.get("api_key"):
        key = _classify_topic(cfg, question)
        if key and key != "other":
            return topic.by_key(key, source="llm")
    return topic.classify(question)


def prepare(question, *, name="", birth_dt=None, gender=None, when=None,
            tp=None, birth_place=None):
    """完成全部确定性步骤，返回单一模式会话对象（ALGORITHM.md 三）。

    tp 可传入 resolve_topic 的结果（判类三级）；缺省按关键词规则判类。
    birth_place 为出生地 (东经, 北纬)（度，可缺）——只供西洋本命盘
    上升与分府（步骤 5b），缺则不算、不以默认地冒充。
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
    return Session(question, tp, when, name, birth_dt, gender, birth_place)


class Session:
    """单一模式会话：四样同起，主断唯一，语境合参。"""

    def __init__(self, question, tp, when, name, birth_dt, gender,
                 birth_place=None):
        self.question = question
        self.tp = tp
        self.when = when
        self.first_result = None
        self.history = []
        self.kb = KnowledgeBase()
        self.zkb = ZiweiKB()

        # 起时间卦（恒起，当下之势之参；meihua:1:qi:shijian）
        self.time_cast = casting.cast_meihua(when)

        # 起问语卦（事类主断：书写来意，以其字占之；meihua:1:qi:weiren）
        self.event_note = ""
        try:
            self.event_cast = casting.cast_wenyu(question, when)
        except ValueError as e:
            self.event_note = f"问语卦未起——{e}；以时间卦（年月日时起例）代主断"
            self.event_cast = self.time_cast

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
        self.astro = None
        self.aspect = zselection.detect_aspect(question)[0]
        if self.primary == "chart":
            # 西洋本命盘：命理主断时另排，只入解读语境（可引不可断，
            # ALGORITHM.md 步骤 5b/10）；出生地可缺——缺则无上升分府
            self.astro = astro_natal.cast(birth_dt, place=birth_place)
        if self.primary == "event":
            ben = self.kb.id_of(self.event_cast.ben_binary)
            zhi = self.kb.id_of(self.event_cast.zhi_binary)
            month = lunar.from_datetime(when).month_num   # 卦气以问时月令论
            self.sel = selection.select(self.kb, self.event_cast.method, ben,
                                        zhi, self.event_cast.moving, tp,
                                        question, month=month)
            if self.sel.tiyong is not None:   # 梅花法：体用生克明文映射
                self.vd = verdict.decide_tiyong(self.sel.tiyong)
            else:
                p = self.sel.primary
                self.vd = verdict.decide(p.cite_id,
                                         self.kb.citation(p.cite_id)["text"])
        else:
            aspect = self.aspect
            if tp.key == "fortune":
                self.sel = zselection.select_fortune(self.zkb, self.chart,
                                                     when, aspect)
                self.vd = zselection.decide_fortune(self.chart, when)
            else:
                self.sel = zselection.select_destiny(self.zkb, self.chart,
                                                     aspect)
                self.vd = zselection.decide_destiny(self.chart)

        self.desk = ()   # 书桌召回结果（仅盘为主断时非空；凭证用）
        self.contexts = self._build_contexts()

    # ── 语境块（可引不可断，ALGORITHM.md 五） ────────────────────────

    def _cast_items(self, cast):
        """卦的语境文本：动爻爻辞＋小象＋本卦卦辞＋彖传，附动爻王弼注。

        经、传、注各备一体，供解读旁征博引（可引不可断）；仍取紧凑，
        不铺陈全卦。"""
        ben = self.kb.id_of(cast.ben_binary)
        pos = cast.moving[0]
        items = []
        for cid in (f"zhouyi:{ben}:yao:{pos}", f"xiaoxiang:{ben}:{pos}",
                    f"zhouyi:{ben}:guaci", f"tuan:{ben}"):
            c = self.kb.citation(cid)
            items.append((cid, c["source"], c["text"]))
        note = self.kb.commentary(f"zhouyi:{ben}:yao:{pos}")
        if note:   # 王弼注偶有缺文（如乾上九），缺则不附
            items.append((note["cite_id"], note["source"], note["text"]))
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
        if self.primary == "chart" or self.event_cast is not self.time_cast:
            # 时间卦恒作当下之势之参（问语卦回落时与主断同卦，不重列）
            yi = "盘" if self.primary == "chart" else "问语卦"
            blocks.append(ContextBlock(
                title="时间卦（当下之势）",
                notes=[f"以此问之时起卦（年月日时起例）：{self._cast_desc(self.time_cast)}",
                       f"只作当下之势之参，吉凶仍依{yi}断"],
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
        if self.primary == "chart":
            desk = self._desk_block()
            if desk is not None:
                blocks.append(desk)
        elif getattr(self.sel, "tiyong", None) is not None:
            li = self._li_block()
            if li is not None:
                blocks.append(li)
        if self.astro is not None:
            blocks.append(self._astro_block())
        return blocks

    _LI_CAP = 2   # 占例召回至多则数（依库序；凭证如实标注）
    _LI_KEYWORDS = {"克体": ("克体", "克之"), "生体": ("生体", "生之"),
                    "比和": ("比和",)}

    def _li_block(self):
        """占例（确定性召回层）：按本卦体用之生克字样自《梅花易数》卷一
        占例池机械召回同类之例入语境（可引不可断）——先取用卦关系，
        再取互变之关系；召回规则与命中数进凭证（repro_text）。"""
        an = self.sel.tiyong
        rels = [an.others[0].rel] + [o.rel for o in an.others[1:]]
        self.li_terms = []
        for r in rels:
            key = {"生体": "生体", "克体": "克体", "比和": "比和"}.get(r)
            if key and key not in self.li_terms:
                self.li_terms.append(key)
        pool = [c["cite_id"] for c in self.kb.citations()
                if c["cite_id"].startswith("meihua:1:li:")]
        hits = []
        for key in self.li_terms:
            for cid in pool:
                text = self.kb.citation(cid)["text"]
                if cid not in hits and any(k in text for k in self._LI_KEYWORDS[key]):
                    hits.append(cid)
        self.li_total = len(hits)
        self.li_hits = hits[:self._LI_CAP]
        if not self.li_hits:
            return None
        items = [(cid, self.kb.citation(cid)["source"], self.kb.citation(cid)["text"])
                 for cid in self.li_hits]
        notes = [f"按本卦体用生克字样（{'、'.join(self.li_terms)}）自卷一占例池"
                 f"机械召回，命中 {self.li_total} 例，依库序列前 {len(self.li_hits)}；"
                 "占例是邵子断法之范：可引其法为比、说本卦之势，不得以例中"
                 "所断之事为本卦之断"]
        return ContextBlock(title="占例（同类生克之例，机械召回）",
                            notes=notes, items=items)

    _DESK_CAP = 8   # 书桌每星至多召回行数（凭证如实标注）

    def _desk_block(self):
        """书桌（确定性召回层）：按主断宫主星——问涉题材时并所涉之宫名
        （书桌二期）——自赋文格诀池机械召回候选断语行入语境（可引不可
        断，模型池内择引）；召回规则与命中数进凭证（repro_text）。"""
        terms = getattr(self.sel, "desk_terms", ())
        self.desk = self.zkb.desk(tuple(self.sel.desk_stars) + tuple(terms),
                                  cap=self._DESK_CAP)
        if not self.desk:
            return None
        notes = ["候选断语按主断宫主星星名（问涉题材时并所涉之宫名）"
                 "字样自《全书·卷一》赋文诸论、十等论、定诸局机械召回，"
                 "未必尽合此盘：引用前须对照盘面星曜庙陷宫支，"
                 "不合者勿引，不得据以立断"]
        by_cid = {}
        for star, hits, total in self.desk:
            label = f"所涉之宫{star}" if star in terms else star
            notes.append(f"{label}：命中 {total} 行"
                         + (f"，列前 {len(hits)}" if total > len(hits) else ""))
            for cid, ln in hits:
                lines = by_cid.setdefault(cid, [])
                if ln not in lines:
                    lines.append(ln)
        items = [(cid, self.zkb.citation(cid)["source"], "\n".join(lns))
                 for cid, lns in by_cid.items()]
        return ContextBlock(title="书桌（候选断语，机械召回）",
                            notes=notes, items=items)

    def _astro_block(self):
        """西洋本命盘：盘面事实＋《占星四书》总纲章与论题章（恒附
        1:5/1:16/1:20/1:22，按判类与题材附卷三卷四之章；排了上升分府
        另附 3:4 轴续倾强弱、3:3 生时难准之义；寿夭疾病生死诸章属红线
        主题不附）。引文约定：底本为英译公版，引用须逐字照录英文原文，
        中译只作解释性转述（校验器拉丁通道强制）。"""
        items = []
        for cid in astro_natal.context_chapters(
                self.tp.key, self.aspect,
                with_place=self.astro.angles is not None):
            c = self.kb.citation(f"tetra:{cid}")
            items.append((c["cite_id"], c["source"], c["text"]))
        notes = (["由生辰确定性排得（凭证详后），异邦占法只作参照语境，"
                  "不出第二个吉凶"]
                 + astro_natal.facts_lines(self.astro)
                 + ["《占星四书》为英译公版底本：引用须逐字照录英文原文"
                    "并标 cite_id，中文只可作解释性转述、不得充作引文"])
        return ContextBlock(title="西洋本命盘（托勒密占星，参照）",
                            notes=notes, items=items)

    # ── 呈现（结论先行，ALGORITHM.md 六） ────────────────────────────

    def resolve_cite(self, cid):
        """引文编号 → 古籍原名（跨易类与紫微两库）；未知编号返回 None。

        编号只在校验层流转，对外展示一律经 report.humanize 换成原名。"""
        for k in (self.kb, self.zkb):
            if k.has(cid):
                return k.citation(cid)["source"]
        return None

    def header_text(self):
        parts = [f"所问：{self.question}",
                 f"类别：{self.tp.name}{report.topic_source_label(self.tp)}"]
        if self.tp.engine_hint == "chart" and self.chart is None:
            parts.append("（属命理之问而生辰不全：以卦就当下之势作断，"
                         "不论终身）")
        if self.event_note and self.primary == "event":
            parts.append(f"（{self.event_note}）")
        if self.name_note:
            parts.append(f"（{self.name_note}）")
        if self.chart_note:
            parts.append(f"（{self.chart_note}）")
        return "\n".join(parts)

    def overview_text(self):
        lines = ["── 卦盘一览 " + "─" * 28]
        if self.primary == "event":
            if self.event_cast is not self.time_cast:
                lines.append(f"  问语卦（主断）：以书写来意起，"
                             f"{self._cast_desc(self.event_cast)}")
                lines.append(f"  时间卦（参·当下之势）："
                             f"{self._cast_desc(self.time_cast)}")
            else:   # 问语无字回落：时间卦代主断（缘由见卷首标注）
                lines.append(f"  时间卦（主断）：{self._cast_desc(self.time_cast)}")
        else:
            lines.append(f"  时间卦（参·当下之势）：{self._cast_desc(self.time_cast)}")
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
        if self.astro is not None:
            sun = next(p for p in self.astro.placements if p.key == "sun")
            moon = next(p for p in self.astro.placements if p.key == "moon")
            got = "、".join(f"{n}{s}" for n, s, _sign in self.astro.dignities) \
                or "无得位"
            doubt = "（落宫存疑，详凭证）" if self.astro.moon_uncertain else ""
            ang = self.astro.angles
            if ang is None:
                asc = ""
            elif ang.asc_uncertain:
                asc = "、上升存疑（时辰两端跨宫，详凭证）"
            else:
                asc = f"、上升{astro_natal.sign_name(ang.asc_sign)}"
            lines.append(f"  西洋本命盘（参·托勒密占星）：太阳"
                         f"{astro_natal.sign_name(sun.sign_idx)}、月亮"
                         f"{astro_natal.sign_name(moon.sign_idx)}{doubt}"
                         f"{asc}，{got}")
        an = getattr(self.sel, "tiyong", None)
        if an is not None:
            lines.append(f"  体用生克（梅花断法）：{an.summary()}")
        lines.append(f"  定例断辞（主断侧机断，{verdict.audit_label(self.vd)}）："
                     f"【{self.vd['verdict']}】{self.vd['action']}")
        return "\n".join(lines)

    def evidence_text(self):
        if self.primary == "event":
            return report.render_readings_compact(self.kb, self.sel)
        return zreport.render_readings_compact(self.zkb, self.sel)

    def detail_text(self):
        """卦画与盘面（--full 附录用；默认输出为省篇幅不含）。"""
        parts = []
        if self.primary == "event" and self.event_cast is not self.time_cast:
            parts.append("问语卦：")
            parts.append(report.render_cast(self.kb, self.event_cast))
            parts.append("时间卦：")
        parts.append(report.render_cast(self.kb, self.time_cast))
        if self.name_cast is not None:
            parts.append(f"姓名卦「{self.name}」：")
            parts.append(report.render_cast(self.kb, self.name_cast))
        if self.chart is not None:
            parts.append(zreport.render_chart(self.chart))
        return "\n\n".join(parts)

    def repro_text(self):
        parts = []
        if self.primary == "event" and self.event_cast is not self.time_cast:
            parts.append(report.render_repro(self.event_cast))
        parts.append(report.render_repro(self.time_cast))
        if self.name_cast is not None:
            parts.append(report.render_repro(self.name_cast))
        if self.chart is not None:
            parts.append(zreport.render_repro(self.chart))
        if self.astro is not None:
            parts.append(astro_natal.render_repro(self.astro))
        an = getattr(self.sel, "tiyong", None)
        if an is not None:
            out = ["── 体用生克凭证（确定性） " + "─" * 16]
            out.append("  法：《梅花易数》卷二体用总诀——动爻所在为用、不动为体，"
                       "八宫五行（卷一）论生克；互卦去初上取中四爻；变卦即"
                       "之卦所变之一卦；卦气依卷一卦气旺衰以问时农历月令论")
            for line in an.lines():
                out.append(f"  {line}")
            out.append("  约定：辰戌丑未月依「四季之月」条论旺衰，余月依四时；"
                       "乾坤纯卦依「乾坤无互，互其变卦」；占章之句按关系字样"
                       "机械截取，无对应字样则不取")
            if getattr(self, "li_terms", None):
                out.append(f"  占例召回：字样（{'、'.join(self.li_terms)}）"
                           f"命中 {self.li_total} 例，入语境 {len(self.li_hits)} 例"
                           "（可引不可断）")
            parts.append("\n".join(out))
        if self.desk:
            out = ["── 书桌召回（确定性） " + "─" * 18]
            out.append("  池：《紫微斗数全书·卷一》赋文诸论、十等论、"
                       "定富贵贫贱杂诸局，逐行")
            out.append(f"  规则：主断宫主星星名（问涉题材时并所涉之宫名）"
                       f"字样命中即收，依库序，每项至多 {self._DESK_CAP} 行"
                       "（超额如实标注）；只入解读语境，可引不可断")
            terms = getattr(self.sel, "desk_terms", ())
            for star, hits, total in self.desk:
                label = f"所涉之宫{star}" if star in terms else star
                out.append(f"  {label}：命中 {total} 行，"
                           f"入语境 {len(hits)} 行")
            parts.append("\n".join(out))
        if getattr(self.sel, "ju", None) is not None:
            total = zpatterns.RULE_COUNT + zpatterns.SKIP_COUNT
            out = ["── 格局判定（确定性） " + "─" * 18]
            out.append(f"  池：《全书·卷一》定富局／定贵局／定贫贱局／"
                       f"定杂局共 {total} 局")
            out.append(f"  规则：诀文自述星曜宫位条件可机判者 "
                       f"{zpatterns.RULE_COUNT} 局逐条对照盘面（判定式与"
                       "文义约定见 ALGORITHM.md 步骤 8）；认出之局入语境，"
                       "可引不可断")
            if self.sel.ju:
                for m in self.sel.ju:
                    out.append(f"  认出：{m.cat}·{m.name}——{m.basis}")
            else:
                out.append("  认出：无")
            out.append(f"  不判 {zpatterns.SKIP_COUNT} 局（宁缺，逐类缘由）：")
            for line in zpatterns.skip_lines(self.zkb):
                out.append(f"    {line}")
            parts.append("\n".join(out))
        return "\n\n".join(parts)

    def degraded_conclusion_text(self):
        """无模型解读时的结论先行：定例断辞之白话＋主断经文为理由。"""
        audited = verdict.audit_label(self.vd)
        kb = self.kb if self.primary == "event" else self.zkb
        c = kb.citation(self.vd["cite_id"])
        text = self.vd.get("quote") or c["text"]
        text = text.replace("\n", " ")
        note = self.vd["basis"]
        if len(text) > 120:   # 长文（如《论大限》全篇）节引，全文见 corpus
            text = text[:120] + "……"
            note += "；节引，全文可于 corpus 按书名查取"
        lines = [
            f"【结论】{self.vd['action']}。",
            f"（定例断辞【{self.vd['verdict']}】，{audited}；"
            "未启用大模型解读，结论直取定例）",
            "",
            f"【理由】主断经文 {c['source']}：「{text}」",
            f"（{note}）",
        ]
        d = verdict.definition(self.vd["verdict"])
        if d and self.primary == "event" and kb.has(d[1]):
            lines.append(f"（断辞之义：「{d[0]}」——{kb.citation(d[1])['source']}）")
        return "\n".join(lines)

    def render_all(self, result=None, model=None, attempts=0, full=False):
        """完整输出（结论先行）：header → 结论/断语/理由/建议 → 一览 →
        所据原文节选 →（--full 卦画盘面）→ 存证 → 凭证 → 免责声明。"""
        parts = [self.header_text(), ""]
        if result is not None:
            parts.append(report.render_interpretation(result,
                                                      self.resolve_cite))
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
                cfg, self.kb, self.question, self.event_cast, self.sel,
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
                cfg, self.kb, self.question, self.event_cast, self.sel,
                self.vd, self.first_result, self.history, ask, self.tp,
                self.contexts)
        else:
            result, _ = zllm.followup_chart(
                cfg, self.zkb, self.question, self.chart, self.sel, self.vd,
                self.first_result, self.history, ask, self.tp, self.contexts)
        self.history.append((ask, result))
        return report.render_followup(result, self.resolve_cite)

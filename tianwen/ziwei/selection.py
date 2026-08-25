"""命引擎断语选取与确定性结论（对应事引擎的 selection + verdict）。

规则选文，杜绝挑拣（DESIGN §5.4、§6.1 「卦断事，盘论人」）：
- 问命格 → 命宫主星：命宫论断文为主断，分宫格（按命宫支取行）、
  入男/女命吉凶诀（按性别取）、诸星问答为语境；另按安命宫支机取
  《卷一》得地合格诀／失陷破格诀（格诀查表，v2.5，只作语境参照）；
- 问时运 → 现行大限宫主星：入限吉凶诀为主断，《论大限十年祸福何如》
  为语境；流年二限（v2.5）：太岁与小限（《安小限诀》）所在之宫如实
  列出、相冲诸项依《论二限太岁吉凶》逐项查验，小限宫主星附入限诀为参；
- 问事分宫：问题落在具体题材（财、婚、业……）时，依关键词规则加取
  所涉之宫诸星断语（《全书·卷二》十二宫），题材宫不另出结论；
- 合参（DESIGN §6.2）：问具体事走事引擎时，命盘只以所涉之宫断语作
  「人的语境」进入解读层，不产生第二个吉凶；
- 宫无正曜依通行借对宫论（如实标注）；
- 书桌（v3 后续之召回层）：主断宫主星名记于 desk_stars，service 层
  据此自赋文格诀池机械召回候选断语入语境（可引不可断，规则进凭证）。

结论不由 LLM 发挥：
- 命格强弱由庙陷表定（庙/旺/得地为得力，利益/平和为平，不得地/落陷
  为失陷），映射规则写死；
- 时运结论直接套《论大限十年祸福何如》明文三例（星曜庙旺得地且无
  羊陀火铃空劫忌为安顺；陷地值煞为凶；余为成败不一）。
自动映射均标 audited=False，人工审定机制后续与事引擎共用。
"""

from dataclasses import dataclass, field

from ..trigrams import ZHI

MALEFICS = ("擎羊", "陀罗", "火星", "铃星", "地空", "地劫")

_GOOD = ("庙", "旺", "得地")
_BAD = ("不得地", "落陷")

#: 问事分宫：问题关键词 → 所涉之宫（顺序即优先级，第一个命中者胜）。
#: 疾厄不设——健康类问题由红线拦截，不入占断。
ASPECTS = (
    ("妻妾", ("婚", "恋", "感情", "姻缘", "桃花", "对象", "配偶", "情感")),
    ("官禄", ("事业", "工作", "职", "官运", "仕途", "功名", "学业", "考")),
    ("财帛", ("财", "钱", "收入", "积蓄", "存款", "赚")),
    ("田宅", ("房", "家宅", "田宅", "置业", "搬家", "迁居")),
    ("迁移", ("出行", "远行", "出国", "外出", "迁徙")),
    ("子女", ("子女", "孩子", "子嗣")),
    ("奴仆", ("人际", "人缘", "朋友", "同事", "下属")),
    ("兄弟", ("兄弟", "姐妹", "手足")),
    ("父母", ("父母", "双亲")),
    ("福德", ("福气", "福分", "福德", "晚年")),
)

#: 合参（§6.2）：事引擎问事类别 → 命盘所看之宫；未列者按关键词分宫，
#: 再无则取命宫。
TOPIC_PALACE = {"career": "官禄", "study": "官禄", "love": "妻妾",
                "relation": "奴仆", "travel": "迁移", "dwelling": "田宅"}


def detect_aspect(question):
    """按关键词定所问之宫 → (宫名, 命中词)；未命中 → (None, "")。"""
    for palace, keywords in ASPECTS:
        for kw in keywords:
            if kw in question:
                return palace, kw
    return None, ""


@dataclass(frozen=True)
class Reading:
    role: str
    cite_id: str
    context_ids: tuple = ()
    primary: bool = False


@dataclass
class ChartSelection:
    rule: str
    palace_name: str       # 所论之宫（命宫 / 大限所行之宫名）
    branch: str
    readings: list = field(default_factory=list)
    notes: list = field(default_factory=list)   # 借对宫等如实标注
    desk_stars: tuple = ()  # 书桌召回所依主断宫主星（ZiweiKB.desk 用）

    @property
    def primary(self):
        return next((r for r in self.readings if r.primary), None)


def _pname(palace):
    return palace.name if palace.name.endswith("宫") else palace.name + "宫"


def _tri(brightness):
    if brightness in _GOOD:
        return 1
    if brightness in _BAD:
        return -1
    return 0


def _borrow(chart, palace):
    """宫无正曜借对宫：返回（取星之宫, 是否借）。"""
    if palace.major():
        return palace, False
    opp = ZHI[(ZHI.index(palace.branch) + 6) % 12]
    return chart.palace_of_branch(opp), True


def _aspect_readings(zkb, chart, aspect, primary=True):
    """所涉之宫诸星断语（《全书·卷二》十二宫）→ (readings, notes)。

    宫总论只随首条断语作语境给一次；底本缺文如实标注。
    """
    p = chart.palace_named(aspect)
    src, borrowed = _borrow(chart, p)
    readings, notes = [], []
    if borrowed:
        notes.append(f"{_pname(p)}无正曜，借对宫主星论之（通行借宫法）")
    zonglun = zkb.gong_zonglun(aspect)
    ctx = (zonglun,) if zonglun else ()
    for s in src.major():
        cid = zkb.gong(aspect, s.name)
        if cid is None:
            notes.append(f"{s.name}入{_pname(p)}断语底本缺文，不取")
            continue
        b = s.brightness or "—"
        readings.append(Reading(
            role=f"所问之宫：{_pname(p)}（{p.branch}） {s.name}（{b}"
                 + (f"，化{s.sihua}" if s.sihua else "") + "）"
                 + ("〔借对宫〕" if borrowed else ""),
            cite_id=cid, context_ids=ctx, primary=primary))
        ctx = ()
    if not readings and zonglun:
        readings.append(Reading(
            role=f"所问之宫：{_pname(p)}（{p.branch}）宫总论"
                 + ("（本宫与对宫俱无正曜）" if borrowed and not src.major()
                    else ""),
            cite_id=zonglun, context_ids=(), primary=False))
    return readings, notes


def select_destiny(zkb, chart, aspect=None):
    """问命格：命宫主星断语；问及具体题材时加取所涉之宫（问事分宫）。"""
    ming = chart.palaces[0]
    src, borrowed = _borrow(chart, ming)
    sel = ChartSelection(
        rule="命宫主星断语（《紫微斗数全书·卷二》），庙陷依《全书》庙陷表",
        palace_name="命宫", branch=ming.branch)
    if borrowed:
        sel.notes.append("命宫无正曜，借对宫（迁移）主星论之（通行借宫法），"
                         "分宫格不取")
    if chart.shen_branch == ming.branch:
        sel.notes.append("命身同宫")
    tag = "male" if chart.gender == "男" else "female"
    for s in src.major():
        ctx = []
        if not borrowed:
            ctx.extend(zkb.ge_lines(s.name, ming.branch))
        jue = zkb.ming_jue(s.name, tag)
        if jue:
            ctx.append(jue)
        wd = zkb.wenda(s.name)
        if wd:
            ctx.append(wd)
        b = s.brightness or "—"
        sel.readings.append(Reading(
            role=f"命宫主星 {s.name}（{b}"
                 + (f"，化{s.sihua}" if s.sihua else "") + "）"
                 + ("〔借自迁移宫〕" if borrowed else ""),
            cite_id=zkb.ming(s.name), context_ids=tuple(ctx), primary=True))
    sel.desk_stars = tuple(s.name for s in src.major())
    _add_gejue(zkb, sel, ming.branch)
    _add_aspect(zkb, chart, sel, aspect)
    return sel


def _add_gejue(zkb, sel, branch):
    """格诀查表（v2.5 格局识别之查表半）：按安命宫支机取《卷一》
    得地合格诀与失陷破格诀。诀文所言星曜须与盘面对照，故只作语境
    参照（primary=False），不改结论单源。"""
    hege = zkb.hege(branch)
    poge = zkb.poge_lines(branch)
    if not hege and not poge:
        return
    sel.notes.append(f"格诀按安命宫支（{branch}）机取（《卷一》得地合格诀"
                     "／失陷破格诀）：诀中所言星曜庙陷须与盘面对照，合者方论")
    if hege:
        sel.readings.append(Reading(
            role=f"安命（{branch}）得地合格诀", cite_id=hege, primary=False))
    for cid in poge:
        sel.readings.append(Reading(
            role=f"安命（{branch}）失陷破格诀", cite_id=cid, primary=False))


def _add_aspect(zkb, chart, sel, aspect):
    """问事分宫：加取所涉之宫断语。题材宫不另出结论（结论仍单源）。"""
    if not aspect or aspect == "命宫":
        return
    readings, notes = _aspect_readings(zkb, chart, aspect)
    if not readings:
        return
    sel.notes.append(f"所问涉{aspect}，加取{aspect}宫诸星断语"
                     "（《全书·卷二》十二宫；题材宫只入解读，不另出结论）")
    sel.notes.extend(notes)
    sel.readings.extend(readings)


def select_fortune(zkb, chart, at, aspect=None):
    """问时运：现行大限宫主星入限诀 + 卷三大限论；问及具体题材时
    加取所涉之宫（问事分宫）。"""
    p, age = chart.current_daxian(at)
    notes = []
    if p is None:
        p = chart.palaces[0]
        notes.append(f"虚岁 {age}，未及起限之岁（{chart.ju_num} 岁起限）或"
                     f"已出十二限，以命宫论之")
    src, borrowed = _borrow(chart, p)
    sel = ChartSelection(
        rule="现行大限宫主星入限吉凶诀（《紫微斗数全书·卷二》），"
             "限势依《卷三·论大限十年祸福何如》",
        palace_name=p.name, branch=p.branch)
    sel.notes.extend(notes)
    sel.notes.append(f"现行大限：{p.daxian[0]}–{p.daxian[1]} 虚岁，"
                     f"行{_pname(p)}（{p.branch}），现虚岁 {age}"
                     f"（{'顺行' if chart.daxian_forward else '逆行'}）")
    if borrowed:
        sel.notes.append(f"{_pname(p)}无正曜，借对宫主星论之（通行借宫法）")
    for s in src.major():
        ctx = []
        wd = zkb.wenda(s.name)
        if wd:
            ctx.append(wd)
        b = s.brightness or "—"
        sel.readings.append(Reading(
            role=f"大限{_pname(p)} {s.name}（{b}"
                 + (f"，化{s.sihua}" if s.sihua else "") + "）入限"
                 + ("〔借对宫〕" if borrowed else ""),
            cite_id=zkb.ming_jue(s.name, "xian"),
            context_ids=tuple(ctx), primary=True))
    sel.desk_stars = tuple(s.name for s in src.major())
    _add_aspect(zkb, chart, sel, aspect)
    sel.readings.append(Reading(
        role="限势总论", cite_id=zkb.lun("daxian"),
        context_ids=(), primary=False))
    _add_liunian(zkb, chart, sel, at, age)
    return sel


def _chong(a, b):
    """地支六冲（对宫相冲）。"""
    return (ZHI.index(a) - ZHI.index(b)) % 12 == 6


def _add_liunian(zkb, chart, sel, at, age):
    """流年二限（v2.5）：太岁（当年年支）与小限（《安小限诀》）所在之宫
    如实列出，相冲诸项依《论二限太岁吉凶》明文逐项查验；小限宫主星附
    入限诀为参。结论仍单源（依《论大限》三例），流年只入解读。"""
    tai = chart.year_branch(at)
    xiao = chart.xiaoxian_branch(age)
    tp, xp = chart.palace_of_branch(tai), chart.palace_of_branch(xiao)
    sel.notes.append(
        f"流年：太岁在{tai}（{_pname(tp)}），小限在{xiao}（{_pname(xp)}）"
        f"——小限依《安小限诀》本生年{chart.lunar.year_zhi}支起宫、"
        f"男顺女逆逐年一宫，太岁即当年年支；虚岁 {age}")
    # 《论二限太岁吉凶》「又看太岁冲大限小限，太岁冲羊陀七杀」——逐项查验
    chongs = []
    if _chong(tai, sel.branch):
        chongs.append(f"太岁冲大限（{sel.branch}）")
    if _chong(tai, xiao):
        chongs.append(f"太岁冲小限（{xiao}）")
    for name in ("擎羊", "陀罗", "七杀"):
        p = chart.star_palace(name)
        if p is not None and _chong(tai, p.branch):
            chongs.append(f"太岁冲{name}（{p.branch}）")
    sel.notes.append("太岁相冲查验（《论二限太岁吉凶》明文诸项）："
                     + ("、".join(chongs) if chongs else "俱无冲"))
    have = {r.cite_id for r in sel.readings}
    for s in xp.major():
        cid = zkb.ming_jue(s.name, "xian")
        if cid is None or cid in have:
            continue
        b = s.brightness or "—"
        sel.readings.append(Reading(
            role=f"小限{_pname(xp)} {s.name}（{b}"
                 + (f"，化{s.sihua}" if s.sihua else "") + "）入限（流年之参）",
            cite_id=cid, context_ids=(), primary=False))
    sel.readings.append(Reading(
        role="二限太岁总说", cite_id=zkb.lun("erxian"),
        context_ids=(), primary=False))


def select_context(zkb, chart, tp, question):
    """合参语境（DESIGN §6.2）：问具体事走事引擎、且已有生辰时，
    命盘只作「人的语境」进入解读层——不出第二个吉凶。

    取与所问之事相应之宫的诸星断语（按事类映射，无则按关键词分宫）；
    仍无则取命宫主星论断文。返回 ChartSelection，可为空 readings。
    """
    aspect = TOPIC_PALACE.get(tp.key) or detect_aspect(question)[0]
    sel = ChartSelection(
        rule="盘论人，仅作语境：命盘断语只说明君之秉性禀赋，"
             "不出第二结论，吉凶仍依卦断",
        palace_name=aspect or "命宫", branch=chart.palaces[0].branch)
    sel.notes.append(f"依生辰命盘：命宫在{chart.ming_branch}，"
                     f"{chart.wuxing_ju}，{chart.yinyang}")
    if aspect:
        readings, notes = _aspect_readings(zkb, chart, aspect, primary=False)
        if readings:
            sel.notes.append(f"所问属{tp.name}，取{aspect}宫诸星断语"
                             "（《全书·卷二》十二宫）")
            sel.notes.extend(notes)
            sel.readings.extend(readings)
            return sel
    ming = chart.palaces[0]
    src, borrowed = _borrow(chart, ming)
    for s in src.major():
        cid = zkb.ming(s.name)
        if cid is None:
            continue
        b = s.brightness or "—"
        sel.readings.append(Reading(
            role=f"命宫主星 {s.name}（{b}）"
                 + ("〔借自迁移宫〕" if borrowed else ""),
            cite_id=cid, context_ids=(), primary=False))
    if sel.readings:
        sel.notes.append("所问无专属之宫，以命宫主星论断文作语境")
    return sel


def _stars_desc(stars):
    return "、".join(f"{s.name}{s.brightness or ''}"
                    + (f"化{s.sihua}" if s.sihua else "") for s in stars)


def decide_destiny(chart):
    """命格结论：命宫主星庙陷定强弱（DESIGN §5.4）。"""
    ming = chart.palaces[0]
    src, borrowed = _borrow(chart, ming)
    majors = src.major()
    tris = [_tri(s.brightness) for s in majors]
    basis = f"命宫（{ming.branch}）主星："
    if borrowed:
        basis = f"命宫（{ming.branch}）无正曜，借对宫主星："
    basis += _stars_desc(majors) if majors else "对宫亦无正曜"
    if not majors:
        v, a = "弱", "命宫与对宫俱无正曜，根基浮泛，宜依人成事、不宜自恃"
    elif 1 in tris and -1 in tris:
        v, a = "强弱互见", "命宫主星得失并见，长短互济，宜用其长、避其短"
    elif 1 in tris:
        v, a = "强", "命宫主星得地，秉性可恃，宜扬长任事"
    elif -1 in tris:
        v, a = "弱", "命宫主星失陷，根基欠力，宜藏锋养实、不宜逞强"
    else:
        v, a = "平", "命宫主星平和，不偏不倚，成事在人"
    if borrowed and majors:
        a += "（借宫而论，其力较本宫为浮）"
    cite = ("ziwei:2:ming:" + _first_seg(majors)) if majors \
        else "ziwei:1:wenda:ziwei"
    return {"verdict": v, "action": a, "basis": basis + "；依《全书》庙陷表",
            "cite_id": cite, "audited": False}


def decide_fortune(chart, at):
    """时运结论：套《论大限十年祸福何如》明文三例。"""
    p, age = chart.current_daxian(at)
    if p is None:
        p = chart.palaces[0]
    src, borrowed = _borrow(chart, p)
    majors = src.major()
    tris = [_tri(s.brightness) for s in majors]
    sha = [s for s in p.stars
           if s.name in MALEFICS or s.sihua == "忌"]
    basis = (f"大限行{_pname(p)}（{p.branch}）：主星 "
             + (_stars_desc(majors) if majors else "无（借对宫亦无）")
             + ("〔借对宫〕" if borrowed else "")
             + ("；煞忌：" + _stars_desc(sha) if sha else "；无煞忌同宫"))
    if majors and all(t == 1 for t in tris) and not sha:
        v, a = "顺", "限宫星曜庙旺无煞，此十年之势安顺，宜进取"
    elif (-1 in tris or not majors) and sha:
        v, a = "危", "限宫星陷值煞，此限多阻，宜守不宜攻，慎防成败"
    else:
        v, a = "中", "限内吉凶相杂，成败不一，宜逐事斟酌、谨慎而行"
    return {"verdict": v, "action": a,
            "basis": basis + "；依《卷三·论大限十年祸福何如》",
            "cite_id": "ziwei:3:daxian", "audited": False}


def _first_seg(majors):
    from .knowledge import STAR_SEG
    return STAR_SEG[majors[0].name]

"""格局判定器：《紫微斗数全书·卷一》定富贵贫贱诸局按星曜组合认局。

诀文全部在库（ziwei:1:ju:*，共 49 局；v3.4 入库，本模块接线）。原则：

- 只判诀文自述星曜宫位条件、且所需盘面事实排盘引擎已安者——逐局
  转码为判定式（下方 _RULES，每条注明原文），认出之局连同盘面依据
  （何星何宫）如实列出；
- 不可机判者宁缺，逐局录明缘由（_SKIPPED，进凭证）：诀作「见前批注」
  无判据者、文义两可不强解者、定杂局论限运盛衰非静态星曜组合者
  （涉空亡与天刑诸局已随天刑天姚与截路旬中空亡安讫解锁）；
- 认出之局只入解读语境（可引不可断），不改结论单源（ALGORITHM.md 五）。

文义约定（今法约定，ALGORITHM.md 步骤 8 如实标注）：
- 夹＝紧邻两宫各一；拱＝三合二宫（本宫支 +4、+8）；向＝对宫；冲＝对宫；
- 「同守身命」解作分守身、命二宫（武曲廉贞依安星诀永不同宫）；
- 「反背」依《全书》庙陷表失陷（不得地／落陷）为准；
- 「逢巨暗」承同列「生不逢时」句例（「命坐空亡逢廉贞」之「逢」即命宫
  见其星）解作巨门守命；
- 「遇吉」解作同宫见吉曜（辅弼昌曲魁钺禄存天马之属）；
- 「庙旺」从严只取庙、旺两级；
- 「四杀守身命临陷地」承「同守身命」句例解作四杀之星分守身、命二宫
  且所见皆陷（四星俱守则羊陀庙陷互斥不可能，命身同宫无以分守，
  均不成局）；
- 「坐空亡」「落空亡」＝其宫之支属截路空亡或旬中空亡（其一即坐）；
- 「同临身命」（刑囚夹印）依字面解作二星同宫而其宫为命宫或身宫——
  天刑廉贞依安星诀可同宫，无须如武贞「同守身命」改读分守；
- 「两杀」（禄逢两杀）即空劫：禄存之宫坐空亡，又见地空或地劫。

个别局依安星诀星序实不可能成局，仍照诀逐字转码——不合则不出，不因
不可能而删诀：财荫夹印之武梁永不夹相；荫印拱身之「身临田宅」依
《安身命例》身宫恒落命、妻妾、财帛、迁移、官禄、福德六宫（命身支序
恒差偶数），永不临田宅。
"""

from dataclasses import dataclass

from ..trigrams import ZHI

_GOOD2 = ("庙", "旺")            # 「庙旺」从严
_BAD = ("不得地", "落陷")        # 「陷地」「反背」所取（与 selection 同）


@dataclass(frozen=True)
class JuMatch:
    cite_id: str
    name: str        # 局名（自 source 末段取，不另转录）
    cat: str         # 定富局 / 定贵局 / 定贫贱局
    basis: str       # 盘面依据（判定式所核之事实）


class _Facts:
    """判定所用之盘面事实（星之所在、亮度、命身、各宫之支、空亡）。"""

    def __init__(self, chart):
        self.chart = chart
        self.pos, self.bright = {}, {}
        for p in chart.palaces:
            i = ZHI.index(p.branch)
            for s in p.stars:
                self.pos[s.name] = i
                self.bright[s.name] = s.brightness
        self.ming = ZHI.index(chart.ming_branch)
        self.shen = ZHI.index(chart.shen_branch)
        self.pb = {p.name: ZHI.index(p.branch) for p in chart.palaces}
        # 空亡：支序 → 标记文字（截路空亡／旬中空亡，兼坐则并列）
        self.kong = {}
        for i, br in enumerate(ZHI):
            marks = chart.kong_marks(br)
            if marks:
                self.kong[i] = "、".join(marks)

    def palace_desc(self, i):
        p = self.chart.palace_of_branch(ZHI[i])
        return f"{ZHI[i]}（{p.name}宫）" if not p.name.endswith("宫") \
            else f"{ZHI[i]}（{p.name}）"

    def flank(self, a, b, x):
        """夹：星 a、b 各居 x 前后两邻。"""
        return {self.pos[a], self.pos[b]} == {(x + 1) % 12, (x - 1) % 12}

    def trine(self, a, b, x):
        """拱：星 a、b 俱在 x 之三合二宫。"""
        tri = {(x + 4) % 12, (x + 8) % 12}
        return self.pos[a] in tri and self.pos[b] in tri


def _at(f, star, x):
    return f.pos.get(star) == x


# ── 判定式（每条注明诀文原文；返回盘面依据或 None） ─────────────────────


def _cai_yin_jia_yin(f):
    # 「财荫夹印 相守命武梁来夹是也，田宅宫亦然。」
    for pal in ("命宫", "田宅"):
        x = f.pb[pal]
        if _at(f, "天相", x) and f.flank("武曲", "天梁", x):
            return (f"天相守{pal}（{ZHI[x]}），武曲在{ZHI[f.pos['武曲']]}、"
                    f"天梁在{ZHI[f.pos['天梁']]}来夹")
    return None


def _ri_yue_jia_cai(f):
    # 「日月夹财 武守命日月来夹是也，财帛宫亦然。」
    for pal in ("命宫", "财帛"):
        x = f.pb[pal]
        if _at(f, "武曲", x) and f.flank("太阳", "太阴", x):
            return (f"武曲守{pal}（{ZHI[x]}），太阳在{ZHI[f.pos['太阳']]}、"
                    f"太阴在{ZHI[f.pos['太阴']]}来夹")
    return None


def _cai_lu_jia_ma(f):
    # 「财禄夹马 马守命武禄来夹是也，逢生旺尤妙。」
    x = f.ming
    if _at(f, "天马", x) and f.flank("武曲", "禄存", x):
        return (f"天马守命（{ZHI[x]}），武曲在{ZHI[f.pos['武曲']]}、"
                f"禄存在{ZHI[f.pos['禄存']]}来夹")
    return None


def _yin_yin_gong_shen(f):
    # 「荫印拱身 身临田宅梁相拱冲是也，勿坐空亡。」（拱＝三合、冲＝对宫；
    # 依《安身命例》身宫恒落命妻财迁官福六宫、永不临田宅——照诀转码，
    # 不合则不出，不因不可能而删诀）
    x = f.pb["田宅"]
    if f.shen != x or x in f.kong:
        return None
    spots = {(x + 4) % 12, (x + 8) % 12, (x + 6) % 12}
    if f.pos["天梁"] in spots and f.pos["天相"] in spots:
        return (f"身宫临田宅（{ZHI[x]}）不坐空亡，天梁在{ZHI[f.pos['天梁']]}、"
                f"天相在{ZHI[f.pos['天相']]}拱冲")
    return None


def _ri_yue_zhao_bi(f):
    # 「日月照璧 日月临田宅宫是也，喜居墓库。」
    x = f.pb["田宅"]
    if _at(f, "太阳", x) and _at(f, "太阴", x):
        return f"太阳太阴俱临田宅宫（{ZHI[x]}）"
    return None


def _jin_can_guang_hui(f):
    # 「金灿光辉 太阳单守，命在午宫是也。」
    ming = f.chart.palaces[0]
    if f.ming == ZHI.index("午") and [s.name for s in ming.major()] == ["太阳"]:
        return "命宫在午，太阳单守"
    return None


def _ri_yue_jia_ming(f):
    # 「日月夹命 不坐空亡遇逢本宫有吉星是也。」（局名之义：太阳太阴
    # 夹命宫；命宫不坐空亡；「逢」承句例＝本宫见星，吉星取吉曜之属）
    x = f.ming
    if x in f.kong or not f.flank("太阳", "太阴", x):
        return None
    lucky = [s.name for s in f.chart.palaces[0].stars if s.kind == "lucky"]
    if lucky:
        return (f"太阳在{ZHI[f.pos['太阳']]}、太阴在{ZHI[f.pos['太阴']]}"
                f"夹命（{ZHI[x]}），命宫不坐空亡，见吉星{('、'.join(lucky))}")
    return None


def _ri_chu_fu_sang(f):
    # 「日出扶桑 日在卯守命是也，守官禄宫亦然。」
    mao = ZHI.index("卯")
    for pal in ("命宫", "官禄"):
        if f.pb[pal] == mao and _at(f, "太阳", mao):
            return f"太阳在卯守{pal}"
    return None


def _yue_luo_hai_gong(f):
    # 「月落亥宫 月在亥守命是也，又名月朗天门。」
    if f.ming == ZHI.index("亥") and _at(f, "太阴", f.ming):
        return "太阴在亥守命"
    return None


def _yue_sheng_cang_hai(f):
    # 「月生沧海 月在子宫守田宅是也。」
    if f.pb["田宅"] == ZHI.index("子") and _at(f, "太阴", f.pb["田宅"]):
        return "太阴在子守田宅"
    return None


def _fu_bi_gong_zhu(f):
    # 「辅弼拱主 紫微守命二星来拱是也，夹之亦然。」
    x = f.ming
    if not _at(f, "紫微", x):
        return None
    if f.trine("左辅", "右弼", x):
        return (f"紫微守命（{ZHI[x]}），左辅在{ZHI[f.pos['左辅']]}、"
                f"右弼在{ZHI[f.pos['右弼']]}三合来拱")
    if f.flank("左辅", "右弼", x):
        return (f"紫微守命（{ZHI[x]}），左辅在{ZHI[f.pos['左辅']]}、"
                f"右弼在{ZHI[f.pos['右弼']]}来夹")
    return None


def _jun_chen_qing_hui(f):
    # 「君臣庆会 紫微左右同守命是也，更会相武阴妙上。」
    x = f.ming
    if _at(f, "紫微", x) and _at(f, "左辅", x) and _at(f, "右弼", x):
        return f"紫微与左辅右弼同守命宫（{ZHI[x]}）"
    return None


def _cai_yin_jia_lu(f):
    # 「财印夹禄 禄守命梁相来夹是也，入财亦然。」
    for pal in ("命宫", "财帛"):
        x = f.pb[pal]
        if _at(f, "禄存", x) and f.flank("天梁", "天相", x):
            return (f"禄存守{pal}（{ZHI[x]}），天梁在{ZHI[f.pos['天梁']]}、"
                    f"天相在{ZHI[f.pos['天相']]}来夹")
    return None


def _zuo_gui_xiang_gui(f):
    # 「坐贵向贵 谓魁钺在命迭相坐拱是也。」（向＝对宫）
    x, opp = f.ming, (f.ming + 6) % 12
    for a, b in (("天魁", "天钺"), ("天钺", "天魁")):
        if _at(f, a, x) and _at(f, b, opp):
            return f"{a}坐命（{ZHI[x]}），{b}在对宫（{ZHI[opp]}）相向"
    return None


def _ma_tou_dai_jian(f):
    # 「马头带剑 谓马有刃是也不是居午格。」（诀明言非「居午」之格，
    # 取天马擎羊同度；诀未限宫位，如实列所在之宫）
    if f.pos.get("天马") == f.pos.get("擎羊"):
        return f"天马与擎羊（刃）同度于{f.palace_desc(f.pos['天马'])}"
    return None


def _xing_qiu_jia_yin(f):
    # 「刑囚夹印 天刑廉贞同临身命主武勇之人。」（「同临身命」依字面：
    # 二星同宫而其宫为命宫或身宫——天刑廉贞可同宫，无须改读分守）
    x = f.pos["廉贞"]
    if f.pos.get("天刑") != x or x not in (f.ming, f.shen):
        return None
    which = "命宫" if x == f.ming else "身宫"
    if f.ming == f.shen == x:
        which = "命身同宫"
    return f"天刑与廉贞（囚）同临{which}（{ZHI[x]}）"


def _tan_huo_xiang_feng(f):
    # 「贪火相逢 谓二星守命同居庙旺是也。」
    x = f.ming
    if (_at(f, "贪狼", x) and _at(f, "火星", x)
            and f.bright["贪狼"] in _GOOD2 and f.bright["火星"] in _GOOD2):
        return (f"贪狼（{f.bright['贪狼']}）火星（{f.bright['火星']}）"
                f"同守命宫（{ZHI[x]}）")
    return None


def _wu_qu_shou_yuan(f):
    # 「武曲守垣 武守命卯宫是也，余不是。」
    if f.ming == ZHI.index("卯") and _at(f, "武曲", f.ming):
        return "武曲守命于卯宫"
    return None


def _quan_lu_sheng_feng(f):
    # 「权禄生逢 二星守命庙旺是也，陷不是。」
    lu, quan = f.chart.sihua["禄"], f.chart.sihua["权"]
    x = f.ming
    if (_at(f, lu, x) and _at(f, quan, x)
            and f.bright[lu] in _GOOD2 and f.bright[quan] in _GOOD2):
        return (f"化禄（{lu}·{f.bright[lu]}）化权（{quan}·{f.bright[quan]}）"
                f"同守命宫（{ZHI[x]}）")
    return None


def _yang_ren_ru_miao(f):
    # 「羊刃入庙 辰戍丑未守命遇吉是也。」（遇吉＝命宫同见吉曜）
    x = f.ming
    if ZHI[x] not in "辰戌丑未" or not _at(f, "擎羊", x):
        return None
    lucky = [s.name for s in f.chart.palaces[0].stars if s.kind == "lucky"]
    if lucky:
        return f"擎羊在{ZHI[x]}守命（庙），同宫见吉曜{('、'.join(lucky))}"
    return None


def _jin_yu_fu_jia(f):
    # 「金舆扶驾 紫微守命前后有日月来夹是也。」
    x = f.ming
    if _at(f, "紫微", x) and f.flank("太阳", "太阴", x):
        return (f"紫微守命（{ZHI[x]}），太阳在{ZHI[f.pos['太阳']]}、"
                f"太阴在{ZHI[f.pos['太阴']]}来夹")
    return None


def _sheng_bu_feng_shi(f):
    # 「生不逢时 命坐空亡逢廉贞是也。」（坐空亡＝命宫支属截路或旬中空亡）
    x = f.ming
    if x in f.kong and _at(f, "廉贞", x):
        return f"命宫（{ZHI[x]}）坐{f.kong[x]}，廉贞守命"
    return None


def _lu_feng_liang_sha(f):
    # 「禄逢两杀 禄坐空亡又逢空劫杀星是也。」（禄＝禄存；「两杀」即
    # 空劫；「逢」承句例＝其宫见其星：禄存之宫坐空亡，又见地空或地劫）
    x = f.pos["禄存"]
    if x not in f.kong:
        return None
    kj = [s for s in ("地空", "地劫") if f.pos[s] == x]
    if kj:
        return (f"禄存之宫（{f.palace_desc(x)}）坐{f.kong[x]}，"
                f"又逢{('、'.join(kj))}")
    return None


def _ma_luo_kong_wang(f):
    # 「马落空亡 马既落亡虽禄冲会无用主奔波。」
    x = f.pos["天马"]
    if x in f.kong:
        return f"天马之宫（{f.palace_desc(x)}）落{f.kong[x]}"
    return None


def _ri_yue_cang_hui(f):
    # 「日月藏辉 日月反背又逢巨暗是也。」（反背依庙陷表失陷；「逢」承
    # 「生不逢时 命坐空亡逢廉贞」句例，解作巨门守命）
    if (f.bright["太阳"] in _BAD and f.bright["太阴"] in _BAD
            and _at(f, "巨门", f.ming)):
        return (f"太阳（{f.bright['太阳']}）太阴（{f.bright['太阴']}）"
                f"反背，又巨门（暗）守命（{ZHI[f.ming]}）")
    return None


def _cai_yu_qiu_chou(f):
    # 「财与囚仇 武贞同守身命是也。」（分守身、命二宫）
    if {f.pos["武曲"], f.pos["廉贞"]} == {f.ming, f.shen}:
        return (f"武曲在{ZHI[f.pos['武曲']]}、廉贞（囚）在"
                f"{ZHI[f.pos['廉贞']]}，分守身命二宫")
    return None


def _yi_sheng_gu_pin(f):
    # 「一生孤贫 谓破守命星陷地是也。」
    if _at(f, "破军", f.ming) and f.bright["破军"] in _BAD:
        return f"破军守命（{ZHI[f.ming]}）临陷地（{f.bright['破军']}）"
    return None


def _jun_zi_zai_ye(f):
    # 「君子在野 谓四杀守身命而言临陷地是也。」（承同列「财与囚仇
    # 武贞同守身命」句例：四杀之星分守身、命二宫，所见皆临陷地；
    # 四星俱守则羊陀庙陷互斥不可能，命身同宫无以分守，均不成局）
    if f.ming == f.shen:
        return None
    sha = ("擎羊", "陀罗", "火星", "铃星")
    seen = {f.ming: [], f.shen: []}
    for s in sha:
        if f.pos[s] in seen:
            if f.bright[s] not in _BAD:
                return None          # 身命所见之杀有不陷者，不成局
            seen[f.pos[s]].append(s)
    if seen[f.ming] and seen[f.shen]:
        return ("四杀" + "、".join(
            f"{s}在{ZHI[f.pos[s]]}（{f.bright[s]}）"
            for names in seen.values() for s in names) + "，分守身命临陷地")
    return None


def _liang_chong_hua_gai(f):
    # 「两重华盖 谓禄存化禄坐命遇空劫是也。」
    x = f.ming
    lu = f.chart.sihua["禄"]
    if not (_at(f, "禄存", x) and _at(f, lu, x)):
        return None
    kong = [s for s in ("地空", "地劫") if _at(f, s, x)]
    if kong:
        return (f"禄存与化禄（{lu}）坐命（{ZHI[x]}），"
                f"同宫遇{('、'.join(kong))}")
    return None


#: 可机判之局：cite_id → 判定式（局名、类别自库中 source 取，不另转录）。
_RULES = (
    ("ziwei:1:ju:fu:1", _cai_yin_jia_yin),
    ("ziwei:1:ju:fu:2", _ri_yue_jia_cai),
    ("ziwei:1:ju:fu:3", _cai_lu_jia_ma),
    ("ziwei:1:ju:fu:4", _yin_yin_gong_shen),
    ("ziwei:1:ju:fu:5", _ri_yue_zhao_bi),
    ("ziwei:1:ju:fu:6", _jin_can_guang_hui),
    ("ziwei:1:ju:gui:1", _ri_yue_jia_ming),
    ("ziwei:1:ju:gui:2", _ri_chu_fu_sang),
    ("ziwei:1:ju:gui:3", _yue_luo_hai_gong),
    ("ziwei:1:ju:gui:4", _yue_sheng_cang_hai),
    ("ziwei:1:ju:gui:5", _fu_bi_gong_zhu),
    ("ziwei:1:ju:gui:6", _jun_chen_qing_hui),
    ("ziwei:1:ju:gui:7", _cai_yin_jia_lu),
    ("ziwei:1:ju:gui:9", _zuo_gui_xiang_gui),
    ("ziwei:1:ju:gui:10", _ma_tou_dai_jian),
    ("ziwei:1:ju:gui:15", _xing_qiu_jia_yin),
    ("ziwei:1:ju:gui:17", _tan_huo_xiang_feng),
    ("ziwei:1:ju:gui:18", _wu_qu_shou_yuan),
    ("ziwei:1:ju:gui:22", _quan_lu_sheng_feng),
    ("ziwei:1:ju:gui:23", _yang_ren_ru_miao),
    ("ziwei:1:ju:gui:27", _jin_yu_fu_jia),
    ("ziwei:1:ju:pinjian:1", _sheng_bu_feng_shi),
    ("ziwei:1:ju:pinjian:2", _lu_feng_liang_sha),
    ("ziwei:1:ju:pinjian:3", _ma_luo_kong_wang),
    ("ziwei:1:ju:pinjian:4", _ri_yue_cang_hui),
    ("ziwei:1:ju:pinjian:5", _cai_yu_qiu_chou),
    ("ziwei:1:ju:pinjian:6", _yi_sheng_gu_pin),
    ("ziwei:1:ju:pinjian:7", _jun_zi_zai_ye),
    ("ziwei:1:ju:pinjian:8", _liang_chong_hua_gai),
)

#: 不可机判之局：cite_id → 缘由（宁缺；凭证如实列出）。
_SKIPPED = (
    ("ziwei:1:ju:gui:8", "「马前有禄印星同宫」文义两可，不强解"),
    ("ziwei:1:ju:gui:11", "诀作「见前批注」，无判据"),
    ("ziwei:1:ju:gui:12", "诀作「见前批注」，无判据"),
    ("ziwei:1:ju:gui:13", "诀作「见前批注」，无判据"),
    ("ziwei:1:ju:gui:14", "诀作「见前批注」，无判据"),
    ("ziwei:1:ju:gui:16", "诀作「见前批注」，无判据"),
    ("ziwei:1:ju:gui:19", "诀作「见前批注」，无判据"),
    ("ziwei:1:ju:gui:20", "诀作「见前批注」，无判据"),
    ("ziwei:1:ju:gui:21", "诀作「见前批注」，无判据"),
    ("ziwei:1:ju:gui:24", "诀作「见前批注」，无判据"),
    ("ziwei:1:ju:gui:25", "诀作「见前批注」，无判据"),
    ("ziwei:1:ju:gui:26", "诀作「见前批注」，无判据"),
    ("ziwei:1:ju:za:1", "定杂局论限运盛衰，非静态星曜组合"),
    ("ziwei:1:ju:za:2", "定杂局论限运盛衰，非静态星曜组合"),
    ("ziwei:1:ju:za:3", "定杂局论限运盛衰，非静态星曜组合"),
    ("ziwei:1:ju:za:4", "定杂局论限运盛衰，非静态星曜组合"),
    ("ziwei:1:ju:za:5", "定杂局论限运盛衰，非静态星曜组合"),
    ("ziwei:1:ju:za:6", "定杂局论限运盛衰，非静态星曜组合"),
    ("ziwei:1:ju:za:7", "定杂局论限运盛衰，非静态星曜组合"),
    ("ziwei:1:ju:za:8", "定杂局论限运盛衰，非静态星曜组合"),
)

RULE_COUNT = len(_RULES)
SKIP_COUNT = len(_SKIPPED)


def _name_cat(zkb, cite_id):
    parts = zkb.record(cite_id)["source"].split("·")
    return parts[-1], parts[-2]


def judge(zkb, chart):
    """认局：逐条判定式对照盘面 → [JuMatch]（依库序，确定性）。"""
    f = _Facts(chart)
    out = []
    for cid, fn in _RULES:
        assert zkb.has(cid), f"格局判定所据不存在：{cid}"
        basis = fn(f)
        if basis:
            name, cat = _name_cat(zkb, cid)
            out.append(JuMatch(cite_id=cid, name=name, cat=cat, basis=basis))
    return out


def skip_lines(zkb):
    """不判之局及缘由（凭证用），按缘由归并。"""
    by_reason = {}
    for cid, reason in _SKIPPED:
        assert zkb.has(cid), f"格局判定所据不存在：{cid}"
        by_reason.setdefault(reason, []).append(_name_cat(zkb, cid)[0])
    return [f"{'、'.join(names)}：{reason}"
            for reason, names in by_reason.items()]

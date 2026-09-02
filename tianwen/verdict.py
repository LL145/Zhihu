"""断辞 → 结论映射（确定性代码，LLM 不得改判）。

自动提取主断经文中的断辞（吉、凶、悔、吝、厉、无咎等），按明示优先级
归为结论类别。审定记两处（audited 如实标注，方法与轮次录
data/PROOFREADING.md）：订正个案记 data/verdict_overrides.json，按
cite_id 覆盖；审定确认名单记 data/verdict_audit.json，名单内维持
自动提取结果而 audited 置真。两处皆无则为待审草案（audited=False）。
"""

import json
from pathlib import Path

OVERRIDES_PATH = Path(__file__).parent / "data" / "verdict_overrides.json"
AUDIT_PATH = Path(__file__).parent / "data" / "verdict_audit.json"

# 匹配顺序即优先级：长词在前，防止「无不利」被拆成「不利」、「悔亡」被拆成「悔」。
# 类别: pos2 大善之辞 / pos 善断 / posl 轻善（悔亡类）/ neut 无咎类 /
#       negs 轻戒（悔吝咎）/ risk 厉 / neg2 凶 / dneg 不宜行动之辞 /
#       None 消耗不计（非断辞之复合词，防其中单字被误拆为断辞）
_TOKENS = [
    ("亨于", None),   # 「王用亨于西山」：亨乃享祀之动辞，非断辞（2026-08 审定）
    ("无不利", "pos"), ("无攸利", "dneg"), ("不利", "dneg"),
    ("元吉", "pos2"), ("大吉", "pos2"),
    ("悔亡", "posl"), ("无悔", "posl"), ("无祗悔", "posl"), ("有悔", "negs"),
    ("无咎", "neut"), ("何咎", "neut"), ("匪咎", "neut"),
    ("何其咎", "neut"), ("无大咎", "neut"),
    ("勿用", "dneg"), ("勿恤", "posl"),
    ("凶", "neg2"), ("厉", "risk"), ("吝", "negs"), ("悔", "negs"), ("咎", "negs"),
    ("吉", "pos"), ("亨", "pos"), ("利", "pos"),
]

_ACTIONS = {
    "吉": "宜进，可行其事",
    "条件": "吉凶系于经文所著之条件，须依原文所示情形而定",
    "凶": "不宜进，宜守静待时",
    "危": "有风险，非必要不动",
    "谨": "可行而有代价，宜慎行",
    "忌": "此时不宜行动",
    "平": "行之无过，顺其自然",
    "未著断辞": "经文未著吉凶断辞，以象传文意为参",
}


def extract_tokens(text: str):
    """按优先级提取断辞，已匹配部分即被消耗，不重复计入。

    类别为 None 的词条只消耗不计入（非断辞之复合词，如「亨于」）。"""
    found = []
    s = text
    for token, cat in _TOKENS:
        while token in s:
            if cat is not None:
                found.append((token, cat))
            s = s.replace(token, "□", 1)
    return found


def classify(tokens):
    cats = {cat for _, cat in tokens}
    pos_major = "pos2" in cats or "pos" in cats
    if "neg2" in cats and pos_major:
        return "条件"
    if "neg2" in cats:
        return "凶"
    if "risk" in cats:
        return "谨" if (pos_major or "posl" in cats or "neut" in cats) else "危"
    if "dneg" in cats:
        # 显否定式与善辞或无咎类并见即对举之句（不利为寇利御寇、利西南
        # 不利东北、甘临无攸利既忧之无咎），吉凶系于所行，归「条件」，
        # 不得相互吞没（2026-08 抽样审定＋全量审定所见）
        return "条件" if (pos_major or "neut" in cats) else "忌"
    if pos_major and "negs" in cats:
        return "谨"
    if pos_major or "posl" in cats:
        return "吉"
    if "neut" in cats and "negs" not in cats:
        return "平"
    if "negs" in cats or "neut" in cats:
        return "谨"
    return "未著断辞"


#: 断辞之义（《系辞上传》第三章，xici:shang:3 逐字子串）：按类别附于定例
XICI_DEFINITION = {
    "吉": "吉凶者，言乎其失得也",
    "凶": "吉凶者，言乎其失得也",
    "条件": "吉凶者，言乎其失得也",
    "谨": "悔吝者，言乎其小疵也",
    "平": "无咎者，善补过也",
}
XICI_CITE = "xici:shang:3"

#: 梅花体用生克（tiyong.py）之定例：总诀明文映射，不经断辞字样提取
_TIYONG_VERDICT = {
    "用生体": "吉", "体克用": "吉", "体用比和": "吉",
    "体生用": "谨", "用克体": "凶",
}
_TIYONG_ACTIONS = {
    "用生体": "有进益之喜：所谋之事反来助我，宜进",
    "体克用": "诸事吉：我能制事，可成（占章多言成迟，须耐）",
    "体用比和": "百事顺遂：彼此相协，可成",
    "体生用": "有耗失之患：为事所耗，宜慎、量力而行",
    "用克体": "诸事凶：事反制我，不宜进",
}


def definition(verdict_name):
    """断辞类别之经典定义 →（句, cite_id）或 None。"""
    s = XICI_DEFINITION.get(verdict_name)
    return (s, XICI_CITE) if s else None


def audit_label(vd):
    """一览与结论行之审定标注。"""
    if vd.get("kind") == "tiyong":
        return "总诀明文映射"
    return "人工审定" if vd["audited"] else "自动提取，待人工审定"


def decide_tiyong(an) -> dict:
    """梅花体用生克之定例：用卦与体之关系按《体用总诀》明文直接映射
    （「体克用，诸事吉；用克体，诸事凶……」），占章之句并记于依据。"""
    from .tiyong import WUXING
    rel = an.rel_yong
    basis = (f"体{an.ti}{WUXING[an.ti]}、用{an.yong}{WUXING[an.yong]}："
             f"{rel}；总诀明文「{an.zongjue}」")
    if an.zhan_clause:
        basis += f"；{an.zhan_title}「{an.zhan_clause}」"
    return {
        "cite_id": "meihua:2:tiyong", "verdict": _TIYONG_VERDICT[rel],
        "action": _TIYONG_ACTIONS[rel], "basis": basis, "audited": True,
        "kind": "tiyong", "quote": an.zongjue,
    }


def _load_overrides():
    if OVERRIDES_PATH.exists():
        return json.loads(OVERRIDES_PATH.read_text("utf-8"))
    return {}


def _load_confirmed():
    if AUDIT_PATH.exists():
        return frozenset(json.loads(AUDIT_PATH.read_text("utf-8"))["confirmed"])
    return frozenset()


def decide(cite_id: str, text: str) -> dict:
    """对主断经文给出确定性结论。"""
    overrides = _load_overrides()
    if cite_id in overrides:
        o = overrides[cite_id]
        return {
            "cite_id": cite_id, "verdict": o["verdict"], "action": o["action"],
            "basis": o.get("note", "人工审定"), "audited": True,
            "kind": "duanci", "quote": text,
        }
    tokens = extract_tokens(text)
    verdict = classify(tokens)
    basis = "断辞：" + "、".join(t for t, _ in tokens) if tokens else "经文未著断辞"
    audited = cite_id in _load_confirmed()
    if audited:
        basis += "；审定确认（2026-08 全量审定）"
    return {
        "cite_id": cite_id, "verdict": verdict, "action": _ACTIONS[verdict],
        "basis": basis, "audited": audited, "kind": "duanci", "quote": text,
    }

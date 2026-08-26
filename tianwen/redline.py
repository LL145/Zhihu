"""红线拦截：医疗、投资、法律、寿夭类问题一律婉拒（宁可错杀）。"""

from . import hanzi

_CATEGORIES = {
    "医疗健康": ["病", "癌", "肿瘤", "医院", "手术", "吃药", "服药", "诊断", "治疗",
               "怀孕", "备孕", "体检"],
    "投资理财": ["股票", "股市", "炒股", "基金", "期货", "币", "比特", "彩票",
               "赌", "投资", "理财", "借贷", "放贷"],
    "法律纠纷": ["官司", "诉讼", "起诉", "仲裁", "判刑", "坐牢"],
    "寿夭生死": ["寿命", "活多久", "什么时候死", "死期", "阳寿"],
}

_CRISIS = ["自杀", "轻生", "不想活", "了结自己"]

_CRISIS_MESSAGE = (
    "从你的问题里，我感到你现在可能非常难受。这不是占卜能回答的事，"
    "也请不要独自扛着——可以拨打全国统一心理援助热线 12356（24小时），"
    "或与你信任的人谈谈。"
)


def check(question: str):
    """返回 None 表示放行；否则返回婉拒文案。

    比对前繁体输入归一为简体（hanzi.t2s）——红线宁可错杀，
    不容因繁体写法绕过。
    """
    question = hanzi.t2s(question)
    for kw in _CRISIS:
        if kw in question:
            return _CRISIS_MESSAGE
    for category, keywords in _CATEGORIES.items():
        for kw in keywords:
            if kw in question:
                return (
                    f"这个问题涉及{category}，属于本产品不作占断的范围——"
                    f"此类事项应求诸专业人士，而非古籍占法。"
                    f"若你想问的是其中的心态、抉择方向等一般性事项，"
                    f"可换一种问法（避开「{kw}」等具体事项）再试。"
                )
    return None

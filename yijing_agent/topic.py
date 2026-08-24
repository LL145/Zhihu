"""问事分类（分类断法）：确定性关键词规则，决定解读落点。

类别依设计文档 §7.2：事业、学业、情感、人际、出行、居所、决策抉择、
命格、时运、其他。每类附「解读落点」指引——这是占法指引而非典籍原文，
只用于约束 LLM 解读的着力方向，不进入引文、不影响 verdict。

命格 / 时运 属命理范畴（v2 紫微命引擎）。v1 只有事引擎，此两类照常
起卦作断，但 engine_hint 标为 chart，调用方据此向用户说明局限。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    key: str
    name: str
    note: str
    engine_hint: str  # "event" | "chart"
    matched: str      # 命中的关键词；未命中（其他）为空串
    source: str = "rule"   # rule=关键词规则 | llm=占者判类 | user=用户指定


# 顺序即优先级：时运最前——问「×运/运势」即是问时运之消长，纵带具体
# 题材（事业运、财运）也属命理范畴，题材由问事分宫处理（ziwei.selection）；
# 其后具体事类，决策抉择兜底在「其他」之前。
# 「换工作是否合适」须落在事业而非决策抉择。
_RULES = (
    ("fortune", "时运", "chart",
     ("运势", "时运", "运气", "财运", "官运", "桃花运", "考运", "运程",
      "流年", "今年运", "近期运", "最近运"),
     "时运消长之问：以本卦断近期之势的顺逆消长与用力方向；"
     "不铺陈祸福细目，不作长期预言。"),
    ("career", "事业", "event",
     ("工作", "跳槽", "升职", "加薪", "离职", "入职", "创业", "事业",
      "面试", "职位", "职场", "转行", "生意", "项目", "合伙", "合作",
      "合同", "谈判", "开店"),
     "谋为进取之事：断此事当下可行与否、阻力何在、宜进宜守；"
     "建议落到具体的进、守、缓、变，不泛谈心态。"),
    ("study", "学业", "event",
     ("考试", "考研", "考公", "考编", "高考", "升学", "学业", "论文",
      "读研", "读博", "留学", "录取", "答辩", "考证"),
     "求学应试之事：断用功方向与临事之势、宜攻宜缓；"
     "不得断具体分数、名次、录取与否等事实结果。"),
    ("love", "情感", "event",
     ("恋爱", "表白", "分手", "复合", "感情", "婚姻", "结婚", "离婚",
      "相亲", "对象", "姻缘", "求婚", "喜欢的人", "脱单"),
     "婚恋情感之事：断两情向背之势、当下宜主动宜静守；"
     "语气尤须克制，不许诺结果，不评判对方。"),
    ("relation", "人际", "event",
     ("朋友", "同事", "领导", "上司", "室友", "邻居", "矛盾", "争执",
      "和好", "人际", "相处", "误会", "闹翻"),
     "人际交往之事：断亲疏顺逆之势与致和之道；"
     "建议落在自处与待人的分寸，不指摘他人。"),
    ("travel", "出行", "event",
     ("出行", "旅行", "旅游", "出差", "远行", "出国", "回家", "行程",
      "航班", "动身", "启程"),
     "出行动身之事：断行止顺阻、宜早宜缓；建议落在行程取舍与时机。"),
    ("dwelling", "居所", "event",
     ("搬家", "租房", "买房", "换房", "装修", "迁居", "居所", "住处",
      "落户", "定居"),
     "居所迁置之事：断迁与守之宜、迟速之机；建议落在迁守取舍与时机。"),
    ("destiny", "命格", "chart",
     ("命格", "命运", "八字", "命好", "命苦", "天生", "一生", "终身",
      "什么命"),
     "命格禀赋之问，本属命理范畴（紫微命引擎，后续版本）。"
     "本卦只能断「当下所处之势」，解读须明言不论终身、只论眼前。"),
    ("choice", "决策抉择", "event",
     ("是否", "该不该", "要不要", "还是", "选择", "选哪", "犹豫",
      "纠结", "抉择", "可不可以", "能不能"),
     "两端取舍之事：断进退取舍之宜，须明确指向其中一端，"
     "或指明当下不宜决断的缘由——不得两可。"),
)

_DEFAULT = Topic(
    key="other", name="其他", engine_hint="event", matched="",
    note="就所问之事直断可行与否、顺阻所在；建议落到可执行的行动。")


#: (key, 中文名) 全表——界面下拉与占者判类共用。分类法本身即正统之绪：
#: 《梅花易数》十八占、六爻按类取用神、紫微十二宫皆是定类而占。
CATEGORIES = tuple((key, name) for key, name, _h, _k, _n in _RULES) \
    + (("other", "其他"),)


def classify(question: str) -> Topic:
    """按规则顺序取第一个命中的类别；未命中归「其他」。确定性，无 LLM。"""
    for key, name, hint, keywords, note in _RULES:
        for kw in keywords:
            if kw in question:
                return Topic(key=key, name=name, note=note,
                             engine_hint=hint, matched=kw)
    return _DEFAULT


def by_key(key: str, source: str = "user") -> Topic:
    """按类别键直接构造 Topic——用户指定或占者判类时用。"""
    for k, name, hint, _kw, note in _RULES:
        if k == key:
            return Topic(key=k, name=name, note=note, engine_hint=hint,
                         matched="", source=source)
    if key == "other":
        return Topic(key="other", name=_DEFAULT.name, note=_DEFAULT.note,
                     engine_hint="event", matched="", source=source)
    raise KeyError(key)

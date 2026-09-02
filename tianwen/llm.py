"""解读生成层：调用 OpenRouter（OpenAI 兼容接口），只解释、不改判。

生成结果须通过 validator 的逐字引文校验；三次不过则抛出 InterpreterError，
调用方降级为「仅原文 + 结论」的无解读模式。

多占法并用（ALGORITHM.md 五）：主断侧文本立断，语境侧文本（姓名卦、
紫微盘等）以 ContextBlock 传入，只作"人的语境"，校验器保证断语所据
落在主断侧——吉凶只有一个出处。

多轮追问（followup）不重新起卦：同一份【所据文本】、同一 verdict，
每轮回答同样过校验闸门。
"""

import json
from collections import namedtuple

import requests

from .config import DEFAULT_REASONING_EFFORT
from .validator import validate, validate_followup

#: 语境块：title 如「姓名卦（论问者之位）」；notes 为说明行；
#: items 为 [(cite_id, 出处名, 原文)]。语境文本可引不可断。
ContextBlock = namedtuple("ContextBlock", "title notes items")

_SYSTEM = """你是一名依《周易》行占的占者。起卦、占法选文皆循古法定例由程序完成；\
断与释，由你任之。你会收到：用户所问之事、起卦结果、依古法定例选定的经文原文\
（各有 cite_id 编号）、以及自经文断辞字样机取的定例断辞（你的对照基准）。

硬性规则：
1. 只可依据【所据文本】【注疏】与【语境】中给出的原文行断与解读，不得引入其中没有\
的任何"典籍内容"或古语。【问事类别与解读落点】是占法指引而非典籍原文，只用于确定\
方向，不得当作原文引用。注疏是后人（王弼）对经文的解释：引用时须标其 cite_id 并\
表明是注家之言，不得与经文混同。《文言》《说卦》为孔门传文，属经传原文可引；体用\
取象（说卦）只作解读取象之资。
2. 引文必须逐字照抄给定原文的文字，并标注其 cite_id。
3. 断由你任之（judgment 字段）：如古之占者，衡所据之文，就用户所问下占断——\
一至两句，明言吉凶宜忌之倾向（用传统断辞字汇：吉、凶、悔、吝、厉、无咎、宜、不宜等，\
不得模棱两可），句末以 [cite_id] 标注所据。断语至少须据一处标〔主断〕之文：梅花法\
即《梅花易数》体用总诀与所问占章之明文（【体用生克】所列体用、互变之关系即其所指），\
爻辞、彖象、文言可并引为佐；朱子法则为主断经文。【语境】文本、注家之言与取象皆不得\
单独立断。【定例断辞】是主断明文的机械映射（梅花法按总诀「体克用，诸事吉；用克体，\
诸事凶……」直取；朱子法按经文断辞字样提取），作你的对照基准：从之，则说明其所以然；\
异断（如体虽受生而卦气衰、互变俱克），则必须明言所据之文与其理，无据不得异断。
3a. 事之起、中、终：总诀言「用为事之端，互为事之中间，变为事之终」「用吉变凶者，\
先吉后凶；用凶变吉者，先凶后吉」——理由宜循用→互→变之序讲此事如何起、中途如何、\
终局如何，每一步据【体用生克】所列之关系与总诀「某卦生体／克体」之具象句（原文有\
「公门之喜」「文书之忧」等语者，转述其象并标 cite_id），有故事、有着落。动爻爻辞\
为易辞之参：与体用之断相合则相印证，不合则如占例「易辞不吉矣，以卦论之」，以体用\
为断而说明易辞之戒。
4. 说人话，如老练占者当面与问者说话：结论与理由须有画面、有比方，善用卦象之象\
作喻（如噬嗑即「咬开硬骨而得金矢」——难中取利），落到问者生活的具体场景；忌公文腔、\
报告腔、术语罗列。可言势之成色与档次，但须有着落：原文有富贵贫贱、高下等第之语者，\
可用白话转述其档次并标出处（如「衣食宽裕有余，大贵则未足」）；以象引申亦可言成色\
（「利艰贞」是辛苦财、「未光」则未至大盛）；不得自造原文没有的档次，不得许诺具体\
数额、时限或必然结果。断语与解读不得软化辞气以媚问者——不得把「凶」说成\
「略有不顺」；紧扣用户所问之事及其类别落点，落到可执行的层面；语气如实，\
不恐吓、不故弄玄虚。
5. 各【语境】块（姓名卦、紫微命盘断语等）只作"人的语境"：仅可用于说明占断落在\
此人之位、秉性禀赋上如何着力；不得据此加强、削弱或反转占断，不得由它得出第二个\
吉凶，不得把语境文本与主断经文混同。参照不是弃置：解读宜旁征博引——理由中\
择要参引语境原文以佐主断之势，主次分明。引用其原文同样须逐字照抄并标注 cite_id。
6. 只输出一个 JSON 对象（不要 markdown 代码块、不要任何其他文字），字段：
   - conclusion: 白话结论，一至两句，直接回答用户所问——像当面告诉朋友，
     开门见山、有人味、有成色感（依第 4 条，须有着落），纯白话，
     不用古文字汇，不带 [cite_id] 标注（字符串）
   - judgment: 传统断语，一至两句，句末以 [cite_id] 标注所据（字符串）
   - reasons: 解释理由，两至四段：引用古籍原文（逐字）并用白话把原文之象
     讲活、说明为何得出上述结论——主断之理落在经传之文，注疏与语境之文
     宜择要参引为佐（旁征博引，主次分明），每段末以 [cite_id] 标注
     该段依据（字符串）
   - advice: 具体建议，2 到 4 条，落到问者日常做得到的事，说人话（字符串数组）；
     其一宜取本卦大象传「君子以……」之义化为可做之事并标其 cite_id
   - quotes: 你实际引用的原文句子，数组，每项 {"text": 逐字原文, "cite_id": 出处编号}"""

_FOLLOWUP_RULES = """解读已完成，用户将就本卦继续追问。追问回答的硬性规则：
1. 不重新起卦：仍只可依据前述给定的原文作答；占断已下，不得于追问中\
变更或软化。
2. 引用原文须逐字照抄并标注 cite_id；追问不必强行引经，无合适原文可不引。
3. 追问若超出本卦所据文本可答的范围（另问一事、追问具体祸福细节、要求预言事实结果），\
如实说明须另占或无法由本卦文本得出，不得杜撰。
4. 只输出一个 JSON 对象（不要 markdown 代码块、不要任何其他文字），字段：
   - answer: 针对追问的回答，一至两段（字符串）
   - quotes: 实际引用的原文，数组，每项 {"text": 逐字原文, "cite_id": 出处编号}，可为空数组"""


class InterpreterError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or []


def _allowed_texts(kb, selection):
    allowed = {}
    for r in selection.readings:
        allowed[r.cite_id] = kb.citation(r.cite_id)["text"]
        for cid in r.context_ids:
            allowed[cid] = kb.citation(cid)["text"]
    # 注疏层：所选经文对应的王弼注一并纳入可引文本（不改判，只作语境）；
    # 文言传（孔门传文，经传原文）挂乾坤经文单元，随选文自动附入
    for scid in list(allowed):
        c = kb.commentary(scid)
        if c:
            allowed[c["cite_id"]] = c["text"]
        w = kb.wenyan(scid)
        if w:
            allowed[w["cite_id"]] = w["text"]
    return allowed


def context_texts(contexts):
    """全部语境块的 {cite_id: 原文}——纳入可引集合（可引不可断）。"""
    texts = {}
    for blk in contexts or ():
        for cid, _source, text in blk.items:
            texts[cid] = text
    return texts


def render_context_blocks(lines, contexts):
    """把语境块渲染进 payload（事引擎与命引擎共用）。"""
    for blk in contexts or ():
        lines.append("")
        lines.append(f"【语境·{blk.title}】（可引不可断：宜择要参引为佐，"
                     "不得据以改动结论，不得出第二个吉凶）")
        for note in blk.notes:
            lines.append(f"※ {note}")
        for cid, source, text in blk.items:
            lines.append(f"[{cid}] {source}：{text}")


def _payload(question, cast, selection, verdict, allowed_texts, kb, topic=None,
             contexts=()):
    lines = [f"【所问之事】{question}", ""]
    if topic is not None:
        lines.append("【问事类别与解读落点】（占法指引，非典籍原文，不得作为引文）")
        lines.append(f"{topic.name}：{topic.note}")
        lines.append("")
    lines.append("【起卦结果】")
    for k, v in cast.reproducibility.items():
        lines.append(f"{k}：{v}")
    lines.append("")
    lines.append(f"【占法】{selection.rule}")
    an = getattr(selection, "tiyong", None)
    if an is not None:
        lines.append("")
        lines.append("【体用生克】（机断结果，非原文：所据须引下列总诀与占章之"
                     "原文并标 cite_id）")
        for ln in an.lines():
            lines.append(f"- {ln}")
    lines.append("")
    primary_ids = getattr(selection, "primary_ids", frozenset())
    lines.append("【所据文本】（断语所据必须落在以下原文上；标〔主断〕者为"
                 "断语必据之文）")
    for cid, text in allowed_texts.items():
        if not cid.startswith("wangbi:"):
            tag = "〔主断〕" if cid in primary_ids else ""
            lines.append(f"[{cid}] {tag}{kb.citation(cid)['source']}：{text}")
    notes = [(cid, text) for cid, text in allowed_texts.items()
             if cid.startswith("wangbi:")]
    if notes:
        lines.append("")
        lines.append("【注疏】（王弼注，后人解释；引用须标 cite_id，须与经文区分，"
                     "不得据以改动结论）")
        for cid, text in notes:
            lines.append(f"[{cid}] {kb.citation(cid)['source']}：{text}")
    render_context_blocks(lines, contexts)
    lines.append("")
    lines.append(f"【定例断辞（机断，占断之对照基准）】{verdict['verdict']}——{verdict['action']}")
    lines.append(f"（其据：主断经文 [{verdict['cite_id']}] 之断辞字样。"
                 "从之须明其所以然，异断须明据）")
    return "\n".join(lines)


def _parse_json(text):
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json"):
            s = s[4:]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("输出中未找到 JSON 对象")
    return json.loads(s[start:end + 1])


def _reasoning(cfg):
    """OpenRouter 统一 reasoning 参数：qwen/glm 等深思模型不加限常思考
    数分钟致超时，缺省 effort=low 收紧思考预算；none 关闭思考（纯思考
    模型忽略之），空串则不发送该字段（兼容不识它的 OpenAI 兼容端点）；
    非思考模型忽略此参数。"""
    v = cfg.get("reasoning_effort", DEFAULT_REASONING_EFFORT)
    if v in ("low", "medium", "high"):
        return {"reasoning": {"effort": v}}
    if v == "none":
        return {"reasoning": {"enabled": False}}
    return {}


def _request(cfg, messages, timeout, temperature=0.4):
    resp = requests.post(
        f"{cfg['base_url'].rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
            "X-Title": "Tianwen",
        },
        json={"model": cfg["model"], "messages": messages,
              "temperature": temperature, **_reasoning(cfg)},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise InterpreterError(f"OpenRouter 请求失败 HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]["content"]


def _attempt_loop(cfg, messages, allowed, check, max_attempts, timeout, fail_msg):
    """请求→解析→校验，不过则带原因重试。messages 会被原地追加。"""
    last_errors = []
    for attempt in range(1, max_attempts + 1):
        content = _request(cfg, messages, timeout)
        try:
            result = _parse_json(content)
        except (ValueError, json.JSONDecodeError) as e:
            last_errors = [f"JSON 解析失败: {e}"]
        else:
            last_errors = check(result, allowed)
            if not last_errors:
                return result, attempt
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content":
                         "你的输出未通过校验，问题如下，请改正后重新输出完整 JSON：\n- "
                         + "\n- ".join(last_errors)})
    raise InterpreterError(fail_msg, last_errors)


def classify_topic(cfg, question, timeout=30):
    """占者判类：配有模型即为判类默认（判类三级之第二级，service.resolve_topic）。

    温度取 0；返回类别键，失败或键不在表内返回 None（调用方回落关键词
    规则）。判类只定选文框架，不作任何占断。
    """
    from . import topic as topic_mod
    cats = "\n".join(f"- {k}：{name}——{note}"
                     for k, name, note in topic_mod.CATALOG)
    messages = [
        {"role": "system",
         "content": "你是占前司事者：只判定用户所问属于哪一类问事，不作任何占断"
                    "或回答。只输出一个 JSON 对象 {\"key\": \"<类别键>\"}，"
                    "键限于用户给出的列表；无法归类或语义不明用 other。"
                    "辨界：问「××运／运势」（财运、事业运、桃花运等）纵带"
                    "具体题材皆归 fortune；问具体谋为之事（如换工作是否合适）"
                    "归其事类；choice 只收无具体题材的两端取舍。"},
        {"role": "user",
         "content": f"类别（键：名——解读落点）：\n{cats}\n\n所问：{question}"},
    ]
    try:
        content = _request(cfg, messages, timeout, temperature=0)
        key = str(_parse_json(content).get("key", ""))
    except Exception:          # 判类失败不致命：网络/解析异常一律回落规则结果
        return None
    return key if key in dict(topic_mod.CATEGORIES) else None


def interpret(cfg, kb, question, cast, selection, verdict, topic=None,
              contexts=(), max_attempts=3, timeout=120):
    """返回 (result, attempts)。校验三次不过抛 InterpreterError。

    contexts: 语境块序列（ContextBlock），可引不可断（ALGORITHM.md 五）。
    """
    allowed = _allowed_texts(kb, selection)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",
         "content": _payload(question, cast, selection, verdict, allowed, kb,
                             topic, contexts)},
    ]
    primary = frozenset(allowed)
    must = getattr(selection, "primary_ids", None) or None   # 主断必据之文
    allowed = {**allowed, **context_texts(contexts)}
    check = lambda r, a: validate(r, a, primary, must)   # noqa: E731
    return _attempt_loop(cfg, messages, allowed, check, max_attempts, timeout,
                         "解读三次未通过引文校验，已拒绝输出")


def followup(cfg, kb, question, cast, selection, verdict, first_result,
             history, ask, topic=None, contexts=(), max_attempts=3, timeout=120):
    """就同一卦追问。history 为 [(往轮追问, 往轮回答 dict), ...]。返回 (result, attempts)。"""
    allowed = _allowed_texts(kb, selection)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",
         "content": _payload(question, cast, selection, verdict, allowed, kb,
                             topic, contexts)},
        {"role": "assistant", "content": json.dumps(first_result, ensure_ascii=False)},
    ]
    first = True
    for prev_ask, prev_result in history:
        prefix = _FOLLOWUP_RULES + "\n\n" if first else ""
        messages.append({"role": "user", "content": f"{prefix}【追问】{prev_ask}"})
        messages.append({"role": "assistant",
                         "content": json.dumps(prev_result, ensure_ascii=False)})
        first = False
    prefix = _FOLLOWUP_RULES + "\n\n" if first else ""
    messages.append({"role": "user", "content": f"{prefix}【追问】{ask}"})
    allowed = {**allowed, **context_texts(contexts)}
    return _attempt_loop(cfg, messages, allowed, validate_followup, max_attempts,
                         timeout, "追问回答三次未通过引文校验，已拒绝输出")

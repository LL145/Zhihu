"""引文校验器：LLM 输出展示前的最后一道确定性闸门。

- 每条引文去标点后须逐字包含于其所标 cite_id 的原文之中；
- 断语（judgment）必须以 [cite_id] 标注所据——无据不断；
- 断语所据须落在主断侧文本（primary 集合）上，且须含经传之文
  （王弼注、说卦取象不得单独立断）——语境侧文本不得立断，
  结构上保证多占法并用而吉凶只有一个出处（ALGORITHM.md 五）；
- 理由（reasons）中方括号标注的 cite_id 须属于本次给定的文本集合；
- 白话结论（conclusion）须为纯白话：不得夹带 [cite_id] 标注；
- 必填字段齐全。任何一条不过即拒绝本次输出。

结构宽容：多段 reasons 常被模型输出为字符串数组，语义等同，合并收下；
其余字段类型不符一律作校验错误反馈（重试时模型据以改正）——校验器
对任何形状的输出都只返回错误列表，不得抛异常。
"""

import re

_CJK = re.compile(r"[^㐀-鿿]")
_CITE_MARK = re.compile(r"\[([a-z]+:[0-9]+(?::[a-z0-9]+)*)\]")

REQUIRED_FIELDS = ("conclusion", "judgment", "reasons", "advice", "quotes")

#: 不得单独立断的文本前缀（注家之言与取象之资）
_NO_STANDALONE = ("wangbi", "shuogua")


def normalize(text: str) -> str:
    """仅保留汉字，去除标点、引号、空白——「逐字」以此为准。"""
    return _CJK.sub("", text)


def _check_quotes(quotes, allowed, errors):
    for i, q in enumerate(quotes):
        if not isinstance(q, dict) or not isinstance(q.get("text"), str) \
                or not isinstance(q.get("cite_id"), str):
            errors.append(f"quotes[{i}] 须含字符串字段 text 与 cite_id")
            continue
        cid = q["cite_id"]
        if cid not in allowed:
            errors.append(f"quotes[{i}] 的 cite_id 不在本次给定文本之内: {cid}")
            continue
        nq = normalize(q["text"])
        if not nq:
            errors.append(f"quotes[{i}] 引文为空")
        elif nq not in normalize(allowed[cid]):
            errors.append(f"quotes[{i}] 与 {cid} 原文不符（须逐字照抄）: {q['text']}")


def _check_cite_marks(text, allowed, errors, where):
    for cid in _CITE_MARK.findall(text):
        if cid not in allowed:
            errors.append(f"{where}中标注的 cite_id 不在本次给定文本之内: {cid}")


def validate(result: dict, allowed: dict, primary=None) -> list:
    """allowed: {cite_id: 原文}；primary: 主断侧 cite_id 集合（None 视同
    全部 allowed）。返回错误列表，空列表为通过。"""
    errors = []
    if isinstance(result.get("reasons"), list) and result["reasons"] \
            and all(isinstance(p, str) for p in result["reasons"]):
        result["reasons"] = "\n\n".join(result["reasons"])
    for f in REQUIRED_FIELDS:
        if f not in result or not result[f]:
            errors.append(f"缺少字段或字段为空: {f}")
    for f in ("conclusion", "judgment", "reasons"):
        if f in result and result[f] and not isinstance(result[f], str):
            errors.append(f"{f} 须为单个字符串，不得是数组或对象")
    if errors:
        return errors

    if not isinstance(result["quotes"], list) or not result["quotes"]:
        return ["quotes 须为非空数组"]
    if not isinstance(result["advice"], list) \
            or not all(isinstance(a, str) for a in result["advice"]):
        return ["advice 须为字符串数组"]
    if _CITE_MARK.search(result["conclusion"]):
        errors.append("白话结论（conclusion）须为纯白话，不得夹带 [cite_id] 标注")

    _check_quotes(result["quotes"], allowed, errors)
    marks = _CITE_MARK.findall(result["judgment"])
    if not marks:
        errors.append("断语（judgment）必须以 [cite_id] 标注所据原文——无据不断")
    else:
        pool = allowed if primary is None else primary
        if not any(m in pool and m.split(":")[0] not in _NO_STANDALONE
                   for m in marks):
            errors.append("断语所据须落在主断侧经传原文上——语境侧文本、"
                          "王弼注与说卦取象皆不得单独立断")
    _check_cite_marks(result["judgment"], allowed, errors, "断语")
    _check_cite_marks(result["reasons"], allowed, errors, "理由")
    return errors


def validate_followup(result: dict, allowed: dict) -> list:
    """追问回答的校验：answer 必填；quotes 须为数组但可为空（追问未必需引文）。"""
    errors = []
    if not isinstance(result.get("answer"), str) or not result.get("answer"):
        errors.append("缺少字段或字段为空: answer")
    if not isinstance(result.get("quotes"), list):
        errors.append("quotes 须为数组（可为空数组）")
    if errors:
        return errors

    _check_quotes(result["quotes"], allowed, errors)
    _check_cite_marks(result["answer"], allowed, errors, "回答")
    return errors

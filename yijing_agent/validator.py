"""引文校验器：LLM 输出展示前的最后一道确定性闸门。

- 每条引文去标点后须逐字包含于其所标 cite_id 的原文之中；
- 解读中方括号标注的 cite_id 须属于本次给定的文本集合；
- 必填字段齐全。任何一条不过即拒绝本次输出。
"""

import re

_CJK = re.compile(r"[^㐀-鿿]")
_CITE_MARK = re.compile(r"\[([a-z]+:[0-9]+(?::[a-z0-9]+)*)\]")

REQUIRED_FIELDS = ("translation", "interpretation", "advice", "quotes")


def normalize(text: str) -> str:
    """仅保留汉字，去除标点、引号、空白——「逐字」以此为准。"""
    return _CJK.sub("", text)


def validate(result: dict, allowed: dict) -> list:
    """allowed: {cite_id: 原文}。返回错误列表，空列表为通过。"""
    errors = []
    for f in REQUIRED_FIELDS:
        if f not in result or not result[f]:
            errors.append(f"缺少字段或字段为空: {f}")
    if errors:
        return errors

    if not isinstance(result["quotes"], list) or not result["quotes"]:
        return ["quotes 须为非空数组"]
    if not isinstance(result["advice"], list):
        return ["advice 须为数组"]

    for i, q in enumerate(result["quotes"]):
        if not isinstance(q, dict) or "text" not in q or "cite_id" not in q:
            errors.append(f"quotes[{i}] 须含 text 与 cite_id")
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

    for cid in _CITE_MARK.findall(result["interpretation"]):
        if cid not in allowed:
            errors.append(f"解读中标注的 cite_id 不在本次给定文本之内: {cid}")
    return errors

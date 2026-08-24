"""命引擎终端呈现：十二宫命盘图、所据断语、流派约定与复现凭证。

结论（render_verdict）与免责声明沿用事引擎 report 的同名实现。
"""

from ..trigrams import ZHI

_BR_ABBR = {"庙": "庙", "旺": "旺", "得地": "得", "利益": "利",
            "平和": "平", "不得地": "不", "落陷": "陷", "": ""}

_CELL_W = 20   # 每宫格显示列宽（汉字占 2 列）
_CELL_H = 4

# 终端盘面布局（传统方位）：
#   巳 午 未 申
#   辰 〔中〕 酉
#   卯 〔宫〕 戌
#   寅 丑 子 亥
_GRID = (("巳", "午", "未", "申"),
         ("辰", None, None, "酉"),
         ("卯", None, None, "戌"),
         ("寅", "丑", "子", "亥"))


def _w(s):
    return sum(2 if "⺀" <= ch <= "￿" else 1 for ch in s)


def _pad(s, width):
    s = str(s)
    while _w(s) > width:
        s = s[:-1]
    return s + " " * (width - _w(s))


def _star_label(s):
    lbl = s.name + _BR_ABBR.get(s.brightness, "")
    if s.sihua:
        lbl += f"({s.sihua})"
    return lbl


def _cell_lines(palace):
    labels = [_star_label(s) for s in palace.stars]
    line1 = " ".join(labels[:2])
    line2 = " ".join(labels[2:5]) + ("…" if len(labels) > 5 else "")
    name = palace.name + ("·身" if palace.is_body else "")
    line3 = f"{name} {palace.gz}"
    line4 = f"限{palace.daxian[0]}-{palace.daxian[1]}"
    return [line1, line2, line3, line4]


def _center_lines(chart):
    return [
        "",
        f" {chart.wuxing_ju}　{chart.yinyang}",
        f" 命宫在{chart.ming_branch}　身宫在{chart.shen_branch}",
        f" 大限{'顺' if chart.daxian_forward else '逆'}行，"
        f"{chart.ju_num} 岁起限",
        "",
        f" {chart.lunar.description}",
        f" （公历 {chart.solar_desc}）",
        "",
    ]


def render_chart(chart):
    by_branch = {p.branch: p for p in chart.palaces}
    center = _center_lines(chart)
    sep = "+" + "+".join(["-" * _CELL_W] * 4) + "+"
    out = [sep]
    for row_i, row in enumerate(_GRID):
        lines = [""] * _CELL_H
        for col_i, br in enumerate(row):
            if br is None:
                if col_i == 1:   # 中区两格并作一栏，宽度双倍加分隔符
                    for k in range(_CELL_H):
                        c = center[(row_i - 1) * _CELL_H + k]
                        lines[k] += "|" + _pad(c, _CELL_W * 2 + 1)
                continue
            cell = _cell_lines(by_branch[br])
            for k in range(_CELL_H):
                lines[k] += "|" + _pad(" " + cell[k], _CELL_W)
        out.extend(l + "|" for l in lines)
        out.append(sep)
    return "\n".join(out)


def _reading_lines(zkb, sel):
    out = []
    for note in sel.notes:
        out.append(f"  ※ {note}")
    for r in sel.readings:
        c = zkb.citation(r.cite_id)
        star = "◆" if r.primary else "◇"
        out.append(f"  {star} {r.role}")
        out.append(f"    {c['source']}：{c['text']}")
        for cid in r.context_ids:
            ctx = zkb.citation(cid)
            out.append(f"      · {ctx['source']}：{ctx['text']}")
    return out


def render_readings(zkb, sel):
    return "\n".join([f"── 所据断语（{sel.rule}） " + "─" * 4]
                     + _reading_lines(zkb, sel))


def render_context(zkb, sel):
    """合参语境（DESIGN §6.2）：命盘断语只作语境，不出第二结论。"""
    return "\n".join([f"── 合参语境（{sel.rule}） " + "─" * 4]
                     + _reading_lines(zkb, sel))


def render_repro(chart):
    out = ["── 排盘凭证（可复现） " + "─" * 20]
    out.append(f"  生辰：{chart.solar_desc}（公历）→ {chart.lunar.description}")
    out.append(f"  性别：{chart.gender}（{chart.yinyang}，大限"
               f"{'顺' if chart.daxian_forward else '逆'}行）")
    out.append("  流派约定（分歧处已显式选定，见下；可用任意通行排盘工具交叉核对，"
               "分歧点或有出入）：")
    for c in chart.conventions:
        out.append(f"    - {c}")
    out.append("  安星规则均出《紫微斗数全书·卷二》安星诸诀，逐条注于源码。")
    return "\n".join(out)

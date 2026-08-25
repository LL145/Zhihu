"""卦象的纯函数运算：爻值 → 本卦/之卦/互卦。

爻值采用四营数：6 老阴（动）、7 少阳、8 少阴、9 老阳（动），自下而上。
"""


def lines_to_binary(lines):
    """六爻爻值 → 本卦爻画（1 阳 0 阴，自下而上）。"""
    return [1 if v in (7, 9) else 0 for v in lines]


def moving_positions(lines):
    """动爻位置（1-6，自下而上）。老阳 9、老阴 6 为动。"""
    return [i + 1 for i, v in enumerate(lines) if v in (6, 9)]


def zhi_binary(lines):
    """之卦爻画：动爻阴阳互变。"""
    out = []
    for v in lines:
        if v == 9:
            out.append(0)
        elif v == 6:
            out.append(1)
        else:
            out.append(1 if v == 7 else 0)
    return out


def hu_binary(binary):
    """互卦爻画：二三四爻为下互，三四五爻为上互。"""
    b = list(binary)
    return [b[1], b[2], b[3], b[2], b[3], b[4]]

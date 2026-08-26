"""从 OpenCC 字典生成繁→简字级归一表（检索层用）。

藏书正文均为简体（各导入脚本已经 OpenCC 转换或底本本简），繁体检索词
若不归一必落空。本表供 corpus 检索层把检索词与单元文两侧同规整——
**只用于检索与摘要定位，引文校验（validator）不经此表**：引文仍须
逐字照抄库文原字，繁体引文照旧不过闸门。

来源：opencc-python-reimplemented（requirements-dev 已有）随包字典
（BYVoid/OpenCC 项目数据，Apache License 2.0）：

- TSCharacters.txt        繁→简字表（多候选取首，OpenCC 同法）；
- TWVariantsRev.txt       台湾字形→OpenCC 标准繁体（复合入繁→简）；
- HKVariantsRev.txt       香港字形→OpenCC 标准繁体（同上）。

约定（数据表，非典籍；记 PROOFREADING.md）：

- 字级映射，词级消歧不做（乾→乾 首候选即原字，故「乾坤」不受累；
  检索为召回层，个别多义字取首候选无碍——校验层不经此表）；
- 键值均单字；恒等映射弃收；台/港字形经标准繁体复合到简体，
  复合后与 TSCharacters 冲突者以 TSCharacters 为准；
- 复合结果若把「本身已是简体之字」改写为他字（潜在腐蚀简体检索），
  一律弃收并计数（meta.skipped）。

用法：
    python tools/import_opencc_t2s.py [--out FILE]
"""

import argparse
import inspect
import json
from datetime import date
from pathlib import Path

OUT = Path(__file__).parent.parent / "tianwen" / "data" / "t2s.json"
LICENSE = "Apache License 2.0（BYVoid/OpenCC 字典数据）"

#: 断言样例：常用繁体（含 樑 等书写变体）须按预期归一
EXPECT = {"謙": "谦", "樑": "梁", "運": "运", "爲": "为", "為": "为",
          "斷": "断", "體": "体", "無": "无", "財": "财", "祿": "禄"}
#: 多义保形弃收（FIXES 例：断言在源表后弃收）——OpenCC 对这些字靠
#: 词表消歧（TSPhrases「乾卦→乾卦」「乾乾淨淨→干干净净」），本表
#: 字级不消歧；乾为乾卦之字，库文保繁，弃收则查「乾」仍中「乾」、
#: 查「干」不误中乾卦
KEEP = ("乾",)
NOT_KEYS = ("紫", "甚", "斗")   # 本为简体（非繁体键），不应见于表


def _dict_dir():
    import opencc
    return Path(inspect.getfile(opencc)).parent / "dictionary"


def load_pairs(path):
    pairs = []
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        key, _, vals = line.partition("\t")
        first = vals.split()[0] if vals.split() else ""
        pairs.append((key, first))
    return pairs


def build():
    d = _dict_dir()
    ts = {}
    for k, v in load_pairs(d / "TSCharacters.txt"):
        assert len(k) == 1 and len(v) == 1, f"非单字映射：{k}→{v}"
        ts[k] = v
    simp_set = set(ts.values())

    out = {k: v for k, v in ts.items() if k != v}
    skipped = 0
    for name in ("TWVariantsRev.txt", "HKVariantsRev.txt"):
        for var, std in load_pairs(d / name):
            if len(var) != 1 or len(std) != 1:
                skipped += 1
                continue
            tgt = ts.get(std, std)
            if var == tgt or var in ts:      # 恒等；或 TSCharacters 已定
                continue
            if var in simp_set:              # 本身已是简体之字：不得改写
                skipped += 1
                continue
            if out.get(var, tgt) != tgt:     # 两地字形互斥（罕见）：弃收
                skipped += 1
                out.pop(var, None)
                continue
            out[var] = tgt

    for k in KEEP:
        assert k in out, f"保形弃收之字不在源表（源表有变？）：{k}"
        out.pop(k)
    for k, v in EXPECT.items():
        assert out.get(k) == v, f"样例断言不合：{k}→{out.get(k)!r}（期 {v}）"
    for k in NOT_KEYS:
        assert k not in out, f"简体之字被改写：{k}→{out[k]}"
    assert all(len(k) == 1 and len(v) == 1 and k != v for k, v in out.items())
    assert len(out) > 3000, f"表意外过小：{len(out)}"

    # 与问语关键词层（hanzi._T2S，OpenCC 逐词反向生成）交叉核对：
    # 两层同源，键相重者映射必同（甚→什 等问语变体不在本表，不相扰）
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tianwen import hanzi
    for k, v in hanzi._T2S.items():
        if k in out:
            assert out[k] == v, f"与 hanzi._T2S 冲突：{k}→{out[k]}≠{v}"
    return out, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    table, skipped = build()
    import opencc
    payload = {
        "meta": {
            "work": "繁→简字级归一表（检索层数据表，非典籍）",
            "source": ("BYVoid/OpenCC 字典（TSCharacters＋TWVariantsRev"
                       "＋HKVariantsRev），经 opencc-python-reimplemented "
                       "0.1.7 随包数据提取"),
            "license": LICENSE,
            "conversion": ("字级繁→简，多候选取首；台/港字形经标准繁体"
                           "复合；恒等弃收；已是简体之字不改写"
                           f"（弃收 {skipped} 条）；多义保形弃收 "
                           + "、".join(KEEP)
                           + "（词级消歧不做，乾卦之字保繁）；"
                           "仅供检索归一，引文校验不经此表"),
            "imported": date.today().isoformat(),
            "count": len(table),
        },
        "map": dict(sorted(table.items())),
    }
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        "utf-8")
    print(f"已写 {args.out}：{len(table)} 字对（弃收 {skipped}）")


if __name__ == "__main__":
    main()

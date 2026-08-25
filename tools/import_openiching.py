"""从 open-iching 仓库导入《周易》经文与《彖》《象》二传，生成本项目知识库数据文件。

用法：
    python tools/import_openiching.py <open-iching仓库路径> [输出路径]

数据底本：https://github.com/john-walks-slow/open-iching （ISC 许可；经传原文为公版文本）
导入后请依通行本（如中华书局点校本）人工校对，校对结果记录于 data/PROOFREADING.md。
"""

import json
import sys
from pathlib import Path

# 八卦三爻（自下而上），用于校验 binary 与 combination 一致
TRIGRAM_LINES = {
    "乾": (1, 1, 1), "兑": (1, 1, 0), "离": (1, 0, 1), "震": (1, 0, 0),
    "巽": (0, 1, 1), "坎": (0, 1, 0), "艮": (0, 0, 1), "坤": (0, 0, 0),
}

# 源仓库缺失条目的补丁（依通行本手补，待校对）。key: (词典名, 条目key)
PATCHES = {
    ("tuan", "iching__32"): (
        "恒，久也。刚上而柔下，雷风相与，巽而动，刚柔皆应，恒。"
        "“恒亨，无咎，利贞”，久于其道也。天地之道，恒久而不已也。"
        "“利有攸往”，终则有始也。日月得天而能久照，四时变化而能久成，"
        "圣人久于其道而天下化成。观其所恒，而天地万物之情可见矣。"
    ),
}

# 源仓库错字订正（依通行本，错文必须在场方可替换）。key: (词典名, 条目key)
FIXES = {
    # 乾九二小象「见龙再田」：通行本作「在田」，且同卦爻辞即「见龙在田」
    ("xiang", "iching__1_2"): ("见龙再田", "见龙在田"),
}


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else (
        Path(__file__).resolve().parent.parent / "tianwen" / "data" / "hexagrams.json"
    )

    iching = json.loads((src / "iching" / "iching.json").read_text("utf-8"))
    xiang = json.loads((src / "ichuan" / "xiang.json").read_text("utf-8"))
    tuan = json.loads((src / "ichuan" / "tuan.json").read_text("utf-8"))

    patched = []
    for (dict_name, key), text in PATCHES.items():
        target = {"tuan": tuan, "xiang": xiang}[dict_name]
        if key not in target:
            target[key] = text
            patched.append(f"{dict_name}:{key}")
    for (dict_name, key), (wrong, right) in FIXES.items():
        target = {"tuan": tuan, "xiang": xiang}[dict_name]
        assert wrong in target[key], f"订正落空（源已改？）: {dict_name}:{key} {wrong}"
        target[key] = target[key].replace(wrong, right)
        patched.append(f"{dict_name}:{key}(订正 {wrong}→{right})")

    assert len(iching) == 64, f"卦数异常: {len(iching)}"
    assert len(xiang) == 450, f"象传条数异常: {len(xiang)}（应为 64 大象 + 386 小象）"
    assert len(tuan) == 64, f"彖传条数异常: {len(tuan)}"

    records = []
    yao_count = 0
    for h in iching:
        hid = h["id"]
        binary = tuple(h["array"])
        lower, upper = h["combination"]
        assert TRIGRAM_LINES[lower] == binary[:3], f"卦{hid} 下卦与爻画不符"
        assert TRIGRAM_LINES[upper] == binary[3:], f"卦{hid} 上卦与爻画不符"
        assert h["symbol"] == chr(0x4DC0 + hid - 1), f"卦{hid} 卦符异常"

        yao = []
        extra = None
        for ln in h["lines"]:
            entry = {
                "pos": ln["id"],
                "name": ln["name"],
                "yang": ln["type"] == 1,
                "text": ln["scripture"],
                "xiaoxiang": xiang[f"iching__{hid}_{ln['id']}"],
            }
            if ln["id"] == 7:  # 用九 / 用六（仅乾、坤）
                assert hid in (1, 2) and ln["name"] in ("用九", "用六")
                entry.pop("pos")
                entry.pop("yang")
                extra = entry
            else:
                expect_yang = binary[ln["id"] - 1] == 1
                assert entry["yang"] == expect_yang, f"卦{hid}爻{ln['id']} 阴阳与爻画不符"
                yao.append(entry)
                yao_count += 1
        assert len(yao) == 6, f"卦{hid} 爻数异常"

        records.append({
            "id": hid,
            "name": h["name"],
            "symbol": h["symbol"],
            "trigrams": [lower, upper],  # [下卦, 上卦]
            "binary": list(binary),      # 自下而上，1 阳 0 阴
            "guaci": h["scripture"],
            "tuan": tuan[f"iching__{hid}"],
            "daxiang": xiang[f"iching__{hid}"],
            "yao": yao,
            "extra": extra,
        })

    assert yao_count == 384, f"爻辞总数异常: {yao_count}"

    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "meta": {
            "title": "周易（经文 + 彖传 + 象传）",
            "source": "john-walks-slow/open-iching (ISC)，经传原文为公版文本",
            "proofread": False,
            "patched_entries": patched,
            "note": "文本待依通行本人工校对；校对前引文核对仅保证与本库自身逐字一致。",
        },
        "hexagrams": records,
    }
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    print(f"OK: 64 卦、{yao_count} 爻、彖 {len(tuan)}、象 {len(xiang)} -> {out}")


if __name__ == "__main__":
    main()

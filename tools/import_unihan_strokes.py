"""从 Unicode 官方 Unihan 数据库导入汉字总笔画表（kTotalStrokes）。

字占（casting.cast_zi，依《梅花易数》卷一以字画起卦）取笔画用。
来源：https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip 内
Unihan_IRGSources.txt 的 kTotalStrokes 字段（现代通行总笔画；多值取首值）。
许可：Unicode License v3（https://www.unicode.org/license.txt）。

覆盖范围取 CJK 统一汉字扩展A区起至基本区末（U+3400–U+9FFF），常用
汉字姓名尽在其中；此外之罕见字起卦时如实拒之（提示改用铜钱法）。
古籍计画偶与今异（如《梅花易数·西林寺牌额占》记「西」为七画，今作
六画），故程序约定一律依本表，并在起卦凭证中逐字列明画数以便核对。

用法：
    python tools/import_unihan_strokes.py [--zip FILE] [--out FILE]
"""

import argparse
import io
import json
import re
import subprocess
import zipfile
from datetime import date
from pathlib import Path

URL = "https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip"
MEMBER = "Unihan_IRGSources.txt"
LICENSE = "Unicode License v3"
LICENSE_URL = "https://www.unicode.org/license.txt"
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"
START, END = 0x3400, 0x9FFF   # 扩展A区起 … 基本区末（含中间少量非汉字码位）


def fetch_zip() -> bytes:
    cmd = ["curl", "-sL", "--max-time", "300", URL]
    if Path(CA_BUNDLE).exists():
        cmd[1:1] = ["--cacert", CA_BUNDLE]
    out = subprocess.run(cmd, capture_output=True).stdout
    if not out.startswith(b"PK"):
        raise RuntimeError("Unihan.zip 下载失败: " + URL)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", help="本地 Unihan.zip（缺省自 unicode.org 下载）")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1]
                                         / "yijing_agent/data/strokes.json"))
    args = ap.parse_args()

    data = Path(args.zip).read_bytes() if args.zip else fetch_zip()
    text = zipfile.ZipFile(io.BytesIO(data)).read(MEMBER).decode("utf-8")

    m = re.search(r"Unicode Version\s+([\d.]+)", text)
    version = m.group(1) if m else "?"

    counts = [0] * (END - START + 1)
    n = 0
    for line in text.splitlines():
        if "\tkTotalStrokes\t" not in line:
            continue
        cp_s, _, val = line.split("\t")
        cp = int(cp_s[2:], 16)          # "U+4E00"
        if START <= cp <= END:
            counts[cp - START] = int(val.split()[0])   # 多值取首值
            n += 1

    out = {
        "meta": {
            "source": "Unicode Unihan kTotalStrokes（Unihan_IRGSources.txt）",
            "unicode_version": version,
            "url": URL,
            "license": LICENSE,
            "license_url": LICENSE_URL,
            "imported": date.today().isoformat(),
            "note": "现代通行总笔画，多值取首值；覆盖 U+3400–U+9FFF"
                    "（CJK 扩展A区＋基本区），0 表示无数据",
            "start": START,
        },
        "counts": counts,
    }
    Path(args.out).write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")
    kb = Path(args.out).stat().st_size / 1024
    print(f"Unicode {version}：{n} 字笔画 → {args.out}（{kb:.0f} KB）")


if __name__ == "__main__":
    main()

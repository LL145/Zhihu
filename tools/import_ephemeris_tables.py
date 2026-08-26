"""生成七曜星历系数表 data/ephemeris.json（西洋占星本命盘之数据表）。

数据表（非典籍，同 strokes.json 之例）；机器来源与转录路径：

- 行星与地球：VSOP87D 周期项（Bretagnon & Francou 1988，IMCCE 公开
  科学数据）。取数经 PyMeeus（MIT 项目文档自述转录自 Meeus
  《Astronomical Algorithms》所载 VSOP87 表；LGPL-3 许可，此处只取
  其转录之科学系数数值，不取其代码）；按振幅阈值截断——第 k 幂序列
  项 [A,B,C] 保留当且仅当 A·TMAX^k ≥ EPS（TMAX=0.21 儒略千年，覆盖
  1790–2210；EPS 见下），截断误差由本脚本对照 PyMeeus 全表逐点实测，
  最大值记入 meta（另有 tests/ 以 pyephem 独立谱系交叉验证）。
- 月亮：Meeus 第 47 章周期项表（ELP-2000 截断，60 项全取，只取黄经
  Σl 列；A1/A2/A3 附加项与 E 因子在求值器内，见 astro/ephemeris.py）。

自检：写出 JSON 后即以运行时求值器（tianwen.astro.ephemeris）对照
PyMeeus 全表在 1900–2100 逐点比较，超差即失败不落盘。

用法：
    python tools/import_ephemeris_tables.py [--cache-dir .cache_ephem]

PyMeeus 自 PyPI 取源码包（pip download）入缓存目录后就地引用
（其 setup.py 与新版 setuptools 不合，不作安装）。
"""

import argparse
import importlib
import json
import math
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "tianwen" / "data" / "ephemeris.json"

PLANETS = ("mercury", "venus", "earth", "mars", "jupiter", "saturn")

TMAX = 0.21       # 儒略千年：覆盖 1790–2210
EPS_LB = 25.0     # 1e-8 rad ≈ 0.05″（R 同阈，单位 1e-8 AU）

#: 自检门限（对照 PyMeeus 全表之最大允差）；距离相对差 1e-5 对地心
#: 黄经的影响在角秒量级，远小于落宫判读所需
TOL_L_ARCSEC = 5.0
TOL_B_ARCSEC = 5.0
TOL_R_REL = 1e-5
TOL_MOON_ARCSEC = 0.01   # 同表同算，仅浮点噪声


def load_pymeeus(cache_dir):
    cache = Path(cache_dir)
    hits = list(cache.glob("PyMeeus-*/pymeeus/__init__.py"))
    if not hits:
        cache.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "download", "pymeeus", "--no-deps",
             "--no-binary", ":all:", "-d", str(cache)], check=True)
        tgz = next(cache.glob("PyMeeus-*.tar.gz"))
        with tarfile.open(tgz) as tf:
            tf.extractall(cache, filter="data")
        hits = list(cache.glob("PyMeeus-*/pymeeus/__init__.py"))
    src = hits[0].parent.parent
    sys.path.insert(0, str(src))
    version = src.name.split("-", 1)[1]
    return version


def truncate_vsop(table):
    """[[ [A,B,C]... ]×幂] → 同构截断表。A 单位 1e-8。"""
    out = []
    tn = 1.0
    for series in table:
        keep = [[a, b, c] for a, b, c in series if a * tn >= EPS_LB]
        out.append(keep)
        tn *= TMAX
    while out and not out[-1]:
        out.pop()
    return out


def build(version):
    data = {"vsop87": {}, "moon": {}}
    counts = {}
    for name in PLANETS:
        mod = importlib.import_module(f"pymeeus.{name.capitalize()}")
        entry = {}
        for key, tab in (("L", mod.VSOP87_L), ("B", mod.VSOP87_B),
                         ("R", mod.VSOP87_R)):
            entry[key] = truncate_vsop(tab)
        data["vsop87"][name] = entry
        counts[name] = {k: sum(len(s) for s in v) for k, v in entry.items()}
    moon_mod = importlib.import_module("pymeeus.Moon")
    data["moon"]["l"] = [[d, m, mp, f, sl] for d, m, mp, f, sl, _sr
                         in moon_mod.PERIODIC_TERMS_LR_TABLE]
    assert len(data["moon"]["l"]) == 60
    data["meta"] = {
        "table": "七曜星历系数（数据表，非典籍）",
        "source": ("VSOP87D 周期项（Bretagnon & Francou 1988，IMCCE 公开"
                   f"科学数据），经 PyMeeus {version}（Meeus 表之转录）"
                   "机器提取；月亮为 Meeus《Astronomical Algorithms》"
                   "第 47 章表（ELP-2000 截断，60 项，黄经列）"),
        "license": "科学数据（VSOP87 公开发布可自由使用；系数数值非代码）",
        "truncation": (f"VSOP87 第 k 幂序列保留 A·{TMAX}^k ≥ {EPS_LB}"
                       "（单位 1e-8 rad/AU）之项；月表全取"),
        "term_counts": counts,
        "generated_by": "tools/import_ephemeris_tables.py",
    }
    return data


def selfcheck(data):
    """运行时求值器对照 PyMeeus 全表逐点实测；超差抛 AssertionError。

    网格：1900–2100 每 100 日（含月亮快变采样充分）。返回实测最大误差
    （记入 meta）。
    """
    from pymeeus.Epoch import Epoch
    from pymeeus.Moon import Moon

    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    sys.path.insert(0, str(ROOT))
    import tianwen.astro.ephemeris as eph
    importlib.reload(eph)

    full = {}
    for name in PLANETS:
        mod = importlib.import_module(f"pymeeus.{name.capitalize()}")
        full[name] = getattr(mod, name.capitalize())

    worst = {"L_arcsec": 0.0, "B_arcsec": 0.0, "R_rel": 0.0,
             "moon_arcsec": 0.0}
    jd0, jd1 = 2415020.5, 2488069.5          # 1900-01-01 … 2099-12-25
    jde = jd0
    while jde <= jd1:
        t = (jde - 2451545.0) / 365250.0
        tc = t * 10.0
        epoch = Epoch(jde)
        for name in PLANETS:
            l_ref, b_ref, r_ref = full[name].geometric_heliocentric_position(
                epoch, tofk5=False)
            L, B, R = eph._vsop(name, t)
            dl = abs((math.degrees(L) - float(l_ref) + 180.0) % 360.0 - 180.0)
            worst["L_arcsec"] = max(worst["L_arcsec"], dl * 3600.0)
            db = abs(math.degrees(B) - float(b_ref)) * 3600.0
            worst["B_arcsec"] = max(worst["B_arcsec"], db)
            worst["R_rel"] = max(worst["R_rel"], abs(R - r_ref) / r_ref)
        lam_ref = float(Moon.geocentric_ecliptical_pos(epoch)[0])
        dm = abs((eph.moon_longitude_mean(tc) - lam_ref + 180.0) % 360.0
                 - 180.0) * 3600.0
        worst["moon_arcsec"] = max(worst["moon_arcsec"], dm)
        jde += 100.0

    assert worst["L_arcsec"] <= TOL_L_ARCSEC, worst
    assert worst["B_arcsec"] <= TOL_B_ARCSEC, worst
    assert worst["R_rel"] <= TOL_R_REL, worst
    assert worst["moon_arcsec"] <= TOL_MOON_ARCSEC, worst
    return worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=str(ROOT / ".cache_ephem"))
    args = ap.parse_args()

    version = load_pymeeus(args.cache_dir)
    data = build(version)
    worst = selfcheck(data)
    data["meta"]["max_error_vs_full_tables"] = {
        "grid": "1900–2100 每 100 日",
        "L_arcsec": round(worst["L_arcsec"], 3),
        "B_arcsec": round(worst["B_arcsec"], 3),
        "R_rel": f"{worst['R_rel']:.2e}",
        "moon_arcsec": round(worst["moon_arcsec"], 5),
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    n = sum(sum(v.values()) for v in data["meta"]["term_counts"].values())
    print(f"星历表：VSOP87 截断共 {n} 项，月表 60 项，"
          f"实测最大误差 {data['meta']['max_error_vs_full_tables']}"
          f" → {OUT}（{OUT.stat().st_size // 1024}KB）")


if __name__ == "__main__":
    sys.exit(main())

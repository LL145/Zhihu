"""生成紫微排盘命例回归集：以 py-iztro（iztro 排盘库的 Python 封装）为
对照工具，跑一批已知命例，落成 tests/fixtures/ziwei_iztro.json。

只在开发机运行（依赖 py-iztro / pythonmonkey，较重，不进 requirements）：
    pip install py-iztro
    python tools/gen_ziwei_fixtures.py

对照口径（流派分歧处不比或改比，见 yijing_agent/ziwei/chart.py 顶注）：
- 比：农历换算、五行局、十二宫名/宫干/支、身宫、大限起止、
  十四主星与昌曲辅弼魁钺禄马、羊陀火铃空劫十四辅煞的落宫、四化；
- 壬干年不比化科（《全书》天府化科，iztro 依流行诀作左辅化科）；
- 辛干年魁钺只比 {寅,午} 落宫集合（《全书》「虎马」与流行诀「马虎」互换）；
- 不比庙旺平陷（以《全书·卷二》庙陷表为底本，个别星宫与 iztro 有出入，
  如七杀在酉底本作旺）；
- 命例避开闰月上半月（本产品依《全书》闰月整月归下月，iztro 以月中分界，
  下半月两派一致）与晚子时。
"""

import json
from pathlib import Path

from py_iztro import Astro

# (公历生日, 时辰序 0=早子…11=亥, 性别) —— 覆盖十天干、正月初一、腊月、
# 三十日、早子时、闰月下半月。
CASES = [
    ("2000-9-14", 6, "男"),    # 庚辰
    ("2001-5-20", 2, "男"),    # 辛巳（魁钺比集合）
    ("2012-3-8", 4, "女"),     # 壬辰（不比化科）
    ("1984-2-5", 0, "男"),     # 甲子，早子时
    ("1985-7-1", 11, "女"),    # 乙丑
    ("1986-10-10", 5, "男"),   # 丙寅
    ("1987-12-31", 8, "女"),   # 丁卯
    ("1988-4-15", 3, "男"),    # 戊辰
    ("1989-8-8", 7, "女"),     # 己巳
    ("1990-11-11", 1, "男"),   # 庚午
    ("1991-3-3", 9, "女"),     # 辛未（魁钺比集合）
    ("1992-6-6", 10, "男"),    # 壬申（不比化科）
    ("1993-9-9", 6, "女"),     # 癸酉
    ("1994-1-30", 4, "男"),    # 癸酉腊月
    ("1977-2-18", 2, "女"),    # 丁巳正月初一
    ("1995-5-29", 0, "女"),    # 乙亥，早子时
    ("2024-7-20", 5, "男"),    # 甲辰
    ("1999-3-17", 3, "女"),    # 己卯
    ("1960-1-1", 7, "男"),     # 己亥（跨甲子边界较早年份）
    ("2023-12-31", 9, "女"),   # 癸卯
    ("2012-6-15", 4, "女"),    # 壬辰闰四月下半月（两派闰月口径一致段）
]

# iztro 宫名 → 《全书》宫名
PALACE_MAP = {"命宫": "命宫", "兄弟": "兄弟", "夫妻": "妻妾", "子女": "子女",
              "财帛": "财帛", "疾厄": "疾厄", "迁移": "迁移", "仆役": "奴仆",
              "官禄": "官禄", "田宅": "田宅", "福德": "福德", "父母": "父母"}

STARS = ["紫微", "天机", "太阳", "武曲", "天同", "廉贞", "天府", "太阴",
         "贪狼", "巨门", "天相", "天梁", "七杀", "破军",
         "文昌", "文曲", "左辅", "右弼", "天魁", "天钺", "禄存", "天马",
         "擎羊", "陀罗", "火星", "铃星", "地空", "地劫"]


def main():
    astro = Astro()
    out = []
    for date, tidx, gender in CASES:
        s = astro.by_solar(date, tidx, gender, True, "zh-CN")
        year_gan = s.chinese_date.split(" ")[0][0] if " " in s.chinese_date \
            else s.chinese_date[0]
        stars = {}
        palaces = {}
        body = None
        for p in s.palaces:
            palaces[p.earthly_branch] = {
                "name": PALACE_MAP[p.name],
                "stem": p.heavenly_stem,
                "daxian": [p.decadal.range[0], p.decadal.range[1]],
            }
            if p.is_body_palace:
                body = p.earthly_branch
            for st in list(p.major_stars) + list(p.minor_stars):
                if st.name in STARS:
                    stars[st.name] = p.earthly_branch
        sihua = {}
        for p in s.palaces:
            for st in list(p.major_stars) + list(p.minor_stars):
                if st.mutagen:
                    sihua[st.mutagen] = st.name
        out.append({
            "solar": date, "time_index": tidx, "gender": gender,
            "iztro_lunar": s.lunar_date,
            "year_gz": year_gan,
            "wuxing_ju": s.five_elements_class,
            "body_branch": body,
            "palaces": palaces,
            "stars": stars,
            "sihua": sihua,
        })
        print(f"{date} tidx={tidx} {gender}: {s.five_elements_class} "
              f"命宫在{[b for b, v in palaces.items() if v['name'] == '命宫'][0]}")
    dst = Path(__file__).parent.parent / "tests" / "fixtures" / "ziwei_iztro.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps({
        "tool": "py-iztro 0.1.5 (iztro)",
        "note": "对照口径见 tools/gen_ziwei_fixtures.py 顶注",
        "cases": out,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写入 {dst}（{len(out)} 例）")


if __name__ == "__main__":
    main()

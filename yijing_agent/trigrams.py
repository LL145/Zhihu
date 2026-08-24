"""八卦基础表。

先天八卦数（《梅花易数》起卦用）：乾一、兑二、离三、震四、巽五、坎六、艮七、坤八。
爻画自下而上，1 为阳、0 为阴。
"""

TRIGRAMS = {
    "乾": {"num": 1, "lines": (1, 1, 1), "nature": "天"},
    "兑": {"num": 2, "lines": (1, 1, 0), "nature": "泽"},
    "离": {"num": 3, "lines": (1, 0, 1), "nature": "火"},
    "震": {"num": 4, "lines": (1, 0, 0), "nature": "雷"},
    "巽": {"num": 5, "lines": (0, 1, 1), "nature": "风"},
    "坎": {"num": 6, "lines": (0, 1, 0), "nature": "水"},
    "艮": {"num": 7, "lines": (0, 0, 1), "nature": "山"},
    "坤": {"num": 8, "lines": (0, 0, 0), "nature": "地"},
}

BY_NUM = {v["num"]: k for k, v in TRIGRAMS.items()}
BY_LINES = {v["lines"]: k for k, v in TRIGRAMS.items()}

ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

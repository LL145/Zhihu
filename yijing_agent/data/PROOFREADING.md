# 典籍文本来源与校对说明

## 底本

`hexagrams.json` 由 `tools/import_openiching.py` 从
[john-walks-slow/open-iching](https://github.com/john-walks-slow/open-iching)
（ISC 许可）导入生成，内容为《周易》经文（卦辞、爻辞、用九用六）、
《彖传》与《象传》（大象、小象）。经传原文为先秦公版文本。

导入时的完整性校验：64 卦、384 爻、彖 64 条、象 450 条（64 大象 + 386 小象）；
卦符、爻画、上下卦、爻名阴阳全部交叉核验一致。

## 手补条目（源数据缺失，导入脚本补入，须优先校对）

- `tuan:iching__32`（恒卦彖传）：源仓库 JSON 与 markdown 均缺失，依通行本手补。

## 校对状态

- [ ] **未校对**。`meta.proofread = false`。
- 引文校验器保证 LLM 引文与本库逐字一致；在完成人工校对之前，
  这只保证"内部一致"，不保证与通行本（如中华书局点校本）逐字一致。

## 校对流程（建议）

1. 以一部通行点校本为准（建议注明版本），逐卦核对 `hexagrams.json`；
2. 发现差异：改在 `tools/import_openiching.py` 的 `PATCHES` 中（而非直接改
   JSON），重新生成，保证可追溯；
3. 全部核毕后将 `meta.proofread` 置为 true，并在本文件记录校对人与所据版本。

## 断辞结论审定

`verdict_overrides.json` 用于人工审定断辞结论：自动提取（audited=false）
仅为初版草案，审定后按 cite_id 写入 override，输出即标注"人工审定"。
优先审定：`未著断辞` 类（约束最弱）与含多个断辞的复合句。

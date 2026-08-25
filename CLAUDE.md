# 天问：开发须知

## 工作流（用户约定）

- **所有改动直接提交并推送到 main 分支**。不开长期功能分支，不开 PR
  （用户明示的固定约定）；推送 main 即触发 GitHub Actions 测试与打包。
- 提交前本地跑通 `python -m pytest tests/ -q`。

## 项目规矩（详见各文档）

- 改流程必先改 [ALGORITHM.md](ALGORITHM.md)——代码与文档不一致视为缺陷；
  设计与路线图在 [DESIGN.md](DESIGN.md)。
- `tianwen/data/*.json` 一律由 `tools/` 导入脚本生成，**不手改**；
  订正走脚本内 FIXES（断言存在后替换），来源、许可与校对状态记于
  [tianwen/data/PROOFREADING.md](tianwen/data/PROOFREADING.md)。
- 底本不过关（残缺、无标点四库本、今人文字机器不可剥离）宁缺，
  缓收书目及缘由录 PROOFREADING.md。
- 非古籍明说不用随机数；引文过校验器逐字校验；吉凶只从主断一处出。

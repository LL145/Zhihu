# 知乎 · 算命 Agent

有典可依、可复现的问事占断。设计文档见 [DESIGN.md](DESIGN.md)。

**核心原则：LLM 不算卦，只解释。** 起卦、选文、断辞结论全部是确定性代码；
大模型只负责把规则选定的《周易》原文讲清楚，其解读中的每条引文都经
逐字校验后方可输出，校验不过即拒绝（降级为仅原文与结论）。

当前为 v1（易经事引擎）。星盘命引擎（紫微斗数）为 v2，见设计文档。

## 快速开始（Windows）

### 方式一：直接下载可执行文件（无需安装 Python）

每次推送到 main 分支，GitHub Actions 会自动打包 Windows 单文件版：
仓库 **Actions** 页 → 最新一次 `build` 运行 → Artifacts → 下载
`yijing-agent-windows`，解压得到 `yijing-agent.exe`。
打了 `v*` 标签（如 `v0.1.0`）则会自动发布到 **Releases** 页，从那里下载更方便。

```powershell
.\yijing-agent.exe -q "近期换一份工作是否合适"
```

要启用大模型解读，把 `config.json`（见下文）放在 exe 同一目录即可。
双击 exe 也可运行（交互输入问题，结束按回车退出）。

### 方式二：源码运行

需要 Python 3.9+（[python.org](https://www.python.org/downloads/) 安装时勾选
"Add python.exe to PATH"）。在项目目录打开终端（PowerShell 或 cmd）：

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

py -m yijing_agent -q "近期换一份工作是否合适"
```

若终端中文显示异常，先执行 `chcp 65001` 切换到 UTF-8。

## 配置大模型解读（OpenRouter）

不配置也能用（输出卦象、原文、结论，只是没有白话解读）。

**首次运行会自动生成 `config.json`**（exe 版在 exe 同目录，源码版在项目
根目录），用记事本打开，填两个字段即可：

```json
{
  "api_key": "在这里填入你的 OpenRouter API Key（形如 sk-or-v1-...）",
  "model": "anthropic/claude-sonnet-5",
  "base_url": "https://openrouter.ai/api/v1"
}
```

- `api_key`：在 [openrouter.ai/keys](https://openrouter.ai/keys) 创建；
- `model`：OpenRouter 上的任意模型 ID，默认 `anthropic/claude-sonnet-5`。

也可用环境变量代替：`OPENROUTER_API_KEY`、`OPENROUTER_MODEL`、
`OPENROUTER_BASE_URL`（环境变量优先于 config.json）。
`config.json` 已在 .gitignore 中，不会被提交。

## 用法

```powershell
# 梅花易数·时间起卦（默认）：完全确定，同一时刻问同一事，任何人复算结果一致
py -m yijing_agent -q "所问之事"

# 铜钱法·六爻：随机种子公开（SHA-256），凭证可复现
py -m yijing_agent -q "所问之事" --method coin

# 指定起卦时刻（复现旧卦 / 测试用）
py -m yijing_agent -q "所问之事" --when "2026-08-24 15:30"

# 不调用大模型
py -m yijing_agent -q "所问之事" --no-llm
```

输出包含：问事类别（事业/学业/情感/出行…，规则分类，决定解读落点）→
卦象（本卦、之卦、互卦、动爻）→ 所据经文（占法规则选定的原文，
含彖、象传与**王弼注**，逐条标出处）→ 断辞结论（吉/凶/谨/忌…，
来自确定性映射，注疏不参与断辞）→ 大模型解读（引文逐字校验后输出）→
起卦凭证（算式或种子，可自行复算）。

**多轮追问**：在终端交互运行且已配置大模型时，解读输出后可就本卦继续
追问（如"如果拖到年底再动呢"）。追问不重新起卦，回答仍只能依据本次
选定的经文，结论不变，每轮回答同样经逐字引文校验；直接回车结束。

## 项目结构

```
yijing_agent/
  casting.py     起卦引擎：梅花易数时间起卦（无随机数）/ 铜钱法（种子公开）
  selection.py   断卦规则：朱熹《易学启蒙》占法 + 《梅花易数》体用
  verdict.py     断辞 → 结论映射（确定性；人工审定走 data/verdict_overrides.json）
  topic.py       问事分类（分类断法）：关键词规则定类别与解读落点，无 LLM
  knowledge.py   典籍知识库：结构化查表（64卦 + 彖传 + 象传，非向量检索）
  llm.py         解读生成与多轮追问（OpenRouter，只解释、不改判）
  validator.py   引文校验器：逐字比对，防幻觉闸门（解读与追问回答同过此关）
  redline.py     红线拦截：医疗/投资/法律/寿夭类问题拒答
  lunar.py       公历→农历（cnlunar），流派约定显式标注
  data/          知识库数据与校对说明（见 data/PROOFREADING.md）
                 hexagrams.json 经传原文；wangbi.json 王弼《周易注》（注疏层）
tools/
  import_openiching.py        从 open-iching 仓库导入并校验典籍数据
  import_wikisource_wangbi.py 从维基文库《周易正義》导入王弼注（经文锚定对齐）
tests/           89 项测试：起卦确定性、占法七情形、断辞映射、问事分类、
                 注疏挂载、引文校验、LLM 重试与追问
```

## 测试

```powershell
pip install -r requirements-dev.txt
py -m pytest tests/ -q
```

## 数据与校对

经传原文导入自 [john-walks-slow/open-iching](https://github.com/john-walks-slow/open-iching)
（ISC 许可，经传原文为公版），导入时做了 64 卦 / 384 爻 / 彖象条数与爻画
一致性的完整校验。王弼《周易注》（598 条）导入自中文维基文库
[《周易正義》](https://zh.wikisource.org/wiki/周易正義)（CC BY-SA 4.0，
含维基文库贡献者所加标点；各页面版本号记录于数据文件 meta），以经文
锚定逐段对齐，注疏只作解读语境、不参与断辞结论。两者**均尚未依通行本
人工校对**——校对流程与状态见
[yijing_agent/data/PROOFREADING.md](yijing_agent/data/PROOFREADING.md)。

## 免责声明

内容源自古代典籍原文及传统占法，属传统文化范畴，仅供参考，不构成任何
现实决策依据。

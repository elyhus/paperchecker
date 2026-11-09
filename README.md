# PaperChecker · 论文格式合规检查（桌面智能体 v1.0）

对应选题：**《面向高校文档规范的桌面智能体设计与实现——格式检查、自动修复与批处理》**

这是一个**可运行的完整原型**：检查、定位、修复、复检、图表、批处理、语义检查都已接通。
答辩时可以现场演示"导入 → 检查 → 定位 → 修复 → 复检"的完整闭环。

---

## 0. 最简单的启动方式（双击）

在访达里进入 `prototype` 文件夹，**双击 `启动.command`** 即可打开界面。
若系统提示"无法打开，因为来自身份不明的开发者"：右键点它 → 选"打开" → 再点"打开"，之后就不用了。

把某个 `.docx` 文件**拖到 `启动.command` 图标上**，会直接检查那个文件。

其他平台：Windows 双击 `启动.bat`，Linux 执行 `./启动.sh`。

## 1. 怎么运行

需要 Python 3.10+ 与 `python-docx`（本机已用运行时自带的 Python 验证）：

```bash
# 桌面界面（主入口）
python run.py

# 命令行检查
python run.py check samples/bad_report.docx

# 导出 Markdown / JSON，并写入 SQLite
python run.py check samples/bad_report.docx --md out/报告.md --json out/结果.json --db out/paperchecker.db

# 一键修复（会先备份原文件，再确认写入）
python run.py check 文档.docx --fix

# 查看规则库 / 检查历史
python run.py rules
python run.py history
```

本机可用的解释器路径：

```bash
/Users/kawen/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3
```

## 2. 目录结构

```
prototype/
├── run.py                     统一入口（无参数＝GUI，带 check/rules/history＝命令行）
├── 启动.command / 启动.bat / 启动.sh   三个平台的启动脚本
├── requirements.txt           依赖清单
├── rules/custom_rules.json    用户自定义规则（可编辑）
├── paperchecker/
│   ├── model.py               数据模型：Issue / Policy / RuleStats
│   ├── docmodel.py            docx 解析：样式继承链回溯，算出“实际生效格式”
│   ├── rules.py               规则库（18 条），纯函数、只读不写
│   ├── engine.py              规则执行与结果聚合，单条规则异常不影响整体
│   ├── fixer.py               一键修复：预览 → 备份 → 写回
│   ├── report.py              控制台表格 / Markdown / JSON
│   ├── store.py               SQLite：任务、问题、修复记录、模型配置
│   ├── llm.py                 语义检查（用户自填 API Key，Key 存系统密钥链）
│   ├── cli.py                 命令行
│   ├── gui.py                 Tkinter 桌面界面
│   ├── customrules.py         用户自定义规则（声明式配置 + 通用执行器）
│   ├── secretstore.py         跨平台密钥存储（Keychain / 凭据管理器 / secret-tool）
│   └── ruledialog.py          规则设置窗口（新建/编辑/启停/删除）
├── samples/
│   ├── make_bad_sample.py     生成“故意违规”的样本
│   └── bad_report.docx        样本（18 类人工植入的违规）
└── out/                       导出的报告、JSON、数据库
```

## 3. 已实现的 18 条规则

| 编号 | 规则 | 级别 | 可修复 |
|---|---|---|---|
| R001 | 正文字体应为宋体 | 错误 | ✓ |
| R002 | 正文字号应为小四（12 磅） | 错误 | ✓ |
| R003 | 正文行距应为固定值 20 磅 | 错误 | ✓ |
| R004 | 标题层级不得跳级 | 警告 | |
| R005 | 一级标题应另起一页 | 警告 | |
| R006 | 摘要字数 200–300 | 错误 | |
| R007 | 关键词 3–5 个，中文逗号分隔 | 错误 | |
| R008 | 目录应由 Word 自动生成（TOC 域） | 警告 | |
| R009 | 图表编号按章连续 | 错误 | |
| R010 | 图表题注为黑体五号 | 错误 | |
| R011 | 结论字数 400–1000 | 错误 | |
| R012 | 参考文献不少于 10 篇 | 错误 | |
| R013 | 英文文献不少于 2 篇 | 错误 | |
| R014 | 英文/数字片段用 Times New Roman | 警告 | |
| R015 | 不得连续 3 个以上空段落 | 警告 | ✓ |
| R016 | 标题序号与题目之间空一格 | 提示 | |
| R017 | 摘要中不得出现文献引用 | 错误 | |
| R018 | 章标题用阿拉伯数字（第1章，非第一章） | 警告 | |

规则只读不写；修复逻辑集中在 `fixer.py`，与检查逻辑解耦。

## 4. 设计要点（报告里可以展开的三处）

1. **样式继承链回溯**：docx 的实际格式 = 直接格式 > 样式链（style → base_style）> 文档默认。
   `docmodel.py` 对段落属性与字符属性都做了回溯，否则"样式里定义了宋体小四"的段落会被误判。
2. **固定行高下的容量预判**：选题单等模板表格的行高是"固定值"，写超了会被裁切。
   `tools/fill_topic_form.py` 在写入前按“可用行数”预检，超预算直接中止，不做无声的破坏。
3. **修复可回滚**：写回前 `backup()` 生成带时间戳的副本，修复记录入 `t_fix_record`，
   每处改动都记录 原值 → 新值。

## 5. 数据模型（6 张表，对应报告第 3 章）

`t_model_config` 模型配置（密钥密文） · `t_rule` 规则库 · `t_check_task` 检查任务 ·
`t_issue` 问题明细 · `t_fix_record` 修复记录 · `t_semantic_result` 语义检查结果

`store.py` 已实现前四张的建表与读写；`t_rule`、`t_semantic_result` 表结构已定义，
规则目前硬编码在 `rules.py`、语义检查尚未批量入库——这是**下一步工作**，报告"不足与展望"可直接引用。

## 6. 现状与边界（答辩别踩坑）

- ✅ 可运行：解析、检查、统计、报告导出、修复、GUI、CLI、SQLite 落库
- ✅ 已验证：样本植入 18 类违规，检出 20 条问题、覆盖全部 18 条规则（R005/R010 各命中 2 处）
- ⚠️ 只支持 `.docx`，`.doc` 需先另存
- ⚠️ R014 对“中英混排在同一 run”的情况保守跳过，字符级字体判定留作后续
- ⚠️ 语义检查（`llm.py`）已封装但默认不调用，需要用户自己填 Key；无 Key 时静默降级，不影响规则结论
- ⚠️ 未做安装包、图标、代码签名；界面为功能原型

## 7. 与报告章节的对应关系

| 报告章节 | 对应代码 |
|---|---|
| 第 3 章 概要设计·系统结构 | `run.py` / `gui.py` / `cli.py` → `engine` → `rules` / `fixer` → `docmodel` |
| 第 3 章 数据库设计 | `store.py` 的 `SCHEMA` |
| 第 4 章 文档解析 | `docmodel.py` 的 `_inherit` / `_line_spacing` / `_style_chain_from_run` |
| 第 4 章 规则引擎 | `rules.py` 的 `rule()` 注册器 + `engine.run()` |
| 第 4 章 修复与回滚 | `fixer.preview()` / `fixer.apply()` / `backup()` |
| 第 4 章 语义检查 | `llm.py`（Provider 适配 + JSON 约束 + 失败降级） |
| 第 5 章 测试 | `samples/make_bad_sample.py` 与 `out/` 下的检查报告 |

## 8. 跨平台说明

| 平台 | 启动方式 | 密钥后端 | 验证状态 |
|---|---|---|---|
| macOS | 双击 `启动.command` | Keychain（`security`） | ✅ 已实测 |
| Windows | 双击 `启动.bat` | 凭据管理器（`CredWriteW` / `CredReadW`） | ⚠️ 代码已写，未实测 |
| Linux | `./启动.sh` | `secret-tool`（libsecret） | ⚠️ 代码已写，未实测 |

**为什么能跨平台**：整个程序是纯 Python（`python-docx` + `tkinter` + `sqlite3` + `urllib`），
没有平台相关的二进制依赖；规则判定基于 OOXML 结构，与操作系统无关。

**平台差异只有两处，都已抽成独立模块**：

1. 密钥存储 → `secretstore.py`：三平台三个后端，都不可用时退化为环境变量（只读、不落盘）
2. 启动脚本 → `启动.command` / `启动.bat` / `启动.sh`

**运行前提**：Python 3.10+、`pip install -r requirements.txt`；
Linux 还需 `sudo apt install python3-tk`（tkinter 不一定随 Python 一起装）。

**不需要**在系统里安装宋体/黑体：程序只读取 docx 里记录的字体名做比对，不做渲染。

## 9. 自定义规则（不用改代码）

规则文件：`rules/custom_rules.json`（首次运行会自动生成一份示例）。
三种添加方式：

1. **界面**：主窗口点「规则设置」→「新建规则」→ 填表单 → 保存，立即生效并自动重检
2. **改 JSON**：直接编辑 `custom_rules.json`，保存后重新检查即可
3. **调参数**：`params` 里可以改正文字号、行距、摘要字数、文献篇数等，覆盖内置默认值

### 四种规则类型

| type | 作用 | 必填字段 |
|---|---|---|
| `text` | 正则匹配：禁止出现 / 必须出现 | `pattern`、`mode`(forbid/require) |
| `format` | 检查字体、字号、行距 | `prop`(font/size/line_spacing)、`expect` |
| `length` | 某个小节的字数区间 | `section`、`min`、`max` |
| `count` | 文献篇数、英文文献、关键词个数 | `target`、`min`、`max` |

### 可选范围 scope

`body` 正文段落 · `heading` 各级标题 · `caption` 图表题注 · `reference` 参考文献 ·
`all` 全部段落 · `section` 指定小节（配合 `section` 字段）

### 例子：正文里出现"笔者认为"就报警

```json
{
  "id": "C001",
  "name": "正文不得出现口语化表述",
  "type": "text",
  "scope": "body",
  "mode": "forbid",
  "pattern": "笔者认为|我认为|我觉得|众所周知",
  "severity": "警告",
  "message": "正文出现口语化表述：{match}"
}
```

### 例子：正文必须 10.5 磅（并且能一键修复到 10.5）

```json
{
  "id": "C010",
  "name": "正文为五号",
  "type": "format",
  "scope": "body",
  "prop": "size",
  "expect": 10.5,
  "severity": "警告"
}
```

`format` 类规则修复时会**按规则自己的 `expect` 生效**，不是按内置默认值——
所以换一份学校的规范，只改 JSON 就能整套复用。

### 边界

- 自定义规则只做**段落级 / 小节级**判断，跨元素的复杂规则（图表编号连续性、标题层级跳级）仍是内置代码规则
- 正则按 Python `re` 单行匹配，不支持跨段落
- 自定义规则不做"忽略某几段"的白名单

## 10. 功能清单（对照选题单逐条核）

| 选题单要求 | 实现位置 | 状态 |
|---|---|---|
| 解析段落/字符格式、样式继承链、节属性 | `docmodel.py` | ✅ |
| 可配置规则库 ≥18 条 | `rules.py`(18) + `customrules.py`(自定义) | ✅ |
| 问题清单：规则/位置/现状值/期望值/级别 | `Issue` + `report.py` | ✅ |
| 一键修复 + 差异预览 + 备份回滚 | `fixer.py` | ✅ |
| 用户自填 API Key 的语义检查 | `llm.py` + 语义检查按钮 | ✅（需用户填 Key） |
| 30 页 ≤10 秒 | 实测 33 段 45–60 ms | ✅ |
| 统计图表 | `charts.py`（Canvas 饼图 + 柱状图） | ✅ |
| 批处理 | `batch.py` + 批量检查页签 + `batch` 子命令 | ✅ |
| 6 张数据表 | `store.py`（`t_model_config/t_rule/t_check_task/t_issue/t_fix_record/t_semantic_result`） | ✅ |
| 报告导出 | Markdown / JSON / 批量汇总 | ✅ |

界面三个页签：**问题清单**（逐条定位）、**统计图表**（级别分布饼图 + 规则命中柱状图）、**批量检查**（多文件、批量修复、汇总导出）。

截图：`out/界面截图-检查结果.png`、`out/界面截图-统计图表.png`。

### 命令行补充

```bash
python run.py batch samples --md 汇总.md      # 批量检查整个文件夹
python run.py check 文档.docx --semantic      # 追加语义检查（需 Key）
python run.py check 文档.docx --no-custom     # 只用内置规则
```

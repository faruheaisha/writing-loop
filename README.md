# writing-loop

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](./LICENSE)
[![Engine: Apache 2.0](https://img.shields.io/badge/Engine-Apache%202.0-green.svg)](./engine/LICENSE)
[![Agent Skills](https://img.shields.io/badge/Spec-Anthropic%20%26%20OpenAI%20Skills-111827.svg)](#即装即用兼容-anthropic-与-openai-技能规范)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](#即装即用兼容-anthropic-与-openai-技能规范)

中文写作与质检技能包（v2.2）。仓库仅保留纯净可运行的技能干货，遵循 **Anthropic Agent Skills**（`SKILL.md`）与 **OpenAI Codex / ChatGPT Skills**（`SKILL.md` + `agents/openai.yaml`）双端解析规范，克隆或解压进技能目录即可直接使用。

起草期以现代汉语章法（话题链流水句、白描物证、比兴留白、用典防伪、QUD 语篇推进）与原作者真实语料样例正向领路；成稿后以零依赖毫秒级机械扫描（精确到行号，免疫 Markdown 非正文结构与未闭合引号穿透）配合本地 RoBERTa 分段检测、改写质量守卫与 Burrows Delta 整句窗口文风画像，单轮定点微创到收敛。

## 核心特性

- **双端标准解析与精准触发**：严格对齐 Anthropic 与 OpenAI 的 `SKILL.md` 白名单字段规范（无 BOM UTF-8、无 XML 尖括号、全引号单行安全 YAML），内置 `agents/openai.yaml` 声明入口与隐式路由策略；显式排除程序脚本编写与代码重构误触发，500 字内短稿零读档直通。
- **正向章法先于负向禁令**：`kickoff.py` 覆盖 10 类核心场景与 20 个常见体裁别名，一次组装场景目标、六维语域旋钮、现代汉语筋骨准则、个人表达 DNA 与 KATE 最近邻旧稿样例，不在起草期倾倒细碎正则禁令。
- **实证校准与防过度改写**：撤销「句长均匀度、段长均匀度、比喻密度、正文问句、被字句、进行+动词」等已证伪伪特征，保留 33 条词句规则与 3 条段落构式规则，内置成语高频误用、塑料死喻、生理情绪套话与虚化动宾壳子拦截。
- **对抗级防穿透与零返工行号定位**：引文豁免限制在段内或单行，阻断单处未闭合引号跨段吞噬全文；拦截 17 类零宽与双向隐形作弊字符并统计真实总命中数；Markdown 代码块、YAML 头、表格与链接 URL 自动等长遮罩，全部命中直报 1-based `[行N]` 或 `行L1-L2` 坐标。
- **跨格式直读与本地隐私推理**：全套脚本原生支持 `.txt`、`.md`、`.docx`（自动反转义 XML 实体）及带首字节 UTF-8 BOM 文本。内嵌晓语中文 RoBERTa 引擎（默认 `int4` 权重 60.2MB），经跨段窗口去重与按长凑批推理加速，全程本地 CPU 运行，不联网上传一字。

## 即装即用（兼容 Anthropic 与 OpenAI 技能规范）

### 方式一：直接克隆入技能目录（零配置即用）

```bash
# Claude Code / Anthropic Agent Skills
git clone https://github.com/faruheaisha/writing-loop.git ~/.claude/skills/writing-loop

# OpenAI Codex / Agent Skills
git clone https://github.com/faruheaisha/writing-loop.git ~/.codex/skills/writing-loop
# 或放入项目级 .agents/skills/writing-loop
```

### 方式二：运行一键安装器（自动探测目录、按需拉权重并跑自测）

```bash
git clone https://github.com/faruheaisha/writing-loop.git
cd writing-loop
python install.py
```

安装脚本自动探测 `~/.workbuddy/skills`、`~/.claude/skills`、`~/.agents/skills`、`~/.codex/skills`，仅将纯净运行时文件部署为单技能 `writing-loop`（内含 `engine/`，消除双技能碰撞）。

```bash
python install.py --target ~/.claude/skills   # 指定目标技能目录
python install.py --no-weights                # 离线安装，立即启用章法、扫描与个人画像
python install.py --standalone-engine         # 可选：同时暴露同级独立的晓语检测子技能
python install.py --uninstall                 # 干净卸载
```

## 命令行速查（全命令支持 `.txt` / `.md` / `.docx`）

```bash
# 1. 开局组装：输出场景目标、语域旋钮、现代汉语章法、三行微骨架与个人语料样例
python scripts/kickoff.py "探讨技术官僚与基层损耗" --scene 杂文随笔 --words 1800
python scripts/kickoff.py "除夕夜小站" --scene 白描叙事 --profile self

# 2. 机械扫描 + 首句大纲体检：零第三方依赖，毫秒级输出 [行N] 坐标与中段三分之一区间
python scripts/scan.py 稿件.md --outline
python scripts/scan.py --text "直接传入短稿正文做快速自检"

# 3. 重度全闭环：一次跑完机械扫描、400字分段检测、改写质量守卫与个人包络核对
python scripts/loop.py 稿件.md --target 0.10 --baseline 旧稿.md --whitelist 白名单.txt

# 4. 个人文风画像（Burrows Delta 经典 Manhattan 距离 + 整句滚动窗口）
python scripts/style_profile.py build ~/文档/我的旧稿/ --name self
python scripts/style_profile.py card --name self
python scripts/style_profile.py drift 新稿.docx --name self
python scripts/style_profile.py check 新稿.docx --name self --json

# 5. 全量回归与规范自测（零第三方依赖）
python tests/run_tests.py -v
```

若启用本地 RoBERTa 分段检测，需安装 CPU 推理依赖并拉取一次权重。

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers
python engine/scripts/download.py             # 默认拉取 int4 (60.2MB)；可选 --bits 8 或 --bits 32
```

## 目录架构

```text
writing-loop/
├── SKILL.md                    # 技能主清单（兼容 Anthropic 与 OpenAI Agent Skills 规范）
├── agents/
│   └── openai.yaml             # OpenAI Codex / ChatGPT 技能界面与隐式调用配置
├── scripts/
│   ├── kickoff.py              # 开局正向章法、六维语域旋钮与个人样例组装器
│   ├── scan.py                 # 零依赖行号级扫描器（Markdown 免疫、防穿透、首句大纲）
│   ├── loop.py                 # 一令全闭环驱动器（扫描 + 分段检测 + 守卫 + 包络核对）
│   ├── score_batch.py          # 跨文本滑窗去重与按长分桶批量推理子进程
│   └── style_profile.py        # Burrows Delta 个人文风画像、KATE 选样与整句滚动漂移
├── references/
│   ├── 章法与手法.md           # 现代汉语话题链、化定为谓、白描、比兴、用典与留白温差
│   ├── 思辨.md                 # 破论点塌缩、正反合、QUD 隐含问题树与学术 15 条硬门禁
│   ├── 场景模型.md             # 六维场景定位模型与 15 类体裁锚点表
│   ├── 语域参数.md             # 六旋钮语域调校与硬约束
│   ├── 规则-S.md / 规则-AB.md  # 已证伪伪特征清单与 S/A/B 级微创改写示例
│   ├── 闭环.md                 # 滑窗聚合刻度、分段定位原理与停止红线
│   └── 合规与责任.md           # 引用溯源、署名边界、法定格式与隐私脱敏
├── engine/                     # 内嵌未修改第三方检测组件（xiaoyu-chinese-ai-detect, Apache-2.0）
├── install.py                  # 单技能安装器（安装至目标目录时自动剥离非运行时文件）
└── tests/
    └── run_tests.py            # 全量零依赖回归与双端规范校验套件
```

## 物理边界与诚实承诺

1. **不承诺代笔刷低分**：只要句子由大模型生成，即便换成散文腔或口语打断腔，在统计检测器下依然呈高概率；真人原稿一旦交由模型改写约三成句子，原有低分同样失效，故真需极低检测分时请走**陪跑模式**由作者亲手落笔。
2. **保护短句体裁与正常修辞**：质量守卫在核查 `15` 字句长中位数红线时，自动豁免原本即属短句体裁的口播稿与短剧对白基线，仅拦截改写造成的异常碎句化与实词流失（`<85%`）。
3. **不做作者身份司法鉴定**：个人画像测量的是功能词、标点与句长分箱的表面统计距离（语料满 `5` 篇且累计 `≥3000` 字后方启用包络判定），用于找回个人气口与定位跑调段落，不作真伪鉴证。
4. **阻断字符级作弊**：正文内部夹带零宽或双向隐形控制符时，`loop.py` 以退出码 `3` 直接阻断（文件首字节合法 UTF-8 BOM 自动剥离，绝不冤判）。

## 开源许可与权利说明

本项目主体代码与文档采用保守的强著佐权协议 **GNU General Public License v3.0（`GPL-3.0-only`）**，详见 [`LICENSE`](./LICENSE) 与 [`NOTICE.md`](./NOTICE.md)。

- **禁止闭源商业包壳**：任何基于本项目的修改版、衍生技能包或集成软件在分发时，必须保留版权声明并以 `GPL-3.0` 协议完整开源。
- **用户文稿权利独立**：你使用本工具创作、检测、润色的任何文章与本地个人文风画像，其全部权利均归你本人所有，不受 `GPL-3.0` 协议约束。
- **内嵌引擎独立授权**：`engine/` 目录原样保留自 `fuyi-git/xiaoyu-chinese-ai-detect`，遵循其原有的 [`Apache License 2.0`](./engine/LICENSE)（与 `GPL-3.0` 兼容）。

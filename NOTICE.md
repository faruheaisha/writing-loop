# NOTICE

## 本项目自身（writing-loop）

Copyright (C) 2026 faruheaisha

`writing-loop`（含 `SKILL.md`、`install.py`、`references/`、`scripts/`、`tests/` 及根目录研究文档，不含 `engine/` 目录）采用 **GNU General Public License v3.0（`GPL-3.0-only`）** 开源许可，完整协议全文见根目录 `LICENSE`。

- 任何复制、修改、打包或再分发本项目的衍生作品，均须保留原始版权声明，并以相同 `GPL-3.0` 协议开放完整源代码，禁止闭源商业封装分发。
- 用户使用本工具起草、扫描、诊断或润色所产出的个人文稿，以及由用户本人语料构建的个人文风画像（`~/.writing-loop/profiles/`），其著作权与数据归用户本人独立享有，不受 `GPL-3.0` 传染约束。

## 内嵌的第三方独立组件

**本地中文检测引擎组件（`engine/` 目录）**：`fuyi-git/xiaoyu-chinese-ai-detect`（Copyright 2026 fuyi163），采用 **Apache License 2.0** 许可（与 `GPL-3.0` 单向兼容）。
本项目在 `engine/` 目录下原样保留其脚本、分词词表配置、`engine/LICENSE` 与 `engine/NOTICE`，未作任何字节修改；预训练模型权重不由本仓库分发，由用户按需自行拉取。

## 规则与统计方法的学术及开源溯源

本项目未复制下列仓库的代码实现，仅在实证核验后借鉴其配对测量方法、公开统计口径或文献线索，特此致谢：

- `larashero3-dotcom/lieflat-less-ai-tone`（CC BY-NC 4.0）：同题同事实配对实验设计、分母测量失误复盘与已证伪特征复核口径
- `Nanako0129/sepia`（MIT）：三十维叙事量规、情绪四模式实测均值、QUD 隐含问题树方法
- `MrGeDiao/shuorenhua`（MIT）：改写实词保留率 0.90/0.85 参考线
- `blader/humanizer`（MIT）与 `op7418/Humanizer-zh`（MIT）：常见模型表面句式分类线索
- `zenstory-ai/oh-story-claudecode`（MIT）：短文本最小命中数与密度双门判定思路
- `Xiaoyangy/novel-studio`（Apache-2.0）：内容完整性地板与软副词密度参考线
- 学术文献溯源：Burrows (2002) *Delta*、Liu et al. (2021) *KATE*、Kim et al. (2026) *Argument Collapse*、*Chengyu-Bench* (arXiv:2506.18105)、*The Width of a Voice* (2026)、*StyloPrompt* (AIED 2026)、*PersonalBench* (2026)

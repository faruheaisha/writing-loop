# NOTICE

## 本项目自身

writing-loop（SKILL.md、references/、scripts/、tests/）由 faruheaisha 开发，采用 MIT 许可。

## 依赖的第三方组件

**检测引擎组件**：fuyi-git/xiaoyu-chinese-ai-detect，Apache License 2.0。
本项目调用其 detect.py 与预训练权重，权重与分词器不由本仓库分发。
用户须自行获取该组件。原始许可保留于该组件仓库。

**规则方法的思想来源**（未复制其代码，只借鉴方法与阈值，均已在溯源文档中列明）：
- larashero3-dotcom/lieflat-less-ai-tone（CC BY-NC 4.0）：配对实验方法与阈值口径
- Nanako0129/sepia（MIT）：三十维量规、误判白名单、QUD 方法
- MrGeDiao/shuorenhua（MIT）：实词保留率 0.90/0.85
- blader/humanizer（MIT）：二十六条模式分类
- op7418/Humanizer-zh（MIT）：中文专有条目
- zenstory-ai/oh-story-claudecode（MIT）：双门判定与阈值
- Xiaoyangy/novel-studio（Apache-2.0）：内容完整性地板、人类锚点乘子思想
- Lniosy/qiqing-liuyu（未见 LICENSE 文件）：未直接引用其代码


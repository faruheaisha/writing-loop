# writing-loop

中文写作质检工作台：按场景定位写作，按规则扫描模型腔，跑本地 AI 检测，按分段定位要改的段落，复检到收敛。附风格画像与风格卡，给模型提供你自己的写作参照。

## 一键安装

```bash
git clone https://github.com/faruheaisha/writing-loop.git
cd writing-loop
python install.py
```

脚本会自动探测技能目录（`~/.workbuddy/skills`、`~/.claude/skills`、`~/.agents/skills`、`~/.codex/skills`，或项目级 `.claude/skills`），装好本技能与检测引擎，下载权重，跑一遍自测。

```bash
python install.py --target ~/.claude/skills   # 指定目录
python install.py --no-weights                # 离线安装，只用扫描功能
python install.py --uninstall                 # 卸载
```

克隆后不装也能直接跑：检测引擎已随仓库附带，`scripts/` 会自动找到 `engine/`。

## 立刻能跑

```bash
# 机械扫描，零依赖
python <本目录>/scripts/scan.py 稿件.txt

# 整篇检测加分段定位（需装检测引擎组件）
python <本目录>/scripts/loop.py 稿件.txt

# 规则自测，37 项
python <本目录>/tests/run_tests.py
```

## 两层结构

1. **本技能**：扫描、守卫、场景模型、风格画像。零第三方依赖，Python 3.10 以上。
2. **检测引擎**（`engine/`）：中文 RoBERTa 二分类器，int4 权重 60MB。代码随仓库附带，权重需首次下载（约 6 到 7 分钟），也可离线安装后单独下载。

## 画像需要你自己的旧稿

```bash
python <本目录>/scripts/style_profile.py build ~/文档/我的旧稿/ --name self
python <本目录>/scripts/style_profile.py card --name self
```

docx 直接支持。单篇 150 字起，总量 3000 字、5 篇以上才稳定。没有语料就没有画像，这是功能定义。

## 能干什么

- 六维场景定位：目的、读者、评价者、范式、事实责任、节奏，坐标派生结构、语域、合规、检测四类约束
- 模型腔扫描：S 级必改、A 级按密度加最小命中、B 级弱信号，每条带改法和出处
- AI 检测：整篇概率加分段定位，长文不会被整篇分稀释
- 改写守卫：实词保留率地板、语义噪声拦截、字数与句长红线
- 风格画像与风格卡：把你的风格变成模型可读的参照
- 三种模式：代笔、编辑、陪跑，按你要的质量还是低分选

## 不干什么

- 不承诺「降到 10% 以下」。句子由模型产出就压不下去，要极低分须由人落笔。
- 不做作者判定。风格跨度大的人，AI 文可能比本人节选更接近画像。
- 不做字符级作弊。零宽字符直接拦截。

## 许可

MIT。第三方组件与思想来源见 NOTICE.md。

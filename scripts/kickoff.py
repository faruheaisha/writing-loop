#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 faruheaisha
# SPDX-License-Identifier: GPL-3.0-only
"""writing-loop · 开局一令组装器（v2.2：场景目标 + 语域六旋钮 + 现代汉语章法 + 个人表达 DNA + 真人样例）

不在起草期向模型倾倒 33 条细碎正则禁令，也不贴「顶级文学大师」这类诱发端架子腔的高帽。
一条命令输出起草所需的全部正向上下文，省去连读多份参考文档的工具往返。

用法：
  python kickoff.py "探讨技术官僚与基层损耗" --scene 杂文随笔
  python kickoff.py "第三章：寒潭破境" --scene 修仙玄幻 --stance 绝境算计
  python kickoff.py "Q3 跨部门研发效能复盘" --scene 管理汇报
  python kickoff.py "意识的不可计算性" --scene 学术驳论 --profile self
  python kickoff.py "除夕夜车站" --scene 白描叙事 --exemplar 样例.docx
"""
import argparse
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))

SCENES = {
    "白描叙事": {
        "aim": "以少总多，冷笔写热事",
        "reg": "单人限知视角钉死 ｜ 规范白话夹本色口语 ｜ 零术语 ｜ 句长随呼吸起伏 ｜ 动作现场先入",
        "craft": (
            "以具体动作与器物磨损痕迹立住现场，剥离『沧桑、斑驳、凄凉』等替读者下结论的形容词包浆。"
            "写情绪守四模式配比：反常小动作第一，直白命名（如『他慌了』）第二，内省判断第三，"
            "克制冷汗、心跳、喉头发紧、铁锈味等生理套话。钉死单人限知视角，不跳出视角剧透。"
        ),
        "mid_shift": "行至中段三分之一处主动换质地：紧凑对白后切入冷静的器物环境速写，放入一个开头未预告的细小变数。",
        "ending": "允许偶然、他人或客观规矩决定结局；收在最后一个具体动作或未接下去的半句话上，严禁点破寓意或自我和解升华。",
    },
    "修仙玄幻": {
        "aim": "期待阶梯与规则博弈兑现",
        "reg": "主角限知视角 ｜ 利落叙事忌现代出戏网梗 ｜ 设定随交手兑现 ｜ 交锋短句蓄势长句 ｜ 压迫处境先入",
        "craft": (
            "按『期待铺垫—受挫承压—意外变数—越级反制（四阶推进）』组织章内张力。"
            "功法代价、灵石损耗与境界压制靠具体交手动作与筹码计算落地，不写大段设定说明书，主角不靠喊口号顿悟。"
        ),
        "mid_shift": "中段引入第三方窥伺、阵法暗门或功法反噬等突发阻力，把顺风推演逼入险中求胜的算计。",
        "ending": "断在动作余波或下一重更大危机的露头处（章末留钩），绝不总结本章感悟。",
    },
    "硬核科幻": {
        "aim": "动作空间与物理硬约束推演",
        "reg": "冷峻第一或第三人称 ｜ 工程克制语调 ｜ 硬术语精确不堆伪词 ｜ 中短句记操作 ｜ 反常读数或约束先入",
        "craft": (
            "把笔墨从被凝视的光影氛围空间拉回角色操作、磨损、受限的动作空间：散热极限、燃料账本、通信延迟与工程冗余。"
            "技术设定前后严丝合缝，不用空洞的量子或宿命修辞糊弄机制。"
        ),
        "mid_shift": "中段暴露原方案未算入的物理副产物或制度死锁，迫使角色在硬约束下做有损取舍。",
        "ending": "停在客观读数、工程结果或沉默的物理事实上，拒绝温情说教。",
    },
    "杂文随笔": {
        "aim": "刺破流行伪共识与账本重构",
        "reg": "克制观察视角 ｜ 雅洁现代白话 ｜ 术语出现即拆解 ｜ 长短参差有顿挫 ｜ 具体切口或反常识账本先入",
        "craft": (
            "不做两边讨好的端水折中。先立靶点出大众习以为常的流行说法（正题），"
            "紧接着算清它没说出口的隐性代价、买单人群与失灵边界（反题），最后换一把尺子重提真问题（合题）。"
            "化典入骨如水中着盐，不排比古人掉书袋，不用时代齿轮、双刃剑等死喻。"
        ),
        "mid_shift": "中段横插一笔看似跑题的具体史料切片或日常账目，与主命题形成冷峻互证。",
        "ending": "话说到命门即断崖勒马，留一道未决追问给读者，不喊口号、不回头复述引言。",
    },
    "学术驳论": {
        "aim": "图尔敏五元闭环与善意最强反驳",
        "reg": "第三人称或本文主语 ｜ 高正式度学术书面语 ｜ 核心术语≤3个定死不换词 ｜ 严密中长句≤45字 ｜ 研究缺口与可证伪主张先入",
        "craft": (
            "核心主张写成可被证伪的陈述句，关键术语首次定义后全文不换同义词。"
            "严守主张（Claim）—证据（Data）—桥接保证（Warrant）—反驳块（Rebuttal）—成立边界（Qualifier）闭环；"
            "数据与结论之间必须写出桥接理由，不拿案例故事顶替机制证明。"
        ),
        "mid_shift": "中段正面引入反对立场最有杀伤力的论证（禁用荒谬、显然等贬损词），交代原主张是否因此限缩。",
        "ending": "回到经反驳校准后的主命题，点明知识净增量与尚未解决的边界条件，不抛新论点。",
    },
    "管理汇报": {
        "aim": "结论先行（BLUF）与决策权责穿透",
        "reg": "客观业务主语（忌我觉得） ｜ 简明商务书面语 ｜ 指标口径对齐 ｜ 短句带实数 ｜ 结论与待拍板事项先入",
        "craft": (
            "首段直接给结论、核心指标涨跌与待拍板事项（SCQA 骨架）。"
            "通篇剥离抒情形容词与公文空转黑话（赋能、抓手、闭环），每条判断绑定基准数、对比数、归因链与负责人。"
        ),
        "mid_shift": "中段挑明方案的非对称风险、资源缺口及失效触发条件，不报喜藏忧。",
        "ending": "落到具体行动项、责任人、交付时点与所需跨部门授权，言尽即止。",
    },
    "机关公文": {
        "aim": "行文关系严整与实数实责",
        "reg": "法定机关行文主语 ｜ 庄重公文语体（GB/T 9704） ｜ 规范政策术语 ｜ 句法严整实词收口 ｜ 依据与事项先入",
        "craft": (
            "严格匹配上行、平行、下行文种规范（参照 GB/T 9704）。"
            "依据、现状、措施、分工、时限五要素齐全；每项举措有明确主语与量化口径，杜绝无主语空洞表态。"
        ),
        "mid_shift": "措施部分按轻重缓急与职责边界分条列实，不交叉推诿，不凑对仗空话。",
        "ending": "按法定祈请语或执行要求干净收尾，核准署名、成文日期与附件说明。",
    },
    "影视短剧": {
        "aim": "可拍摄动作与错位潜台词博弈",
        "reg": "纯外部镜头视角 ｜ 口语潜台词 ｜ 零书面解释词 ｜ 台词十五字内推挡 ｜ 场号景别与冲突动作先入",
        "craft": (
            "先立分场节拍再出对白。镜头只写演员能演出来、摄影机能拍到的外部动作与器物交互。"
            "台词严禁替观众广播背景设定；人物在冲突中多用反问、岔开话题、抓话柄或沉默完成攻守推挡。"
        ),
        "mid_shift": "场中关键筹码或隐瞒信息提前漏底，瞬间倒转双方攻守位置。",
        "ending": "切在动作悬停或局势骤变的一瞬，不写事后解释台词。",
    },
    "口播脚本": {
        "aim": "听觉呼吸气口与单点穿透",
        "reg": "第一与第二人称对话 ｜ 自然口语呼吸感 ｜ 术语当场翻成大白话 ｜ 单句十五字上下 ｜ 三秒痛点或反常识结果先入",
        "craft": (
            "专为耳朵写，不拿书面通稿硬念。前三秒直接抛反常识结果或切身痛点抓人；"
            "单句控制在十五字上下，顺着自然说话的气口断句，少用倒装与书面关联词，术语出现当场用大白话拆开。"
        ),
        "mid_shift": "每三十秒给一个具体数字或生活切片托底，用自问或反诘带住听众注意力。",
        "ending": "收在一句听完能立刻转述给别人的干脆判断上。",
    },
    "冷面幽默": {
        "aim": "声调温差反讽与反高潮解构",
        "reg": "冷眼一本正经叙述视角 ｜ 庄词谐用与平淡记账交替 ｜ 按反差调配术语 ｜ 铺垫绵密收句短促 ｜ 荒诞反常结果先入",
        "craft": (
            "幽默靠叙述声调与事实份量的错位，绝不靠感叹号、自夸好笑或堆砌过气网络烂梗。"
            "交替运用『大词小用』（拿考据或公文腔一本正经分析鸡毛蒜皮）与『重事轻说』（拿记买菜账的平淡口气写荒诞变故）。"
        ),
        "mid_shift": "中段顺着荒诞前提极其严肃地往下算细账，把表面体面的逻辑推到自相矛盾的墙角。",
        "ending": "铺垫足预期后轻轻一笔反高潮（Anti-climax）收煞，冷面退场。",
    },
}

SCENE_ALIASES = {
    "散文": "白描叙事",
    "短篇小说": "白描叙事",
    "长篇小说": "白描叙事",
    "故事": "白描叙事",
    "修仙网文": "修仙玄幻",
    "网文": "修仙玄幻",
    "科幻": "硬核科幻",
    "评论": "杂文随笔",
    "公众号": "杂文随笔",
    "论文": "学术驳论",
    "学术论文": "学术驳论",
    "工作总结": "管理汇报",
    "述职汇报": "管理汇报",
    "公文": "机关公文",
    "剧本": "影视短剧",
    "分镜脚本": "影视短剧",
    "口播": "口播脚本",
    "商业文案": "口播脚本",
    "抽象幽默": "冷面幽默",
    "讽刺随笔": "冷面幽默",
}


def resolve_scene(scene):
    s = SCENE_ALIASES.get(scene, scene)
    return s, SCENES.get(s, SCENES["杂文随笔"])


def load_profile_context(profile_name, topic, k=3):
    sys.path.insert(0, HERE)
    try:
        import style_profile as sp
    except Exception:
        return None, []
    store = sp.store_for(profile_name)
    prof = sp.load(store)
    if not prof:
        return None, []
    dna = sp.descriptor(prof) if prof.get("baseline") else None
    exs = [a["text"] for a in sp.select_exemplars(prof, query_text=topic, k=k) if a.get("text")]
    return dna, exs


def load_profile_exemplars(profile_name, topic, k=3):
    _, exs = load_profile_context(profile_name, topic, k=k)
    return exs


def build_kickoff_prompt(topic, scene="杂文随笔", stance="正面直陈、刺破套话",
                         exemplars=None, target_words=1500, profile_name=None):
    canon_scene, cfg = resolve_scene(scene)
    dna = None
    if profile_name:
        dna, prof_exs = load_profile_context(profile_name, topic, k=3)
        if not exemplars:
            exemplars = prof_exs

    parts = [
        "# 写作任务与语域坐标",
        f"- 主题：{topic}",
        f"- 场景坐标：{canon_scene}（核心目标：{cfg['aim']}）",
        f"- 语域旋钮：{cfg['reg']}",
        f"- 对话姿态：{stance}",
        f"- 篇幅预期：约 {target_words} 字",
        "",
        "# 现代汉语章法与气口准则",
        f"1. **场景笔法**：{cfg['craft']}",
        "2. **汉语流水句与实词筋骨**：",
        "   - 立住话题后顺势承前省主语，破除『它、这、该机制』等印欧代词堆积；将多层前置『的』字长定语拆为后置短谓语；",
        "   - 用单双音节及物实词替代『实现了对…的突破、呈现出…的态势』等虚化动宾壳子；可用字面直说处绝不硬拽表演型隐喻；",
        "   - 正面直陈判断，除非纠正读者真实存在过的误解，不写『不是A而是B』式借势翻案句；记不准原典逐字原文时一律用白话直述。",
        "3. **抽象与具象两极直连**：",
        "   - 抽空半山腰温吞的中观概念词，用底层可触摸的具体物证、数字与动作细节，直接撞击高层的冷峻判断。",
        "4. **语篇推进与中段变奏**：",
        "   - 每段只回答一个推进主线的隐含子问题（QUD），拒绝段与段同义复读；",
        f"   - {cfg['mid_shift']}",
        "5. **收笔分寸**：",
        f"   - {cfg['ending']}",
        "6. **防误改护栏**：句长均匀度与人类无差异，比喻密度与正文设问人类反而更高；严禁强拆十余字碎句，严禁把正常『被字句』硬拧成生僻句。",
    ]

    if dna or exemplars:
        parts.append("")
        parts.append("# 个人表达 DNA 与原作者语料样例（贴合其句法气口与选词冷暖，勿照抄具体事实）")
        if dna:
            parts.append(f"- 表达指纹：{dna}")
        for i, ex in enumerate(exemplars or [], 1):
            parts.append(f"--- 样例 {i} ---\n{ex.strip()}")

    parts.extend([
        "",
        "# 动笔前三行微骨架（先在内部对齐这三点，再直接输出干净正文，不加前言寒暄与事后说明）",
        "1. [起笔切口] 第一句话落哪个具体时间、地点、数字、反常动作或可证伪硬判断？",
        "2. [中段变奏] 行至全文中间三分之一处，切入哪一笔未预告的具体物证、账目或阻力打破匀速平铺？",
        "3. [收笔落点] 最后一句停在哪个具体动作、客观结果或边界判断上（确保不回头总结升华）？",
    ])
    return "\n".join(parts)


def main():
    choices = list(SCENES.keys()) + list(SCENE_ALIASES.keys())
    ap = argparse.ArgumentParser(description="writing-loop · 开局正向章法与样例组装器")
    ap.add_argument("topic", help="写作主题或核心命题")
    ap.add_argument("--scene", default="杂文随笔", choices=choices, help="场景类型")
    ap.add_argument("--stance", default="正面直陈、刺破套话", help="对话姿态")
    ap.add_argument("--words", type=int, default=1500, help="预期字数")
    ap.add_argument("--profile", default=None, help="个人画像名（如 self），自动注入表达 DNA 与 KATE 真人样例")
    ap.add_argument("--exemplar", "--exemplar-file", dest="exemplar_file", default=None,
                    help="真人样例文件路径（支持 .txt/.md/.docx，段落间空行分隔）")
    a = ap.parse_args()

    exs = None
    if a.exemplar_file:
        if not os.path.isfile(a.exemplar_file):
            sys.stderr.write("样例文件不存在：%s\n" % a.exemplar_file)
            return 2
        sys.path.insert(0, HERE)
        import scan as _sc
        raw = _sc.read_text(a.exemplar_file).strip()
        exs = [p.strip() for p in raw.split("\n\n") if len(p.strip()) >= 40][:3]

    prompt = build_kickoff_prompt(
        a.topic, scene=a.scene, stance=a.stance,
        exemplars=exs, target_words=a.words, profile_name=a.profile
    )
    print(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())

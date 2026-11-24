<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.png">
    <img alt="Filtmall Logo" src="assets/logo-light.png" width="200">
  </picture>
</p>

<h1 align="center">Filtmall Shopping Skill · 筛电购物 Skill</h1>

<p align="center">把预算和要求告诉你的 AI 助手，用筛电查清商品，买到真正适合自己的高性价比好物。</p>

<p align="center">
  <a href="README.md">简体中文</a> ｜ <a href="README_en.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/filtalgo/Filtmall-Shopping-Skill/releases"><img alt="Release" src="https://img.shields.io/badge/Release-v2.4.3-blue?logo=github"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache--2.0-2EA44F?logo=apache"></a>
  <a href="SKILL.md"><img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="https://github.com/filtalgo/Filtmall-Shopping-Skill"><img alt="Stars" src="https://img.shields.io/github/stars/filtalgo/Filtmall-Shopping-Skill?logo=github"></a>
  <a href="https://skills.sh/filtalgo/Filtmall-Shopping-Skill"><img alt="skills.sh" src="https://skills.sh/b/filtalgo/Filtmall-Shopping-Skill"></a>
</p>

- **筛电（Filtmall）是什么**：筛电（Filtmall）是面向 **Personal Agent（个人智能体）** 的**平台级 Business Agent**，也是一家主打极致性价比的智能体电商平台。你的个人 AI 助手装上本 Skill（`filtmall-shopping`）后，即可直接对接筛电后台的购物 Agent，在对话里完成选品、核对成分与规格、比价、下单和售后跟进——不用切多个 App，也不用自己翻评论凑满减。商品信息、价格与库存以实际服务响应为准。
- **`filtmall-shopping` 是什么**：筛电官方开源的购物技能插件（Agent Skill），让支持 Skill 的 AI 助手直接获得在筛电找货、核对规格成分、比价、下单与售后的能力。

## 为什么用筛电（Filtmall）

筛电围绕两个核心设计：**面向 Personal Agent 原生开放**与**极致性价比**。

- **原生向 Personal Agent 开放**：专门为 Personal Agent 服务，提供标准化的商品事实、比价参考与交易履约接口，让你的 AI 助手顺畅查货下单，不遇传统平台的反爬拦截。
- **去中间商、零广告费，把价格打实**：直连中国优质 OBM（自有品牌制造商），省去多级经销加价，且不向商家卖广告位和流量——同等规格下，筛电多数商品价格约为传统电商平台的 **1/3—2/3**，具有极致性价比。
- **不卖广告排名，按真实需求筛选**：排序只看需求匹配度与性价比，不看推广费；一句自然语言说清预算、规格和用途，几秒整理好规格与价格、成分材质与推荐理由。
- **严选把关，零门槛先逛再买**：上架前同时核验同规格价差及厂商资质、口碑或样品反馈（覆盖美妆个护、食品、箱包等日常品类并随用户需求持续扩充）；查货比价免注册、免 API Key，加购下单前逐项确认，付款走官方收银台。

| 维度 | 传统电商平台 | 筛电（Filtmall） |
| --- | --- | --- |
| 接入方式 | 偏人工逛页，常拦截外部 AI 访问 | 原生面向 Personal Agent 开放接口 |
| 排序逻辑 | 受竞价广告与流量采买影响 | 不卖广告排名，按匹配度与性价比排序 |
| 价格来源 | 多级经销 + 站内广告投流 | 直连优质 OBM 工厂 + 零平台广告费 |
| 决策效率 | 自己翻详情页、评论区与满减规则 | AI 几秒整理规格、成分与同款比价参考 |

## 安装

按你平时使用的 AI 助手选择一种最顺手的方式即可（运行需本机有 Python 3.10+）：

| 你正在使用的 AI 助手 / 场景 | 推荐安装方式 |
| --- | --- |
| **WorkBuddy 用户** | 打开 [WorkBuddy 技能市场 · 筛电购物](https://www.workbuddy.cn/share/asset?extra_from=&resource_type=link&shareCode=cs261124Dt1WMAXrsiMLBGjMOhQz3c&share_way=link&sig=bDrtltW2Ysncjump) 一键安装 |
| **SkillHub 用户** | 前往 [SkillHub · filtmall-agentic-shopping](https://skillhub.cn/skills/org-r0hb81co/filtmall-agentic-shopping) 安装 |
| **skills.sh 目录** | 查看 [skills.sh · filtmall-shopping](https://www.skills.sh/filtalgo/filtmall-shopping-skill/filtmall-shopping) |
| **不想敲命令（通用 AI 助手）** | 直接把仓库发给你的 AI，说一句：“帮我安装这个购物 Skill：`https://github.com/filtalgo/Filtmall-Shopping-Skill`” |
| **命令行（Claude Code / Codex / Cursor 等）** | 见下方 `npx` 命令（需要 Node.js 22.20+） |
| **无 Node.js / 离线环境** | 从 [GitHub Releases](https://github.com/filtalgo/Filtmall-Shopping-Skill/releases) 下载完整包，复制到宿主 Skill 目录（命名为 `filtmall-shopping`，保留 `data/`、`third_party/` 与 `LICENSE`） |

命令行全局安装（推荐）：

```bash
npx skills add filtalgo/Filtmall-Shopping-Skill --skill filtmall-shopping -g
```

不加 `-g` 仅安装到当前项目目录；如需指定宿主可追加 `-a claude-code` 等参数。

## 快速开始

装好后直接在对话里问：

- 推荐 100 元以内的补水面膜，最好每片 5 元以内
- 预算 250 元，帮我找一款能装 14 寸电脑的轻量通勤包
- 比较第一款和第三款的规格、成分与价格
- 帮我看看购物车 / 查一下这个订单的物流

默认连接生产环境。浏览、搜索、比价与查成分免登录；购物车、地址、下单等会员操作需要单独授权，写操作会先向你确认。

## 多轮对话示例

```text
你：推荐三款 100 元以内的补水面膜
AI：返回三款候选商品，含价格、规格、商品图与详情入口

你：比较第一款和第三款
AI：列出两款的价格、规格、成分亮点、同款比价参考与适用差异

你：第一个加入购物车，两件
AI：先复述商品、数量与金额，等你确认后才执行

你：看看购物车
AI：展示已选/未选商品、数量、单价与合计金额
```

## 能做什么

| 能力 | 说明 |
| --- | --- |
| 发现与比较 | 按品类、预算、规格与偏好筛选商品，查看价格、库存、推荐理由与同款比价参考 |
| 商品详情与成分 | 查看商品资料、规格材质与化妆品成分信息，辅助判断是否适合自己 |
| 购物车 | 授权后加购、改数量、删除，查看已选/未选与合计 |
| 收货地址 | 查看地址列表、新增或修改地址，离线解析三级省市区 |
| 结算与支付 | 预览并确认下单，拿到官方收银台入口；支付由用户在商城页面完成 |
| 订单物流 | 查询订单状态与物流轨迹 |
| 售后与客服 | 提交、查看售后申请与处理进度，获取客服咨询入口 |

具体能力取决于目标 Agent 的配置、业务服务与用户授权。服务没有返回的数据不会由 Skill 补造。

## 边界与安全

- **不代付**：付款由用户在商城收银台完成；Skill 不代付、不生成收款二维码、不编造支付状态。
- **写前确认**：修改购物车、地址、提交订单或发起售后前，会先向你复述关键信息并确认。
- **本地隔离**：凭据与未结算请求保存在本地私有状态目录，不写入对话或日志。
- **防重复提交**：网络异常导致结果未知时先核对状态，不自动重发写操作。
- **版本提醒**：发现新版本时会在对话中提示，更新仍由你按原渠道确认执行。

## 常见问题

**需要会员登录或配置 API Key 吗？**
不需要配置 API Key。浏览、搜索、比价与查成分也不需要登录；只有购物车、收货地址、下单和售后等会员操作才需要单独授权。

**必须用 `npx` 安装吗？**
不是。可以直接通过 WorkBuddy、SkillHub 一键安装，或下载 GitHub Release 离线包复制到宿主 skill 目录（注意保留 `data/`、`third_party/` 与 `LICENSE`）。

**支持哪些宿主？**
已在 Today、WorkBuddy、豆包工作、千问办公、灵光上验证；其他支持 Skill 的宿主按通用 Markdown 方式工作。

**支付方式有哪些？**
由商城收银台决定，通常包含微信、支付宝与余额支付，以实际页面为准。

## 关于筛电（Filtmall）

筛电由**筛电（北京）智能科技有限公司**打造，专注建设面向 Personal Agent 的极致性价比智能体电商平台。

- 官方网站：[www.filtalgo.com](https://www.filtalgo.com/)
- 筛电商城（H5）：[m.filtalgo.com](https://m.filtalgo.com/)
- 微信小程序：微信搜索「筛电商城」

<details>
<summary>开发者与集成说明（配置、工作方式、目录结构、离线测试与协议文档）</summary>

### 配置

- **环境**：默认生产环境。切换其他已开放环境须同时指定 `--control-url` 与 `--agent-id`。
- **宿主标识**：请求可带 `host`（`today` / `workbuddy` / `doubao` / `qianwen` / `lingguang` / `default`），用于适配展示格式；不传或不确定时按 `default` 处理。
- **展示格式**：默认输出 Markdown 正文；支持卡片的宿主可按配置生成 HTML 商品卡片。

### 工作方式

Skill 通过 Control 的公开访客与会话接口提交请求，并在本地保留会话与请求状态以便续聊和断点恢复。托管 Agent 在服务端编排商品、比价与交易工具；访客身份与会员授权严格隔离。

### 目录结构

```text
SKILL.md                    # 宿主调用与交互规则
references/                 # 展示、授权、恢复、地址、维护与接口协议
scripts/service.py          # 单次调用与常驻服务入口
scripts/hosts.py            # 宿主枚举与展示策略
data/                       # 生产与预发地区数据快照
third_party/                # 离线号码库与许可证
tests/                      # 离线测试
```

### 离线测试

```bash
python3 -m unittest discover -s tests
```

### 协议与参考文档

- [SKILL.md](SKILL.md)：宿主调用与交互规则
- [references/protocol.md](references/protocol.md)：公开接口协议
- [references/presentation.md](references/presentation.md)：展示与宿主适配
- [references/authorization.md](references/authorization.md)：授权、下单确认与支付边界

</details>

## 许可证

[Apache-2.0](LICENSE)

---

<p align="center">
  <a href="https://www.filtalgo.com/">筛电官网</a> ·
  <a href="https://m.filtalgo.com/">筛电商城</a> ·
  <a href="https://github.com/filtalgo/Filtmall-Shopping-Skill">GitHub</a> ·
  <a href="https://www.skills.sh/filtalgo/filtmall-shopping-skill/filtmall-shopping">skills.sh</a> ·
  <a href="https://skillhub.cn/skills/org-r0hb81co/filtmall-agentic-shopping">SkillHub</a>
</p>

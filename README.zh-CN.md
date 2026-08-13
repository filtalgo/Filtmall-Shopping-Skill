# Filtmall Shopping Skill｜筛电购物

[English README](README.md) · [筛电官网](https://www.filtalgo.com/)

[![skills.sh](https://skills.sh/b/filtalgo/Filtmall-Shopping-Skill)](https://skills.sh/filtalgo/Filtmall-Shopping-Skill/filtmall-shopping)
![版本](https://img.shields.io/badge/version-1.6.2-0B5FFF)
![Node.js](https://img.shields.io/badge/Node.js-18%2B-339933)
![Agent Skill](https://img.shields.io/badge/Agent%20Skill-compatible-111111)

**为智能体而生的极致性价比电商。**

Filtmall Shopping 是筛电（Filtmall / Filtalgo）官方购物 Skill。它把实时商品、同款同规格比价证据、结算、订单、物流和售后完整交给智能体。用户只要说一句需求，智能体就能找到更合适、价格更有优势的商品，讲清价格优势来自哪里，并按需继续完成交易。

当前商品目录以美妆个护为主。账号授权、订单确认和支付由买家本人完成。

## 极致性价比，有证据才展示

部分已核验商品的筛电价约为主流电商公开同款同规格价格的 1/3，甚至低至约 1/4。

| 已核验案例 | 筛电价 | 公开同款同规格价格 | 节省比例 |
| --- | ---: | ---: | ---: |
| J-Jehan／涧妍美白焕亮睡眠面膜 110g | ¥39.8 | [淘宝 ¥168](https://item.taobao.com/item.htm?app=chrome&bxsign=scdsuQBsY_IiMAoCd9klt5Scy55Elp94h1Wwu0UcRsEJWnApTGHO44esUKASaEWDuGLdXcs4OkvNvyy5V7zPPhNXGlFZwQNvOgdGWufo29dkeqD5EqXFJ4zFVIHstQu1Wel&cpp=1&id=980821129625&price=168&shareUniqueId=36772195385&share_crt_v=1&shareurl=true&short_name=h.8X7WtcRQT4uBysM&sourceType=item&sp_tk=Qml2QmdHR2tYMjc%3D&spm=a2159r.13376460.0.0&suid=28533798-57B1-44A7-8C83-5BFB4C3B75EB&tbSocialPopKey=shareItem&tk=BivBgGGkX27%20CA381&un=45d70b9873b3b7be7415b581aeef1d0d&un_site=0&ut_sk=1.ZC6dqqzMfPMDAIDUzOPSNyPC_21380790_1784813927688.Copy.1&wxsign=tbwkM9VEhBW92GKCCP7l812lAmwZ0WToPFZRPJOqqWksMI_nNsblZThXqasdJAhm26Tvm13s_IPBDw1xHOF_oAF4Llv4G2y9snhxxED_PXGGbI8lX2pLT_ybuAlBwGnYBfl&skuId=5938814121614) | 76.3% |
| 片仔癀抗皱紧致面颈膜 1 盒 5 片 | ¥59 | [京东 ¥168](https://item.m.jd.com/product/10207669281949.html?utm_term=CopyURL_shareid9b2f557e1301cc81dc3f392e3f7e151998b7322f17848143202817_shangxiang_none&gx=RnAomTM2OWqgg8BN2M0-BN7ZJxq-Cg&utm_source=iosapp&utm_campaign=t_335139774&utm_medium=appshare&ad_od=share&gxd=RnAoyjVbPjHczM0UrIR2DoEXbi8Zyut7mVjfypOYubA3v_okLeiua530NnpIYo4&jkl=@EBlvs1uOiO@%20MF3390) | 64.9% |

以上比价记录分别采集于 2026 年 7 月 27 日和 7 月 25 日。价格可能随账号、地区、会员身份和优惠活动变化。Skill 会把每条价格结论限定在对应规格、来源平台和记录时间内。

## 安装

```bash
npx skills add filtalgo/Filtmall-Shopping-Skill --skill filtmall-shopping -g
```

运行环境需要 Node.js 18 或更高版本。CLI 已随 Skill 打包，无需另外执行 `npm install`。

支持文件夹或 ZIP 导入的客户端可以直接导入仓库根目录。

## 试试这样说

- “想买一款 100 元以内、保湿但别太黏的面膜。”
- “比较第 1 款和第 3 款，敏感肌更适合哪一款？”
- “我付完了吗？”
- “我最近一笔订单到哪里了？”

前两条用于商品发现和购买决策，后两条会继续查询订单与物流状态。

## 它能帮用户完成什么

| 阶段 | 用户得到的结果 |
| --- | --- |
| 发现 | 把自然语言需求转成筛电实时商品候选 |
| 决策 | 比较价格、规格、库存、商品详情和需求适配度 |
| 购买 | 继续使用持久购物车，或进入隔离的单 SKU `BUY_NOW` 流程 |
| 支付 | 生成适用于桌面网页或移动 H5 的买家结算入口 |
| 跟进 | 查询订单和物流，管理地址，取消符合条件的订单，进入售后流程 |

## 为什么筛电是智能体原生电商

- **商品信息可供智能体直接推理。** 实时价格、规格、库存、链接和比价证据以结构化结果返回。
- **一段对话贯通购物流程。** 商品发现、购买、履约和售后共享同一段需求上下文。
- **极致性价比带着证据展示。** 推荐可以同时给出外部同规格价格、来源平台、记录时间和节省比例。
- **账号与支付由买家控制。** 智能体处理重复步骤，买家打开授权和支付页面，并确认会影响账号或交易的操作。

## 工作方式

```mermaid
flowchart LR
    U["自然语言需求"] --> A["AI 智能体"]
    A --> S["Filtmall Shopping Skill"]
    S --> F["筛电商品与交易服务"]
    F --> A
    A --> H["商品、授权、支付与订单页面"]
```

智能体通过同一个命令入口工作：

```bash
node scripts/filtalgo.js <command> --json
```

内置 CLI 连接筛电的商品和交易服务。仓库包含智能体指令、流程参考、包装入口和打包运行文件；筛电电商基础设施运行在服务端。

## 安全与用户控制

- 清空购物车、删除地址、创建结算、取消订单或申请售后前，先让用户确认。
- 保护账号凭据、设备码、令牌和会话标识。
- 授权、商品、支付、订单、物流、售后和客服链接交给用户打开。
- 商品名称、价格、库存、规格、标识、订单状态和链接以实时返回结果为准。
- 用户正在发生过敏、红肿或明显肿胀时，停止商品流程并建议寻求专业医疗帮助。
- 用户要求在指定日期前送达时，搜索前先确认收货地区，让履约条件完整。

## 开发者快速开始

检查运行环境并搜索实时商品目录：

```bash
node scripts/filtalgo.js doctor --json
node scripts/filtalgo.js search "想要保湿一点的面膜，预算 100 元以内，但别太黏" --json
```

需要账号的流程从 OAuth Device Flow 开始：

```bash
node scripts/filtalgo.js auth login
node scripts/filtalgo.js auth status --json
```

继续处理购物车和结算：

```bash
node scripts/filtalgo.js cart add-item --way CART --sku-id <sku_id> --quantity 1 --json
node scripts/filtalgo.js checkout create --way CART --json
node scripts/filtalgo.js checkout prepare-payment <checkout_session_id> --link-channel mobile_h5 --json
```

查询订单和物流：

```bash
node scripts/filtalgo.js order list --page-size 5 --json
node scripts/filtalgo.js order get <order_sn> --include-items true --json
node scripts/filtalgo.js logistics get <order_sn> --json
```

执行 `node scripts/filtalgo.js help` 可以查看完整命令列表。

## 买家链接渠道

返回买家页面的命令支持：

```text
--link-channel pc_web
--link-channel mobile_h5
```

桌面浏览器使用 `pc_web`，移动客户端或 App WebView 使用 `mobile_h5`。默认渠道是 `mobile_h5`。

## 仓库结构

```text
SKILL.md                  # 智能体指令与触发元数据
references/               # 按需加载的流程规则
scripts/filtalgo.js       # CLI 包装入口
assets/filtalgo-cli.cjs   # 打包后的 CLI 运行文件
agents/openai.yaml        # Skill 展示元数据
skills.sh.json            # skills.sh 展示元数据
README.md                 # 英文说明
README.zh-CN.md           # 中文说明
```

## 1.6.2 版本更新

- 明确“智能体原生的极致性价比电商”品牌定位。
- 增加带日期和来源链接的同款同规格比价案例。
- 将分发平台与智能体可见描述聚焦到结构化购物、可见价格证据和完整交易旅程。
- 统一仓库徽章、Skill 元数据和分发元数据为 1.6.2。

## 关于筛电

筛选算法（北京）科技有限公司运营筛电（Filtmall），并以 Filtalgo 名称发布面向开发者和智能体生态的技术能力。

筛电是为智能体而生的极致性价比电商平台。它把实时商品、同款同规格比价证据、交易、履约和售后变成智能体可以可靠执行的购物流程。

[筛电官网](https://www.filtalgo.com/) · [关于筛电](https://www.filtalgo.com/about) · [面向大模型的官方资料](https://www.filtalgo.com/llms.txt) · [机器可读服务目录](https://www.filtalgo.com/agents.json)

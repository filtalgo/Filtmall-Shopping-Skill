# Filtmall Shopping Skill

[English README](README.md)

**公司官网：** [https://www.filtalgo.com/](https://www.filtalgo.com/)

Filtmall Shopping Skill 是面向开发者、智能体使用者和早期体验用户的 AI 购物技能包。它把轻量级 Node.js CLI 和买家授权流程打包成一个可直接使用的 skill 目录，让智能体能够帮助用户搜索商品、对比商品、加入购物车、创建结算单、打开买家支付页，并在支付后继续查询订单状态。

这个仓库适合公开演示和快速体验。你可以把它安装到支持 Skill 的智能体环境中，让智能体真实体验一次从“想买什么”到“生成支付链接”的购物流程。

## 你可以体验什么

- 使用中文自然关键词搜索商品，例如 `沐浴露`、`洗发露`，或者品牌和商品片段。
- 让智能体辅助完成加购、结算和支付跳转。
- 通过浏览器完成买家登录授权和钱包支付。
- 查询历史订单、订单详情、物流状态，管理收货地址。
- 体验取消订单、退款申请和售后申请等交易后流程。
- 打包后的 CLI 运行文件只需要 Node.js 18+，不需要额外 npm install。
- 当前远程测试商品目录包含美妆个护相关商品，包括沐浴露、护肤、护手、洗发护发等品类。

## 适合谁使用

- 想体验 AI 购物助手的开发者。
- 正在评估智能体电商能力的团队。
- 想录制或演示真实购物流程的 Agent 平台用户。
- 想提前了解 Filtalgo / Filtmall 生态的社区用户和合作伙伴。

## 目录结构

```text
SKILL.md                  # 智能体读取的技能说明
README.md                 # 英文项目介绍
README.zh-CN.md           # 中文项目介绍
scripts/filtalgo.js       # CLI 包装入口
assets/filtalgo-cli.cjs   # 打包后的 CLI 运行文件
agents/openai.yaml        # Skill 展示元信息
```

## 快速开始

前置条件：Node.js 18 或更高版本。

```bash
node scripts/filtalgo.js auth login
node scripts/filtalgo.js doctor --json
node scripts/filtalgo.js search "沐浴露" --json
```

登录后，智能体可以继续执行购物流程：

```bash
node scripts/filtalgo.js cart clear --confirm --json
node scripts/filtalgo.js cart add-item --sku-id <sku_id> --quantity 1 --json
node scripts/filtalgo.js checkout create --json
node scripts/filtalgo.js checkout prepare-payment <checkout_session_id> --handler wallet --json
```

将返回的 `payment_url` 发给用户。用户在浏览器中完成钱包支付后，智能体可以继续查询订单：

```bash
node scripts/filtalgo.js order list --page-size 5 --json
node scripts/filtalgo.js order get <order_sn> --include-items true --json
node scripts/filtalgo.js logistics get <order_sn> --json
```

## 推荐体验 Prompt

安装 skill 后，可以让智能体尝试：

> 我想买一款性价比高的沐浴露，请帮我在 Filtmall 上搜索、对比几个选项，确认后加入购物车并生成支付链接。

智能体应该使用本 skill 内置 CLI，展示真实商品结果，在需要确认时询问用户，并最终返回浏览器支付链接。

## 为什么这个 Demo 值得体验

很多智能体购物 Demo 只停留在“推荐商品”。Filtmall Shopping Skill 更进一步：它可以让智能体完成从推荐到加购、结算、支付跳转、查单的连续流程，更适合验证真实 Agent Commerce 场景。

用户仍然掌控登录和支付，智能体负责处理重复的购物操作。

## 关于 Filtalgo

[Filtalgo](https://www.filtalgo.com/) 正在建设面向 AI 时代的电商与智能交易基础能力，探索更智能的商品发现、辅助购物和交易流程。Filtmall Shopping Skill 是这一方向的早期公开体验项目。

访问公司官网：[https://www.filtalgo.com/](https://www.filtalgo.com/)

## 使用注意

- 不要在面向用户的输出中打印 access token、refresh token 或 client secret。
- 在结算、取消订单、退款或售后申请前，应向用户确认。
- 商品价格、SKU、订单号和支付链接应以 CLI 返回为准，不要自行编造。
- 如果搜索没有结果，可以先尝试更短的中文关键词；仍无结果时，再说明当前测试商品目录暂无匹配商品。

## 当前状态

当前版本属于公开预览 / MVP 阶段，适合 Demo、开发者体验和智能体购物流程验证。后续会继续扩展商品范围、优化智能体体验，并完善更多交易后服务能力。

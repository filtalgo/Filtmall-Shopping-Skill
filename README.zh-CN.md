# Filtmall Shopping Skill

[English README](README.md)

Filtmall Shopping Skill 是面向 Filtalgo/Filtmall 电商平台的智能体购物技能包。它把轻量级 Node.js CLI、OAuth 授权流程和 Agent Tool Gateway 调用打包在一个目录里，可以发布到 Skill 市场，也可以被智能体直接使用。

它的目标很明确：让智能体在不直接访问内部 service API 的前提下，帮助用户完成商品搜索、商品对比、购物车管理、收货地址管理、创建结算单、生成钱包支付链接，并在用户完成浏览器支付后继续查询订单、物流、取消、退款和售后状态。

## 亮点

- 面向智能体设计的完整购物流程：搜索、加购、结算、支付跳转、查单。
- 通过 buyer 前端完成 OAuth 登录和授权，CLI 只负责本地回调与 token 管理。
- 只调用 protocol-adapter 的 Agent Tool Gateway，不暴露内部 service API。
- 打包后的 skill 内置 CLI 运行文件，只需要 Node.js 18+，不需要额外 npm install。
- 当前远程测试商品目录包含约二十多款官方测试商品，覆盖沐浴露、护肤、护手、洗发护发等个人护理品类。
- 支持订单查询、物流查询、地址增删改查、未支付订单取消、已支付未发货整单退款申请，以及 `RETURN_MONEY` / `RETURN_GOODS` 售后申请。

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

## 为什么需要这个 Skill

当前很多公网智能体运行环境并没有完整的买家侧 OAuth 客户端、结算运行时和支付跳转能力。这个 skill 用 CLI 补齐这条链路：

1. CLI 打开 Filtalgo buyer 授权页。
2. 用户登录并明确授权能力范围。
3. CLI 在本地保存 OAuth token。
4. 智能体通过 CLI 调用 protocol-adapter Agent Tool Gateway。
5. 支付仍由用户在浏览器收银台中完成。

这样既能让智能体真正完成购物辅助，又能保持边界清晰：智能体不能直接访问内部 service API。

## 安全说明

- 不要在面向用户的输出中打印 access token、refresh token 或 client secret。
- 当前内置 OAuth client 用于 remote test 环境。
- CLI 只会把真实 access token 放在 HTTP `Authorization` header 中。
- 智能体不应直接调用 service、UCP 或 ACP 接口；请统一通过 `scripts/filtalgo.js` 访问 Agent Tool Gateway。

## 当前状态

当前版本属于内测 / MVP 阶段，适用于受控演示、远程开发环境联调和智能体购物流程验证。正式公网用户版还会继续完善商品范围、错误提示、授权体验和售后链路。

## 品牌说明

Filtmall Shopping Skill 属于 Filtalgo 生态的一部分，用于探索真实商品目录搜索、购物车操作、买家授权结算和交易后服务等 Agent Commerce 场景。

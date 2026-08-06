# 购物车、地址、结算与支付参考

处理购物车、立即购买、地址、结算或支付任务前，必须完整阅读并遵守本文件。

## 目录

- [购物车](#购物车)
- [地址](#地址)
- [结算与支付](#结算与支付)

## 购物车

购物车有两个隔离场景：

- `CART`：常规持久购物车，可放多个 SKU，默认场景。
- `BUY_NOW`：单 SKU 立即购买临时态，只用于用户明确要求“直接购买/立即购买”的场景。

查看购物车：

```bash
node scripts/filtalgo.js cart get --way CART --json
```

加入购物车或覆盖数量：

```bash
node scripts/filtalgo.js cart add-item --way CART --sku-id <sku_id> --quantity <num> --cover true --json
```

`--cover true` 表示把该 SKU 的购物车数量覆盖为指定数量。比如购物车有 A/B/C，B 当前 1 件，用户说“把 B 改成 3 件”，就对 B 调用 `--quantity 3 --cover true`。

只有在智能体已经向用户展示具体 SKU 对应的商品与规格、数量、收货地址和应付金额，且用户在这之后明确确认直接购买时，才执行：

```bash
node scripts/filtalgo.js buy-now <sku_id> --quantity <num> --json
```

`buy-now` 会清理 `BUY_NOW` 临时态、写入当前单个 SKU，再通过 adapter 原生 `shopping.checkout.create_from_cart` 创建 `BUY_NOW` checkout。它不会清空或修改用户的 `CART` 持久购物车，也不会自动支付。

用户说“我要买第 1 个”“数量 1、默认规格”只是在选择商品、规格和数量，不是最终结算确认。此时允许执行 `auth status` 和 `address list` 来准备确认摘要，但严禁调用 `buy-now`、`checkout create`、`checkout select-address` 或 `checkout prepare-payment`。必须先展示完整确认摘要并问一次确认：

```markdown
请确认以下购买信息：

- 商品：{商品名}
- 规格：{规格}
- 数量：{数量}
- 收货地址：{脱敏收货人、手机号和完整地址}
- 应付金额：{金额}

确认使用以上信息直接结算吗？
```

只有用户在看到该摘要后明确回复确认，才能调用 `buy-now`。不能把 `buy-now` 创建出的 checkout 或订单信息反过来当作“结算前确认”。

购物车回复模板：

```markdown
## 购物车

| 商品 | 数量 | 小计 |
| --- | ---: | ---: |
| {商品} | {数量} | {金额} |

合计：{总金额}

如果确认这些商品，我可以继续帮你创建结算。
```

## 地址

查看地址：

```bash
node scripts/filtalgo.js address list --json
```

删除地址必须二次确认：

```bash
node scripts/filtalgo.js address delete <address_id> --confirm --json
```

新增、修改、设为默认地址通常引导用户打开 CLI 返回的 `selected_buyer_links.address_list`；没有该字段时，读取 `buyer_link_targets.address_list.channels.mobile_h5.url`。

地址列表回复模板：

```markdown
## 收货地址

| 序号 | 收货人 | 手机 | 地址 |
| ---: | --- | --- | --- |
| 1 | {姓名} | {脱敏手机号} | {省市区 + 详细地址} |

你可以告诉我使用哪一个地址。

如需新增或修改地址，可以打开：[管理收货地址]({address_management_url})
```

## 结算与支付

标准结算流程：

```bash
node scripts/filtalgo.js cart get --json
node scripts/filtalgo.js address list --json
node scripts/filtalgo.js checkout create --way CART --json
node scripts/filtalgo.js checkout select-address --way CART --shipping-address-id <address_id> --json
node scripts/filtalgo.js checkout prepare-payment <checkout_session_id> --handler wallet --link-channel mobile_h5 --json
```

`checkout create` 默认调用 adapter 原生 `shopping.checkout.create_from_cart`，由服务端读取已选购物车并建立结算会话。不要再在 Agent 侧手工拼装商品金额或 checkout payload。

立即购买必须分成确认前和确认后两个阶段。

确认前只允许查询登录态和地址，并使用搜索结果中的真实商品、规格、数量和价格生成上面的确认摘要：

```bash
node scripts/filtalgo.js auth status --json
node scripts/filtalgo.js address list --json
```

用户看到摘要并明确确认后，才一次性执行立即购买结算流程：

```bash
node scripts/filtalgo.js buy-now <sku_id> --quantity <num> --json
node scripts/filtalgo.js checkout select-address --way BUY_NOW --shipping-address-id <address_id> --json
node scripts/filtalgo.js checkout prepare-payment <checkout_session_id> --handler wallet --link-channel mobile_h5 --json
```

从购物车结算时，结算前先展示购物车和地址；立即购买时，结算前先展示具体商品、规格、数量、地址和应付金额。支付入口生成后只给支付链接，不代替用户输入支付密码，除非用户在当前任务里明确授权且策略允许。

给出支付链接后，保留该次结算的 `checkout_session_id` 和已知的 `order_sn` 作为待核验上下文。不要要求用户回复“已支付”，也不要在没有新消息时持续轮询。用户下一次发送任何消息时，先自主查询订单状态：已知订单号时使用 `order get`，否则使用 `order list` 定位最近订单；展示最新状态后，再继续处理用户本次消息。

面向用户的支付回复必须以支付链接作为最后一项内容。输出支付链接后立即结束回复，不得再附加任何文字、问题或行动要求，包括但不限于“请回复已支付”“支付完成后告诉我”“完成后回来确认”“需要我帮你查询订单吗”等相同含义的表达。不要要求或暗示用户为了继续流程而发送特定消息。下一次消息自动查询订单状态属于智能体内部流程规则，不要在支付链接后向用户说明。

支付回复模板：

```markdown
## 订单已准备好

- 订单号：{order_sn；如工具未返回则写“工具未返回，可支付后查看订单列表确认”}
- 应付金额：{amount}
- 支付方式：平台收银台

[去支付]({payment_url})
```

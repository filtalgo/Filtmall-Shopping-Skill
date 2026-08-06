# 订单、物流与取消订单参考

处理订单查询、支付后状态回查、物流或取消订单任务前，必须用 `Read` 完整阅读并遵守本文件。任何 `auth status`、`order` 或 `logistics` Bash 命令都必须发生在本次 `Read` 之后，不能因为只是查询最近一单或状态简单而跳过。

默认隐藏完整订单号、交易号、运单号和物流轨迹中的电话号码。编号只保留前后少量字符，例如 `O20260729…4305`；手机号写成 `188****3085`。只有用户明确要求复制完整编号时才展示。

## 支付状态短句

“我付完了吗？”“支付成功了吗？”“钱扣了吗？”等短句必须按最近订单支付状态查询处理，不能因为缺少平台名或对话上下文而退出购物流程：

1. 先执行 `order list --page-size 5 --json`。
2. 优先定位最近的待支付、已支付、待发货或其他能回答付款结果的相关订单；必要时再执行 `order get`。
3. 能唯一定位时明确回答“已支付”“待支付”或订单返回的真实状态。不能唯一定位时展示脱敏候选并只问一个澄清问题。
4. 未完成真实查询前不得回复“没有访问支付记录的权限”，也不得让用户改查银行、支付平台、短信或订单页面。
5. 如果订单列表确实为空，如实说明当前账号暂无可查询订单；这表示账号数据不足，不要编造付款结论。
6. 能得到明确付款结论时，结论就是回复的最后一项，立即结束且不得出现任何问句。不得在结尾连续询问“想查看哪笔？”和“还有其他疑问？”。
7. 只有确实无法唯一定位时才允许追问，并且只能原样使用一个问句：“你指的是上面哪一笔订单？”

明确结论模板：

```markdown
最近一笔有效订单是 {masked_order_sn}（{商品摘要}，{amount}），状态为 **{真实状态}**，{已支付/待支付结论}。
```

## 订单

没有订单号时查列表：

```bash
node scripts/filtalgo.js order list --page-size 5 --json
```

有订单号时查详情：

```bash
node scripts/filtalgo.js order get <order_sn> --json
```

订单列表必须保留“商品”列。优先读取 `orderItems[]`，再兜底读取 `items[]`；都没有可用商品信息时，商品列写“暂未提供商品信息”。

订单列表模板：

```markdown
## 最近订单

| 序号 | 订单号 | 下单时间 | 状态 | 金额 | 商品 | 可操作状态 |
| ---: | --- | --- | --- | ---: | --- | --- |
| 1 | {masked_order_sn} | {time} | {status} | {amount} | {商品摘要} | {可取消/可查物流/可售后/需详情确认} |

需要查看完整订单或自己操作，可以打开：[我的订单]({order_list_url})
```

订单详情链接优先使用 CLI 返回的 `selected_buyer_links.order_detail`；没有该字段时，读取 `buyer_link_targets.order_detail.channels.mobile_h5.url`。不要自行拼接域名、路径或参数。

## 物流

```bash
node scripts/filtalgo.js logistics get <order_sn> --include-items true --include-traces true --json
```

如果用户没有明确订单号，先用 `order list` 列出候选订单，让用户选择，避免查错。

物流回复模板：

```markdown
## 物流信息

- 订单号：{masked_order_sn}
- 快递公司：{logistics_name}
- 快递单号：{masked_logistics_no}
- 最新进度：{latest_trace.description；其中手机号必须脱敏}
- 更新时间：{latest_trace.time}

### 物流轨迹

| 时间 | 内容 |
| --- | --- |
| {时间1} | {轨迹1} |
| {时间2} | {轨迹2} |
| {时间3} | {轨迹3} |

需要查看更多订单和物流信息，可以打开：[查看订单详情]({order_detail_url})
```

只有 `has_trace=false` 或 `packages[].traces` 为空时，才说“暂未返回具体物流节点”。如果未发货，直接说明商家尚未发货。

## 取消订单

用户没有提供订单号时，必须先查订单列表，不要直接说“没有可取消订单”。

```bash
node scripts/filtalgo.js order list --page-size 5 --json
node scripts/filtalgo.js order cancel <order_sn> --reason "用户取消" --confirm --json
```

取消前模板：

```markdown
请确认是否取消这笔订单？

- 订单号：{masked_order_sn}
- 当前状态：{status}
- 金额：{amount}

你明确确认后我再继续处理。
```

确认回复只能包含这一个问句。在用户明确确认前，只允许查询订单，不得调用 `order cancel`。

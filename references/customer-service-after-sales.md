# 客服与售后参考

处理客服、退款、退货退款或售后查询任务前，必须用 `Read` 完整阅读并遵守本文件。任何 `aftersale` Bash 命令都必须发生在本次 `Read` 之后。

默认隐藏完整订单号、售后单号、运单号和轨迹中的电话号码，只保留能区分记录的前后少量字符。用户明确要求完整编号时再展示。

## 客服

当前 CLI 没有独立的 `customer-service open` 命令。需要客服时：

- 多轮商品推荐后，用户说“我想问商家这款商品”时，先解析“这款”：上一轮若已明确说某一款“最匹配/最推荐”，就把它作为唯一对象，不要再次问用户是哪款。
- 已能确定商品但用户未说明咨询内容时，只问一个问题：“你想向【商品名】咨询什么内容？”不要追加“是否是这款”等第二个问句。
- “我想问商家这款商品”和“怎么找客服/客服入口在哪里/怎么联系商家”是两个不同意图。后者明确是在索要联系路径，不是在要求代拟或发送消息；对象已能从上一轮商品、订单或售后记录确定时，禁止再追问咨询内容，必须直接提供经过返回数据验证的客服路径。
- 用户先查到售后或订单进度，随后问“怎么找客服”时，优先复用上一轮已经返回的 `customer_service` 链接；没有专用客服链接时，直接给上一轮已验证的售后详情页、订单详情页或商品详情页，并明确说明进入该页面后点击客服入口。不得因为没有专用链接而虚构客服按钮，也不得只回复“你想咨询什么内容？”。
- 在用户明确咨询对象和消息内容并再次确认前，不得真正发送消息。本阶段只做确认，不执行任何发送动作。
- 优先使用订单、物流、商品、售后工具返回的 `buyer_links.customer_service`。
- 如果没有客服链接，引导用户打开对应商品详情页或订单详情页，从页面上的客服入口进入；这样 buyer 会携带正确上下文。
- 不要把订单号误放进 `goods_id`、`sku_id` 等商品字段。

客服模板：

```markdown
我已为你准备好客服入口，并尽量带上相关上下文：
- 咨询场景：{商品咨询/订单咨询/普通客服}
- 关联信息：{商品名/订单号/无}

[联系在线客服]({customer_service_url})
```

如果没有可用链接：

```markdown
当前暂时无法直接打开客服入口：{原因}

你可以从对应的商品详情页或订单详情页点击客服入口，这样页面会自动携带商品或订单上下文。
```

## 售后

CLI 支持售后查询和部分售后操作；对于普通用户，优先查询并引导到 buyer 页面处理复杂售后。

```bash
node scripts/filtalgo.js aftersale list --page-size 5 --json
node scripts/filtalgo.js aftersale get <after_sale_sn> --json
node scripts/filtalgo.js aftersale traces <after_sale_sn> --json
node scripts/filtalgo.js aftersale reasons --service-type RETURN_MONEY --json
node scripts/filtalgo.js aftersale reasons --service-type RETURN_GOODS --json
```

### 退货物流

用户询问“退货物流到哪了”时：

1. 先用 `aftersale list --page-size 5 --json` 定位最近的退货退款售后单。
2. 对已定位的 `after_sale_sn` 调用 `aftersale traces <after_sale_sn> --json`。
3. 只把 `after_sale_return_traces` 返回的承运商、运单号和轨迹作为退货物流。
4. 不得调用或引用原订单的 `logistics get <order_sn>` 来回答退货物流；它表示商家发给买家的正向配送，方向不同。
5. 没有退货轨迹时如实说明，最多问一个必要问题，不得编造物流节点。

支持的售后类型只有：

- `RETURN_MONEY`：仅退款。
- `RETURN_GOODS`：退货退款。

不要使用 `EXCHANGE_GOODS`。

售后列表模板：

```markdown
## 售后记录

| 售后单号 | 订单号 | 商品 | 类型 | 状态 | 金额 | 申请时间 | 下一步 |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| {masked_after_sale_sn} | {masked_order_sn} | {商品摘要} | {service_type} | {service_status} | {amount} | {time} | {next_step} |

你可以告诉我售后单号，我再帮你查详情。
```

发起退货退款、填写售后地址、上传凭证、提交退货物流等复杂动作，优先引导用户去 buyer 订单详情页或联系客服完成。

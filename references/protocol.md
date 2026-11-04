# Control 公开访客与会话协议

已按 Control 的 `server/routes/identity.py`、`sessions.py`、`sessions/results.py` 与 `sessions/public_documents.py` 核对。默认生产根地址和目标见包内 `defaults.json`；这些公开值不需要按机器配置。此入口是 Control 原生公开 API，不是标准 A2A 发现协议。

## 自动身份

1. `POST /api/v2/identity/guests`，JSON `{}`，无 AK/SK、无预先 token。成功 HTTP 201 返回 `access_token`、`access_expires_at`、`refresh_token`、`refresh_expires_at` 等字段；到期时间为 Unix 毫秒。
2. 后续使用 `Authorization: Bearer <access_token>`。临近过期时 `POST /api/v2/identity/tokens:refresh`，JSON `{"refresh_token":"<私有保存的刷新令牌>"}`。刷新 token 轮换后原子保存整组凭据。
3. 刷新失败不得自动新建访客替代旧身份，否则原会话不再可访问。HTTP 401/403 不通过换身份、扫描管理 API 或套用会员 token 绕过。

每个用户独立持有身份；宿主生成用户与对话映射。SDK/脚本不得把 bearer 发往服务端返回的任意 URL，也不跟随重定向。

## 会话与请求

创建：`POST /api/v2/sessions`，例如：

```json
{"agent_id":"production-shopping-commerce","title":"外部 Agent 会话","client_id":"filtalgo-public-skill"}
```

成功 HTTP 201，实际会话标识为响应 `id`。对该会话发送：

```text
POST /api/v2/sessions/{id}/inputs
Prefer: respond-async
Content-Type: application/json
Authorization: Bearer <平台访客 token>
```

```json
{"request_id":"skill-<每条消息独立的随机标识>","text":"用户原始请求","mode":"prompt"}
```

提交前持久保存 ID 与确切载荷。HTTP 202 只是已接收。相同 ID 必须保持相同载荷；状态不明时不创建新 ID 重做。

## 执行终态与展示

轮询 `GET /api/v2/sessions/{id}/inputs/{request_id}/result`。返回的 `execution_result.status="applied"` 是回执状态；实际执行状态看 `execution_result.operation_status`：`completed`、`cancelled`、`waiting`、`failed`。没有权威执行回执时继续等待；Control 在接受前取消的输入可按外层 `status="cancelled"` 结束。

公开内容通过 `GET /api/v2/sessions/{id}/documents?after_order=0&limit=200` 读取。响应有 `revision`、`documents`、`next_cursor`；分页直到 `next_cursor=null`，游标必须严格递增。

本客户端优先使用提交前保存的 revision，通过 `after_revision` 增量读取本轮文档；按文档 ID 合并较新版本并处理删除。边界异常、缺少本轮状态或其引用的答复不在增量结果时，回退到完整文档快照。断线恢复继续使用原请求及其原始 revision 边界，不把旧答复当作新结果。

- 每个 document 有 `document_id`、`kind`、`schema_version`、`request_id`、`revision`、`display_order`、`deleted`、`value`。
- 找当前 request_id 对应的 `kind="request.status"`，再用 `value.answer_document_id` 找真正的答复文档。答复自身的 `request_id` 可能为空，不能只过滤 request_id 而丢掉答案。
- `kind="message"` 且 `value.role="assistant"` 的 `value.content` 是当前答复。
- `filtalgo.shopping.block:*` 的 `value.block` 包含 `schema`、`payload`、`fallbackText`。商品 schema 常见 `filtmall.products/v1`、`filtmall.products/v2` 或 `filtmall.product-card/v1`。它们是会话资料，可能包含上轮商品，只展示与当前答复引用一致的商品。
- 不展示 deleted 文档、用户输入、进度或旧答复作为本轮最终输出。没有可展示答案时明确说明，不伪造。

客户端将当前权威答复放在 stdout 的 `answer`，卡片及授权资料放在 `context_documents`，不输出凭据。当前实现轮询公开快照，不声称已经消费实时 SSE。

兼容已部署的 Shopping 扩展：若 completed 的 `request.status.answer_document_id` 为空，客户端仅聚合**本轮提交前 revision 之后**的 schema1 `filtalgo.shopping.text`，标为 `source="current-turn-public-text"`。不会使用 activity 进度、旧轮次文本、用户消息或 deleted 文档；显式指向非法答复的引用也不会触发此回退。提交前的 revision 与请求 ID 一起私有保存，恢复不会改变边界。`waiting` 时仅消费本轮 revision 之后且请求 ID 匹配或为空的会员授权文档，通过 Control 设备授权接口获取用户验证链接，并在私有状态中保存 state 和加密 exchange；这些数据不输出。用户发送下一条消息时调用 device/poll 一次（遵守间隔），授权成功后才提交新消息。

## 恢复、停止与清空

- 恢复时先查原请求结果；明确 404 才可以按相同 ID、相同载荷提交。网络错误不等于 404，不做自动重发。
- `POST /api/v2/sessions/{id}/inputs/{request_id}/interrupt` 只停止自己的指定输入。返回 `stopping` 不是已停止，继续核对回执；不能推断订单或其他业务副作用已回滚。
- `DELETE /api/v2/sessions/{id}` 归档自己的会话。客户端拒绝在仍有未结算请求时直接清空；先取消并核对终态。下一条请求创建新 Control 会话。
- `POST /api/v2/identity/logout` 可撤销当前凭据；存在未结算请求时不得丢弃身份。此 Skill 不会为普通请求自动登出。

## 能力边界

访客可以委托已开放的 Agent，不获得会员账户和交易权限。会员业务使用平台已有的用户授权流程并独立验收；不要把平台 guest bearer、CLI agent_session_id 和商城 accessToken 混用。管理/部署接口不属于外部 Skill 接入流程。

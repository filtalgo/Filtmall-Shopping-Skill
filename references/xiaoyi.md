# Control 现有 A2A 协议

本参考按 agent-platform `0a597c3` 的 `filtalgo-control/filtalgo_control/channels/xiaoyi.py`、`server/app.py` 及 `tests/server/test_xiaoyi_a2a.py` 核对。描述代码契约，不代表任意环境已经启用或验收通过。

## 地址、配置和鉴权

所有方法都 POST 到运维提供的 `https://<control-host>/a2a/xiaoyi`，请求头 `Content-Type: application/json`。禁用时路由不注册；404 也可能来自代理路径错误，需运维核实。不要把 protocol-adapter `/gateway/mcp` 或 Agent Runtime 内部地址当作此入口。

宿主配置建议：`FILTALGO_CONTROL_URL`、`FILTALGO_A2A_ACCESS_KEY`、`FILTALGO_A2A_SECRET_KEY`。这些只是接入宿主的约定，不是 Control 自身环境变量。SK 只供可信宿主使用；不可信模型执行环境应由宿主代理完成签名和请求。

初始化请求头：

```text
accessKey: <provisioned access key>
ts: <current Unix time in milliseconds, decimal string>
sign: <Base64(HMAC-SHA256(UTF8(secretKey), UTF8(ts)))>
```

签名只使用时间戳字符串，不拼接请求体或 URL。签名时间窗由服务端配置；同一 AK 的同一时间戳只能成功使用一次。并发初始化由宿主协调生成当前时间窗内不重复的时间戳；签名请求重试须重新生成时间戳及签名。

```json
{"jsonrpc":"2.0","id":"init-1","method":"initialize"}
```

成功返回 `result.version="1.0"`、`result.agentSessionId`、`result.agentSessionTtl`（秒，默认 604800）。后续请求头使用 `agent-session-id: <opaque token>`。到期或 401 时在受信任宿主重新初始化；业务会话 ID 保持不变。不要重复无限尝试。商城 OAuth token 不能替代此认证。

可选初始化通知也必须有 JSON-RPC `id`，这是当前适配器的实际契约：

```json
{"jsonrpc":"2.0","id":"initialized-1","method":"notifications/initialized"}
```

该方法成功时 HTTP 200、空响应体。

## 消息与续聊

```json
{
  "jsonrpc": "2.0",
  "id": "rpc-1",
  "method": "message/stream",
  "params": {
    "id": "task-unique-1",
    "sessionId": "host-generated-opaque-conversation-id",
    "message": {
      "role": "user",
      "parts": [{"kind": "text", "text": "推荐一台适合卧室的空气净化器"}]
    }
  }
}
```

`id` 是 JSON-RPC 请求标识，`params.id` 是任务幂等标识，`params.sessionId` 是业务对话标识，三者不要混用。业务会话与任务 ID 各最多 128 字符。文本必须非空；只支持文字输入。`kind=data` 的对象元信息会被忽略，不能用来传会员授权或控制目标 Agent。图片、文件、音频不支持。服务端默认请求体上限 1MiB，可配置。

续聊：沿用业务 `sessionId`，使用新的 `params.id`。相同任务与相同载荷重试复用原输入；相同任务换文本返回冲突。对同一业务会话串行提交消息。

## SSE 消费

成功消息响应为 `text/event-stream`。服务端发送 `data: <JSON-RPC object>\n\n`，不是自定义 `event:` 路由。使用标准 SSE 解析器处理网络分片、CRLF、多行 data 及注释心跳，不假设一次网络读取就是一个事件。

每帧先检查 JSON-RPC `error`，再读 `result`：

- `kind=status-update`：读 `status.state`，初始可能是 `submitted` 或 `working`。
- `kind=artifact-update`：读 `artifact.artifactId` 与 `artifact.parts`。按 artifact ID 维护展示缓冲，`append=false` 替换，`append=true` 追加。文字位于 `kind=text` 的 `text`。文字块最多 1000 字符。
- 商品位于 `kind=data` 的 `data.cardsInfo[].cardData.skuList[]`，字段包括 `sku_title`、`sku_price`、`sku_image`、`sku_url.webURL`。不支持卡片渲染的宿主可按返回事实转成文字及链接，不从自由文本臆造卡片。
- artifact 上的 `lastChunk` / `final` 不是任务终态。只有 `kind=status-update` 且 `final=true` 才结束任务；终态为 `completed`、`canceled` 或 `failed`。

终态示例（整个对象位于 SSE data）：

```json
{"jsonrpc":"2.0","id":"rpc-1","result":{"taskId":"task-unique-1","kind":"status-update","final":true,"status":{"state":"completed"}}}
```

没有收到终态就断连时，结果未知。恢复原任务时从重放流重建它的 artifact，不把重放内容再次追加给用户。不存在 `tasks/get` 或游标续传接口；不得自行调用猜测的方法。

## 取消与清空

两者的 `sessionId` 位于 JSON-RPC **顶层**，不是 `params`：

```json
{"jsonrpc":"2.0","id":"cancel-1","method":"tasks/cancel","sessionId":"host-generated-opaque-conversation-id"}
```

返回 `result.status.state` 为 `canceled` 或 `unknown`。取消回执不证明任何业务副作用已回滚；仍应以实际业务回读为准。

```json
{"jsonrpc":"2.0","id":"clear-1","method":"clearContext","sessionId":"host-generated-opaque-conversation-id"}
```

成功返回 `result.status.state="cleared"`；服务端归档原 Control 会话，保留历史任务投影。活跃输入未及时收敛可能返回冲突，不能向用户声称已清空。该方法可以省略业务 ID，但外部宿主始终显式提供，避免误清共享认证 token 的最近会话。

## 错误处理与接入验收

检查 HTTP 状态和 JSON-RPC `error.code`，HTTP 200 也可能是错误：

| code | 含义 | 宿主动作 |
| --- | --- | --- |
| -32700 / -32600 / -32602 | JSON、请求或参数不合法 | 修正请求，不原样无限重试 |
| -32601 | 方法不存在 | 只用本文列出的五种方法 |
| -32001 | 鉴权失败/过期 | 核对凭据、时间及重放；受保护地重新初始化 |
| -32005 | Content-Type 不支持 | 使用 application/json |
| -32009 | 幂等冲突、已清上下文等冲突 | 保留原映射，核对任务/载荷/会话，不换 ID 自动重做 |
| -32603 | 内部错误 | 记录脱敏关联信息，结果不明时恢复原任务 |

部署接入需核对固定目标 Agent 已启用且 Runtime ready，以及 HTTPS 代理允许该路径并关闭 SSE 缓冲。运维使用原有 Control 配置体系完成；此 skill 不修改服务端配置。

拿到正式接入配置后，至少实际验收：初始化与过期鉴权；一次完整文字/商品流到终态；同会话第二轮；同任务重放无重复执行；不同用户会话隔离；断线恢复；取消；显式清空及清空后新任务。渠道凭据持有方是受信任主体，业务 ID 隔离不能替代独立渠道凭据与权限隔离。会员交易授权回流单独验收，不因搜索通过就声称交易可用。

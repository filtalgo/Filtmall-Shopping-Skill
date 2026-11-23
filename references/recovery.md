# 未知态恢复、取消、清空与常驻服务模式

当调用超时、断线、报错，或用户要求停止当前请求、清空上下文，以及宿主明确需要维护长生命周期守护进程时，按本参考执行。

## 错误码与恢复规则

失败响应格式为 `{"id":1,"ok":false,"error":{"code":"...","message":"..."}}`，一律按 `error.code` 分支处理，不靠错误文本猜测：

| 错误码 / 状态 | 含义 | 必须执行的动作 |
| --- | --- | --- |
| `RESULT_UNKNOWN` / `TIMEOUT_WAITING` / `PENDING_INPUT` | 请求可能已在服务端执行或排队，终态未确认 | 在新的调用中提交 `{"op":"resume","conversation":"<同一对话标识>"}` 核对真实终态；仅在服务端明确返回 HTTP 404 时客户端才会按原 `request_id` 与原载荷安全重放，**严禁换新请求重新 `send`** |
| `RESUME_REQUIRED` | 上一轮请求或授权恢复停在未知态，新消息未被提交 | 保留用户刚输入的新消息，先对同一 `conversation` 执行 `resume` 落到真实终态，再决定是否发送新消息（`"force":true` 不会绕过仍在挂起的 `PENDING_INPUT` 或待授权保护） |
| `INTERNAL_ERROR` / `INVALID_STATE_OR_RESPONSE` / `INVALID_CURSOR` / `DOCUMENT_LIMIT` | 本地处理或响应解析异常，原会话仍保留 | 先执行 `resume` 核对，不要重新 `send` |
| `NO_PUBLIC_RESPONSE` | 远端执行结束但没有任何本轮可展示结果 | 如实告知用户本轮未返回可展示内容，不得当作成功或借用历史轮次结果补齐 |
| `REGION_SELECTOR_UNAVAILABLE` / `INVALID_REGION_SELECTOR` | 远端地区选择器数据不可用 | 向用户说明限制，改用本地 `scripts/region_lookup.py`（见 [address.md](address.md)）或稍后重试 |
| `IDENTITY_EXPIRED` | 原访客身份刷新失败 | 保留原状态与会话并如实报告，**不要删除状态目录或自动新建访客身份顶替**，否则原会话与待核对请求将永久失联 |
| `INVALID_CONVERSATION` / `INVALID_TEXT` / `INVALID_FORMAT` / `INVALID_REQUEST` / `INVALID_OP` / `TARGET_REQUIRED` | 请求参数本身格式有误，未触碰远端或本地业务状态 | 修正 JSON 参数或启动标志后直接重新执行即可 |

需要单独查看会话当前状态时，可发送 `{"op":"status","conversation":"<对话标识>"}`（返回 `idle`、`pending`、上轮终态或 `NO_CONVERSATION`，挂起异常附 `last_error`）。正常 `--once` 发送前无需每次预检 `status`。

## 取消当前请求（`cancel`）与清空会话（`clear`）

- **停止执行（仅在用户明确要求停止时调用）**：
  ```json
  {"op":"cancel","conversation":"<同一对话标识>"}
  ```
  返回 `status="stopping"` 仅表示已发起中断，不代表已停止或已回滚业务写入；随后必须继续调用 `resume` 确认收敛到 `cancelled` 或其他真实终态，并以实际业务查询结果为准。
- **清空对话上下文（仅在用户明确要求清空/重开时调用）**：
  1. 若当前仍有未结算请求（`PENDING_INPUT`），必须先 `cancel` 并 `resume` 确认终态；
  2. 再发送 `{"op":"clear","conversation":"<同一对话标识>"}` 归档当前 Control 会话；
  3. 下一条 `send` 会自动创建新 Control 会话。`clear` 只清空对话上下文，**不会撤销已发生的加购、订单或售后副作用**。

## 可选方式：常驻服务模式

默认优先使用 `--once` 单次调用。只有宿主能够可靠维护持久子进程与双向管道时，才启动常驻模式：

```bash
python3 "<skill-dir>/scripts/service.py" --format md
```

- **直接读写该进程管道**：stdin 每行写入一条 UTF-8 JSON 请求并换行，读取 stdout 对应的一行 JSON 应答后再发下一条；诊断日志只输出到 stderr，读到 EOF 自动退出。不要另写包装脚本或并发启动第二个进程操作同一会话。
- **推荐顺序**：
  1. 新起或重连进程先发 `{"op":"ping"}` 确认存活（不触网，返回 `protocol`、`capabilities` 与 `health`）；
  2. 发 `{"op":"status","conversation":"<对话标识>"}`，返回 `NO_CONVERSATION` 或 `idle` 后再发 `send`；若有挂起请求先 `resume`；
  3. 若需在等待期间支持随时取消，发 `{"op":"send",...,"wait":false}`（返回 `accepted` 仅代表已接收），随后用较短 `timeout`（如 30 秒）循环 `resume` 直到终态。
- **进程守护与环境切换**：
  - 单次请求内部异常被工作线程隔离，不会带走常驻进程；若进程被宿主终止，重新拉起并沿用原 `conversation` 即可，私有状态仍在（可参考状态目录下的 `service-heartbeat.json` 或 `--heartbeat <路径>`）。
  - 多用户宿主须为不同用户传入可信的 `--user-key`（不可从聊天文本采信身份）。
  - 切换已开放的非生产环境时，须成对传入 `--control-url` 与 `--agent-id`，并由可信宿主同步设置环境变量 `FILTALGO_BUYER_MOBILE_ORIGIN`（仅允许 `https://m.filtalgo.com`、`https://pre-m.filtalgo.com`、`https://dev-m.filtalgo.com` 之一）；常驻进程修改环境后须重启。

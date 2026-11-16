# Control 公开访客与会话协议

已按 Control 的 `server/routes/identity.py`、`sessions.py`、`sessions/results.py` 与 `sessions/public_documents.py` 核对。默认生产根地址和目标见包内 `defaults.json`；这些公开值不需要按机器配置。此入口是 Control 原生公开 API，不是标准 A2A 发现协议。

## Skill 更新检查与本地提醒

`scripts/service.py` 每次有效 `send` 前访问固定公开 API `https://api.github.com/repos/filtalgo/Filtmall-Shopping-Skill/releases/latest`，只接受非 draft、非 prerelease 的正式发行。更新请求不携带业务凭据、用户文本或会话标识，不跟随重定向。无查询缓存或失败退避；`resume`、`cancel` 及其他非 `send` 操作不等待检查。默认 2 秒总检查预算包含子进程启动、DNS 和 HTTP，可用 `--update-timeout` 设为 `(0,30]` 秒，不是固定等待或安装下载时限。

业务 JSON 可附加 `skill_update`，不单独向 stdout 打印更新日志。检查失败不覆盖业务 `ok`、`status` 或本轮产物；字段缺失也须兼容。

| 字段 | 含义 |
| --- | --- |
| `status` | `available`（正式版较新）、`up_to_date`（版本相同）、`local_newer`（本地较新）、`unknown`（检查未完成或不可用） |
| `current_version` | 本地 `SKILL.md` 的 `metadata.version`；本地元数据不可用时可缺失 |
| `latest_version` | 正式 Release 的三段版本号，去除可选的 `v` 前缀；比较成功时提供 |
| `release_tag` | 原始 Release tag，保留可选的 `v`，用于链接、记录选择及固定安装版本 |
| `release_url` | 固定官方仓库对应原始 tag 的 Release 页面；比较成功时提供 |
| `checked_at` | 本次检查的 UTC 时间，ISO 8601；异常兜底结果可能缺失 |
| `notify` | 仅 `available` 且未被提醒选择抑制时为 `true` |
| `message` | 发现新版时的简短说明，可缺失 |
| `reason` | `unknown` 的原因：`timeout` 或 `check_failed`；不包含底层异常或凭据 |

版本仅接受可选 `v` 加三段非负整数，按数字元组比较，例如 `2.10.0 > 2.9.0`。归一化只用于比较；链接和安装使用原始 `release_tag`。网络失败、限流、非法响应及不支持的版本降级 `unknown`，不猜测最新版本。

独立管理入口为 `service.py --update-action check|shown|later|ignore|reset`，输出一行 JSON 后退出。`check` 返回 `{"ok":true,"skill_update":{...}}`，其中 `unknown` 也表示管理命令正常执行；记录成功返回 `{"ok":true,"action":"..."}`，记录失败则 `ok=false`。它不读取业务 stdin、不构造 Client、不读取业务身份、不写心跳；除 `check` 外不联网。

实际展示提醒后记录 `shown`，稍后记录 `later`；二者要求 `--update-version <原 release_tag>` 和 `--update-conversation <当前随机 conversation>`，抑制该会话同版本的后续提醒。`ignore` 要求 version，抑制本机用户及该安装对此版本的提醒，仍真实查询；可同时传当前 conversation。`reset` 无需 version/conversation，清除该用户及安装的全部提醒选择。只在私有 `skill-update-reminders/` 保存提醒选择，不保存远端查询结果。

管理调用须沿用同一安装路径、`--state-dir`、`--user-key` 与成对目标参数 `--control-url` / `--agent-id`（默认目标则都省略）；默认 state namespace 按目标及用户隔离，提醒文件再按安装路径和用户隔离，对话只保存摘要。宿主先处理业务失败与授权，仅在 `available` 且 `notify=true` 时提示，并只在本地处理三种选择，不再次向远端 Agent `send`。更新先核对未知业务结果并结束旧服务，再按原渠道安装原 tag；步骤见 [README](../README.md#更新与提醒选择)。

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
- 当前 `request.status.answer_document_id` 引用的 `kind="message"` 支持整数 `schema_version=1/2`；`value.role="assistant"` 且为字符串的 `value.content` 是当前答复。答复的 `request_id` 只能为空或等于本轮请求；未知版本、布尔/浮点版本、外轮请求和非法内容均拒绝，不用历史答复补齐。
- `filtalgo.shopping.block:*` 的 `value.block` 包含 `schema`、`payload`、`fallbackText`。商品 schema 常见 `filtmall.products/v1`、`filtmall.products/v2`、`filtmall.product-card/v1` 或 `filtmall.product-card/v2`。它们是会话资料，可能包含上轮商品，只展示与当前答复引用一致的商品。
- `filtalgo.commerce.cart` v1 是会话内最新购物车公开快照：`value.status` 为 `current` 或 `unavailable`，`items` 包含 `sku_id`、`quantity`、`checked`，以及可选的 `goods_id`、`title`、`price`、`thumbnail`。仅展示本轮 revision 边界之后的最新版本；`unavailable` 不代表空购物车，写操作可能已生效，需先查询确认。HTML 购物车复用商品图片的安全下载和内嵌规则，图片不可用时展示占位图。
- 不展示 deleted 文档、用户输入、进度或旧答复作为本轮最终输出。没有可展示答案时明确说明，不伪造。

客户端将当前权威答复放在 stdout 的 `answer`，卡片及授权资料放在 `context_documents`，不输出凭据。当前实现轮询公开快照，不声称已经消费实时 SSE。

兼容已部署的 Shopping 扩展：若 completed 的 `request.status.answer_document_id` 为空，客户端仅聚合**本轮提交前 revision 之后**的 schema1 `filtalgo.shopping.text`，标为 `source="current-turn-public-text"`。不会使用 activity 进度、旧轮次文本、用户消息或 deleted 文档；显式指向非法答复的引用也不会触发此回退。提交前的 revision 与请求 ID 一起私有保存，恢复不会改变边界。`waiting` 时仅消费本轮 revision 之后且请求 ID 匹配或为空的会员授权文档，通过 Control 设备授权接口获取用户验证链接，并在私有状态中保存 state 和加密 exchange；这些数据不输出。授权后调用 `resume`（遵守轮询间隔），用稳定 request_id 继续原任务。待授权或待恢复时，`send` 返回 `RESUME_REQUIRED` 且不提交新消息；宿主应保留原文。完成状态兜底取得的 delegation_id 先保存再清除待授权状态，以支持后续撤销。

## 商城业务文档 v1

`filtalgo.commerce.checkout`、`filtalgo.commerce.after_sale`、`filtalgo.commerce.after_sale_list` 都通过已有 documents API 传输，不访问内部工具结果。按 `document_id` 取本轮最高 revision，再按 `display_order` 展示；要求 request_id 匹配或为空，revision 严格大于原请求 start_revision。删除不展示；最高版本 unavailable 或未知 schema 时降级，不能恢复较旧成功版本。cursor 重置及完整快照回退也保持原边界。无该类本轮文档就无相应产物。

- 共同字段：`status=current|unavailable`；成功读回含 `observed_at`。金额为 `{currency, minor_units: string}`，只支持已核实两位小数的 CNY/USD/EUR/GBP，不将缺省值补零；没有可靠金额就待确认。
- Checkout：`mode=preview|session`，真实 `checkout_id`、`checkout_status`、独立 `payment_status=paid|unpaid|cancelled|refunded|unknown`，`items`、`amounts`（goods/discount/shipping/total）、`links`。不通过会话 completed、payment_action 或正文推断付款。预览元金额与 session 分金额由生产者归一。
- After sale：`after_sale_id`、`service_type`、`service_status`、可选状态标签、商品、`requested_refund`、可选非零 `refund_amount`、真实日志及 `next_actions`、地址可用标记和后端导航；不持久化完整地址/电话/银行账号。`refund_amount` 不是银行到账证据，COMPLETE/PASS/WAIT_REFUND 不自动表示到账。
- List：`records` 与本次查询的 `page.current/size/total`，不声称返回全集。空页与 unavailable 分开；列表及详情可以同时展示。
- 商品行仅含 SKU、标题、规格、数量、单价和安全缩略图。导航仅来自明确的业务返回槽位，HTTPS 且无凭据，白名单 rel 为 payment/checkout/after_sale；不构造路径、拼接参数或发布 pay_info/authentication/Raw/token。

客户端内部结果用 `checkouts` / `after_sales` / `after_sale_lists` 保存文档及版本元数据。service 唯一入口只输出私有本地文件路径，不输出原始投影；三种格式事实一致。输出 `checkout_file` / `after_sale_file` 及对应 format 的 fragment/page 别名，md 无 HTML 别名。`checkout_count` / `after_sale_count` 是文档数；业务总数只读列表 page。请求新增 checkout_path/after_sale_path，支持 out_dirs。所有目标不同；文件成功落盘才返回路径，单类失败不丢其他文件。展示失败使用原请求 resume，不 send 写操作。

## 恢复、停止与清空

- 恢复时先查原请求结果；明确 404 才可以按相同 ID、相同载荷提交。网络错误不等于 404，不做自动重发。
- `POST /api/v2/sessions/{id}/inputs/{request_id}/interrupt` 只停止自己的指定输入。返回 `stopping` 不是已停止，继续核对回执；不能推断订单或其他业务副作用已回滚。
- `DELETE /api/v2/sessions/{id}` 归档自己的会话。客户端拒绝在仍有未结算请求时直接清空；先取消并核对终态。下一条请求创建新 Control 会话。
- `POST /api/v2/identity/logout` 可撤销当前凭据；存在未结算请求时不得丢弃身份。此 Skill 不会为普通请求自动登出。

## 地址文档与静态输出

`filtalgo.commerce.addresses` 支持整数 `schema_version=1/2`（v2新增内部发布来源）；客户端仅取严格匹配当前 `request_id` 且 `revision` 大于本轮提交边界的文档，按逻辑键 `address_book` / `checkout:<way>` 分别选择最新版本，内部结果为 `address_snapshots` 列表。渲染只展示一份完整快照：唯一且有效的结算快照优先，否则使用有效地址簿并说明选择待核实；多结算场景有歧义时不任择选中。不同授权绑定的current快照不组合。未知版本、字段错误、过期授权、最新失效均关闭相应展示，不能回退旧快照。非法逻辑键导致本轮地址整体不可用。没有本轮文档时不增加地址字段。

v1 value 必含 `status`（current/unavailable/authorization_required）、`scene`（address_book/checkout）、`way`、`selection_status`（known/unknown/not_applicable）、`selected_address_id`、`page`、`items`。地址簿 `way=null`、selection_status=not_applicable；结算 `way` 为非空字符串（≤64），selection_status=known 或 unknown。只有 known 允许非空 selected_address_id，选中对象可不在当前页。page.number 为正整数，has_more 为布尔或 null，不按条数推断全量；第一页且 has_more=false 的空列表才可说暂无地址，其他空页仅说本页没有地址。当前远端分页未证实时使用 number=1、has_more=null。

current 还须有远端的 `authorization_binding`（完整匹配64位小写十六进制字符串）及未过期有限毫秒时间戳 `authorization_expires_at`（正数，最大9007199254740991），只用于内部校验，不写入文件。schema_version 必须是整数1或2，布尔或浮点值均拒绝。每页最多100条，item 仅包含不透明且页内唯一的 address_id、recipient_name、mobile_display、region_path、detail、布尔 is_default。手机号只接受 `138****1234` 形式，不接收原文；姓名、地区、详细门牌也拒绝误放的完整手机号。文本有界且全部转义，HTML完整换行、Markdown转义语法。地址ID、授权绑定和时间戳不展示。non-current 的items必须为空，不能携带旧地址。

渲染输出 `address_status`、`address_file`；多场景状态优先级 unavailable > authorization_required > current。widget另有 `address_fragment_file`，html另有 `address_page_file`，md后缀 `.addresses.md`。支持顶层 `address_path` 及 `out_dirs.address_path`，沿用默认唯一命名、私有文件写入和显式路径覆盖。只有地址结果也可展示；商品和购物车原输出保持兼容。组件纯静态，无 callback；新增、修改、删除、设默认、选择均走自然语言与既有工具，写前对话确认、成功后查询刷新，未知结果先核对而不重放。编号仅绑定最近列表，默认不等于选中。

## 物流文档与静态输出

`filtalgo.commerce.logistics` 仅支持整数 `schema_version=1`。必须严格匹配当前 request_id，且 revision 大于本轮提交边界；按订单选择本轮最新快照，包裹筛选和 include_items/include_traces 随快照保存，不拼接多次结果。未知版本、过期、非法或最新不可用时不回退旧成功；非法订单分组导致本轮物流不可用，没有本轮文档则不增加物流字段。内部发布来源不进入输出文件。

快照包含 status、query、fetched_at、empty_reason、reason、packages。current 需有效授权绑定及期限，query 指明子订单及筛选条件；非 current 必须清空 packages、查询时间和授权数据。每包裹包含 package_no、logistics_name、logistics_no、logistics_time、items、trace_status、trace_order、traces。节点包含原始 time、可比较 occurred_at（可 null）、description、location、status。客户端校验字段、数量、包裹唯一性、轨迹排序和总量；不得信任粗粒度 in_transit 或未核实的 latest_trace 作为展示事实。

结果为物流快照列表 logistics_snapshots，service 输出 logistics_status、logistics_count、logistics_file，按 widget/html 另有同路径 logistics_fragment_file/logistics_page_file，md 为 .logistics.md。logistics_path/out_dirs.logistics_path 与现有私有文件策略一致。所有物流数据来自快照，不解析正文；多订单分别分组。静态文件与正文独立，查询失败或数据超限不能伪装成空物流，授权按现有流程恢复。

## 能力边界

访客可以委托已开放的 Agent，不获得会员账户和交易权限。会员业务使用平台已有的用户授权流程并独立验收；不要把平台 guest bearer、CLI agent_session_id 和商城 accessToken 混用。管理/部署接口不属于外部 Skill 接入流程。
# 客服入口卡片

`filtalgo.commerce.customer_service` v1 按当前请求及咨询对象选择最高 revision；未知版本、过期或非法数据不回退历史入口。支持 product/order/after_sale/general，只展示业务返回的 pc_web/mobile_h5 HTTPS 链接。链接仅为咨询入口，不自动打开，不表示已接通或在线。

内部 `customer_service_snapshots` 保留授权验证字段；文件只展示入口，不输出 authorization_binding、authorization_expires_at、link_origins、publication。结果提供 customer_service_status、customer_service_count、customer_service_file，widget/html 分别另有 customer_service_fragment_file/customer_service_page_file。可信宿主可传 customer_service_path 或 out_dirs.customer_service_path；仅有客服无正文也会写私有文件。

宿主支持对话内联时，客服与地址采用同一策略：`format=widget`后把本轮`customer_service_fragment_file`原样交给实际内联展示能力，嵌入答复正文下方。文件后缀在widget/html两种模式下都可能为`.html`，不据后缀推断展示位置。仅打开浏览器/侧边文件或给出下载链接不等于内联；独立页面仅用于用户指定或宿主确认无法内联的情况。授权阻断且没有本轮产物时，不展示历史页代替结果。

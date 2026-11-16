# Filtmall Shopping Skill

[English](README_en.md) · [筛电官网](https://www.filtalgo.com/) · [Skill 使用说明](SKILL.md) · [公开接口协议](references/protocol.md)

**用自然语言完成从选品到购物的对话。**

Filtmall Shopping 是筛电的托管购物 Agent Skill。用户可以提出需求，查询商品、比较价格和规格，并在授权和确认后继续购物。商品信息、价格和库存以实际服务响应为准。

当前包默认使用 **生产环境**。会员操作需要单独授权，订单提交和付款由用户确认。

本目录 Skill 版本为 **2.2.0**，包含生产地区目录、授权恢复、地址隐私保护和正式版本更新检查。

## 安装

将本目录完整复制到宿主的 Skill 目录，安装名称为 `filtmall-shopping`。需要 Python 3.10 或更高版本，无需安装额外依赖、配置渠道 AK/SK 或 SSH。客户端会申请并私有保存访客身份。

如需连接其他已开放环境，须同时指定 `--control-url` 和 `--agent-id`。

## 更新与提醒选择

每次有效 `send` 前会访问 [官方正式 Release](https://github.com/filtalgo/Filtmall-Shopping-Skill/releases/latest)，不缓存结果，也不因失败暂停后续检查。默认检查预算为 2 秒；`--update-timeout <秒数>` 可设为 `(0,30]`，包含子进程启动、DNS 和 HTTP，不是固定等待或下载时限。检查失败返回 `unknown`，不影响购物结果和本轮文件；`resume`、`cancel` 等非 `send` 操作无需等待更新检查。

宿主先处理业务失败、恢复及授权，只在可选 `skill_update.status=available` 且 `notify=true` 时提示。展示后记录 `shown`；稍后只抑制当前会话对此版本的重复提醒，忽略对此本机用户及安装抑制该版本提醒。忽略仍会真实查询，有更新版本仍可提醒。提醒偏好按本机用户、安装与会话隔离，管理操作只写提醒状态，不保存远端查询结果，也不提交购物请求。

管理命令使用 `scripts/service.py`，输出一行 JSON 后退出，不读取 stdin、不创建业务身份或心跳。以下使用默认目标；将 `<skill-dir>`、`<原 state-dir>`、`<原 user-key>` 替换为同一安装及业务调用的实际值，`<release_tag>` 使用响应中的原始 tag。业务未指定 `--state-dir` 或 `--user-key` 时，管理命令也沿用默认值；切换过目标时，每条命令还须带原 `--control-url` 和 `--agent-id`。示例 conversation 仅示意，实际使用宿主为当前对话生成并沿用的不可预测随机标识，不从用户自然语言拼接 Shell 命令。

```bash
python3 "<skill-dir>/scripts/service.py" --state-dir "<原 state-dir>" --user-key "<原 user-key>" --update-action check --update-conversation b71033727dfa4f6da529c87434cb06a4
python3 "<skill-dir>/scripts/service.py" --state-dir "<原 state-dir>" --user-key "<原 user-key>" --update-action shown --update-version "<release_tag>" --update-conversation b71033727dfa4f6da529c87434cb06a4
```

只有实际展示提示后才执行 `shown`。用户选择“稍后”或“忽略此版本”时，将第二条命令的 `shown` 分别换为 `later` 或 `ignore`；解除全部提醒选择时用 `--update-action reset`，省略 version 和 conversation。检查与管理失败时按 JSON 如实说明，不能假称已保存。完整返回字段见 [协议](references/protocol.md#skill-更新检查与本地提醒)。

这三种选择只由宿主本地处理，不转发远端购物 Agent。“现在更新”沿用原安装渠道：

1. 若购物结果未知，先 `resume` 核对；确认请求终态、没有待恢复请求，并退出旧服务进程。
2. 备份旧包和本地定制，保留私有 state。打开响应中的 `release_url`，固定本次原始 `release_tag`，按原渠道取得对应包；手动复制安装就用该 tag 的包替换 Skill 目录，不使用默认 `main` 或未经核实的通用更新命令。
3. 核对新包安装名仍为 `filtmall-shopping`，`metadata.version` 与选定 Release 一致；重新阅读 `SKILL.md` 后启动服务。不能可靠安装时，提供该 Release 的人工下载与替换步骤，不宣称已更新。

本功能不新增安装器，不自动覆盖安装；当前源码交付不表示已发布新的 Release。

## 试一试

- “推荐 100 元以内的保湿面膜。”
- “比较第一款和第三款的规格与价格。”
- “帮我查看购物车里的商品。”
- “查询这个订单的物流状态。”

会员业务需要用户完成授权，写操作须经用户确认。

## 能做什么

| 阶段 | 用户可以做什么 |
| --- | --- |
| 发现 | 用自然语言描述品类、预算和需求，查找商品 |
| 比较 | 查看服务返回的价格、规格、库存、商品信息及可用的比价证据 |
| 详情 | 查看商品资料和规格，并查询成分信息 |
| 购买 | 授权后管理购物车，预览并确认订单 |
| 跟进 | 查询订单和物流，处理适用的取消与售后请求 |

具体能力取决于目标 Agent 的配置、业务服务及用户授权。服务没有返回的数据不会由 Skill 补造。

## 工作方式

```mermaid
flowchart LR
    U["用户需求"] --> A["宿主 Agent"]
    A --> S["Filtmall Shopping Skill"]
    S --> C["Control 会话 API"]
    C --> R["托管购物 Agent"]
    R --> C
    C --> S
    S --> A
```

Skill 通过 Control 的公开访客和会话接口提交请求，并保留会话及请求状态以便续聊和恢复。托管 Agent 在服务端编排业务工具；访客身份不等于会员授权。公开接口不是标准 A2A Agent Card 发现协议。

## 开发者快速开始

推荐使用单次调用模式，从标准输入传入一行 JSON：

```bash
python3 "<skill-dir>/scripts/service.py" --once --format widget
```

```json
{"conversation":"<宿主生成的对话标识>","text":"推荐100元以内的面膜，只查询。"}
```

宿主应为每个用户和对话生成独立标识，续聊时沿用。`format` 可选 `widget`（HTML 片段）、`html`（完整页面）或 `md`（Markdown），商品卡片和购物车使用同一格式。结果通过 JSON 返回状态和产物路径：正文为 `answer_file`；商品按格式返回 `fragment_file`、`page_file` 或 `html_file`；购物车为 `cart_file`，HTML 模式另提供 `cart_fragment_file` 或 `cart_page_file`。`cart_status` 为 `current` 或 `unavailable`；后者表示状态不可用，应先查询确认，不要重复写操作。宿主需能访问这些文件，并以 UTF-8 读取。没有对应内容时，相应字段不会出现。

### 选择展示格式

| 场景 | 请求参数 | 商品产物 | 购物车产物 |
| --- | --- | --- | --- |
| 在聊天窗口或宿主界面内联展示 | `"format":"widget"`（默认） | `fragment_file`：HTML 片段 | `cart_fragment_file`：HTML 片段 |
| 在浏览器或 WebView 打开独立页面 | `"format":"html"` | `page_file`：完整 HTML 页面 | `cart_page_file`：完整 HTML 页面 |
| 宿主支持 Markdown 或只需文本展示 | `"format":"md"` | `html_file`：`.cards.md` 文件 | `cart_file`：`.cart.md` 文件 |

这三种格式同时适用于商品、购物车、结算和售后；正文仍从 `answer_file` 读取。结算输出 `checkout_file`，售后输出 `after_sale_file`；widget 另提供 `checkout_fragment_file` / `after_sale_fragment_file`，html 另提供 `checkout_page_file` / `after_sale_page_file`，md 直接读取相应 `.md`。结算/售后不要求有正文；只有本轮文档才生成文件，多实体合入对应业务文件。page 使用与内联相同的卡片，不附额外页面标题或状态栏。

`checkout_path` / `after_sale_path`（也可放在 `out_dirs`）支持宿主自定义完整路径，所有产物路径必须不同。默认文件按轮次唯一；自定义目标原子覆盖。`presentation_status=failed` 时保留成功产物及真实执行状态；用原对话 `resume` 重渲染，不重复写操作。支付、退款实际状态只使用明确业务证据，不从正文或金额推断。完整字段与边界见 [协议](references/protocol.md)。

内联模式要求宿主支持 HTML 和 `data:` 图片；无法内联时选 `html` 或 `md`。购物车展示选中/全车款数和件数、规范单价及缺价提示，HTML 第 3 行后折叠但不丢行，md 完整输出；图片共享本轮预算并复用重复 URL。

启动时可用 `--format widget`、`--format html` 或 `--format md` 设置默认值；单次请求中的 `"format"` 会覆盖启动默认值。例如：

```json
{"op":"send","conversation":"<对话标识>","text":"查看购物车","format":"md"}
```

在 **Qoder** 中内联展示商品卡片时，使用 `widget`，并直接通过 `out_dirs.fragment_path` 将片段输出到 Qoder 的 `visualizations/` 目录下。将示例中的占位符替换为该目录的实际绝对路径，再用返回的 `fragment_file` 内联展示；异步调用时，在取得最终结果的 `resume` 请求中也要传入该路径。

```json
{"op":"send","conversation":"<对话标识>","text":"推荐100元以内的面膜，只查询。","format":"widget",
 "out_dirs":{"fragment_path":"<Qoder 的 visualizations 目录绝对路径>/products.html"}}
```

指定路径的同名文件允许覆盖；需要保留不同轮次结果时，请使用不同文件名。

网络中断或结果未知时，使用同一会话的 `resume` 核对原请求，不要自动重新提交。停止使用 `cancel`，清空会话使用 `clear`。完整请求、授权、地址和展示规则见 [SKILL.md](SKILL.md)。

商城授权完成后使用同一会话的 `resume` 恢复原任务；原任务尚未恢复时，`send` 返回 `RESUME_REQUIRED`，新消息未提交。宿主应保留新消息，确认原任务终态后再发送。用户明确要求撤销授权时使用 `revoke-authorization`。地址隐私校验依赖随包提供的离线号码库，复制时须保留 `third_party/`。

## 用户控制与数据边界

- 修改购物车、地址、订单或发起售后前，取得用户明确同意。
- 授权和付款由用户在对应页面完成；不要把访客身份当作会员授权，也不要编造支付链接或成功状态。
- 凭据和未结算请求保存在宿主私有状态目录，不写入模型消息或日志。
- 地址地区数据随包提供独立的 prod/pre 快照，工具按请求 environment 选择；未指定时使用 defaults.json 的环境，正式包默认 prod。不能跨环境使用 ID，--data-file 可指定同环境可信目录。
- 完成状态不代表付款成功；订单及支付结果以业务服务的实际结果为准。

## 目录结构

```text
SKILL.md                 # 宿主调用和交互规则
references/protocol.md   # Control 公开会话协议
scripts/service.py       # 单次调用和常驻服务入口
scripts/update_check.py  # 正式 Release 检查与本地提醒选择
scripts/client.py        # 身份、会话与请求恢复
scripts/cards.py         # 商品卡片渲染
scripts/commerce_ui.py   # 商品、购物车、地址、物流与客服共用主题及页面外壳
scripts/address_cards.py # 地址验证、单列表与状态标签展示
scripts/logistics_cards.py # 物流验证、包裹摘要及完整时间轴展示
scripts/customer_service_cards.py # 客服入口验证、场景卡片与渠道链接展示
scripts/region_lookup.py # 地区名称转三级ID与地址拆分，按环境选目录
scripts/commerce_render.py # 购物车、结算和售后的三格式渲染
data/regions-pre.json    # pre 地区数据快照
data/regions-prod.json   # 生产地区库只读导出的快照
agents/openai.yaml       # 宿主展示元数据
```

本 Skill 采用 [Apache-2.0 许可证](LICENSE)。直接调用底层购物工具的独立 CLI Skill 为 `filtmall-shopping-cli`，与本 Skill 的身份和会话相互独立。
## 收货地址静态展示

服务支持本轮 `filtalgo.commerce.addresses` v1/v2 快照，使用标准库模块 `scripts/address_cards.py`，与商品、购物车共用 `format=widget/html/md`。输出 `address_status` 和 `address_file`，widget 另有同路径 `address_fragment_file`，html 另有 `address_page_file`，md 文件后缀为 `.addresses.md`。请求可传 `address_path` 或 `out_dirs.address_path`，路径须在可信宿主当前用户私有空间。默认每轮文件名唯一，显式路径可覆盖。

地址只显示一个完整可信列表，商品、购物车和地址共用主题、卡片尺度与深浅色支持。唯一有效的结算快照优先；结算失效时显示当前地址簿并提示本次选择待核实，多结算场景有歧义时先明确场景，不拼接跨场景选中字段。详细地址完整换行，默认和本次选中独立标记。没有按钮、脚本或 callback，地址操作通过自然语言继续对话，写前确认对象与完整参数，成功后刷新。编号仅对应最近实际展示的列表；刷新或歧义后重新确认。没有本轮快照不生成文件，只有地址无正文可正常展示。缺授权走既有流程，查询不可用不能当空地址簿。

文件使用现有私有写入策略，不在示例或日志输出真实地址。远端撤权无法回收已生成的本地文件。此功能的离线虚构快照测试不代表线上业务验收。

## 订单物流静态展示

支持 `filtalgo.commerce.logistics` 整数 schema v1，沿用同一 `service.py`、公开文档读取、共享主题和私有文件输出管线。每包裹一卡，展示商品、发货数量、快递公司、运单号、发货时间、摘要及全部返回的轨迹。可靠时间倒序，不明确时保留返回顺序并提示；暂无包裹、未找到指定包裹、暂无轨迹、未查询轨迹、失败和需授权分开显示。

日期显示为 `YYYY-MM-DD HH:mm`：有效显式时区转换为北京时间，无偏移的本地时间保留原钟面，未知格式原样安全展示，不改变原始时间或排序。节点字段标签为“状态”；正常卡片不额外显示“已有物流轨迹”，查询时间省略“非轨迹发生时间”的括号提示。

结果字段为 `logistics_status`、`logistics_count`、`logistics_file`；widget/html 分别另有同路径的 `logistics_fragment_file` / `logistics_page_file`，md 使用 `.logistics.md`。可信宿主可通过 `logistics_path` 或 `out_dirs.logistics_path` 指定私有文件路径。没有本轮快照不生成文件，只有物流无正文也可展示。最新未知版本、失效或失败不回退旧成功。

订单号由 Agent 查找或在对话中确认，不新增订单列表组件。刷新及指定包裹通过自然语言调用既有工具，页面无按钮、脚本、地图或自动刷新。运单号为会员私有信息，不能公开分享生成文件。测试 fixture 不代表真实承运商或预发订单验收通过。
# 客服入口卡片

`filtalgo.commerce.customer_service` v1 按当前请求及咨询对象选择最高 revision；未知版本、过期或非法数据不回退历史入口。支持 product/order/after_sale/general，只展示业务返回的 pc_web/mobile_h5 HTTPS 链接。链接仅为咨询入口，不自动打开，不表示已接通或在线。

内部 `customer_service_snapshots` 保留授权验证字段；文件只展示入口，不输出 authorization_binding、authorization_expires_at、link_origins、publication。结果提供 customer_service_status、customer_service_count、customer_service_file，widget/html 分别另有 customer_service_fragment_file/customer_service_page_file。可信宿主可传 customer_service_path 或 out_dirs.customer_service_path；仅有客服无正文也会写私有文件。

支持对话内联的宿主应使用 `widget`，将本轮 `customer_service_fragment_file` 原样嵌入回复下方；打开侧边预览或仅贴链接不等于内联。两种模式均可能使用 `.html` 后缀，应依据 fragment/page 字段识别。卡片隐藏店铺、SPU、SKU 内部编号，保留必要的结构化身份和链接参数；点击入口后进入商城已有客服页，不在卡片内聊天。授权阻断且本轮没有产物时不能复用历史卡片。

# Filtmall Shopping Skill

[English](README_en.md) · [筛电官网](https://www.filtalgo.com/) · [Skill 使用说明](SKILL.md) · [公开接口协议](references/protocol.md)

**用自然语言完成从选品到购物的对话。**

Filtmall Shopping 是筛电的托管购物 Agent Skill。用户可以提出需求，查询商品、比较价格和规格，并在授权和确认后继续购物。商品信息、价格和库存以实际服务响应为准。

当前包默认使用 **生产环境**。会员操作需要单独授权，订单提交和付款由用户确认。

当前版本为 **2.1.1**，对应 [GitHub Release v2.1.1](https://github.com/filtalgo/Filtmall-Shopping-Skill/releases/tag/v2.1.1)。`SKILL.md` 的 `metadata.version` 为 `2.1.1`，Release/tag 使用 `v2.1.1`，三者保持一致。

## 安装

将本目录完整复制到宿主的 Skill 目录，安装名称为 `filtmall-shopping`。需要 Python 3.10 或更高版本，无需安装额外依赖、配置渠道 AK/SK 或 SSH。客户端会申请并私有保存访客身份。

如需连接其他已开放环境，须同时指定 `--control-url` 和 `--agent-id`。

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

## 用户控制与数据边界

- 修改购物车、地址、订单或发起售后前，取得用户明确同意。
- 授权和付款由用户在对应页面完成；不要把访客身份当作会员授权，也不要编造支付链接或成功状态。
- 凭据和未结算请求保存在宿主私有状态目录，不写入模型消息或日志。
- 地址地区数据是随包提供的 pre 快照，仅可在明确使用 pre 时查询；不得用于生产地址或推断生产地区 ID。
- 完成状态不代表付款成功；订单及支付结果以业务服务的实际结果为准。

## 目录结构

```text
SKILL.md                 # 宿主调用和交互规则
references/protocol.md   # Control 公开会话协议
scripts/service.py       # 单次调用和常驻服务入口
scripts/client.py        # 身份、会话与请求恢复
scripts/cards.py         # 商品卡片渲染
scripts/commerce_render.py # 购物车、结算和售后的三格式渲染
scripts/region_lookup.py # pre 地区查询
data/regions-pre.json    # pre 地区数据快照
agents/openai.yaml       # 宿主展示元数据
```

本 Skill 采用 [Apache-2.0 许可证](LICENSE)。直接调用底层购物工具的独立 CLI Skill 为 `filtmall-shopping-cli`，与本 Skill 的身份和会话相互独立。

# Filtmall Shopping Skill

[筛电官网](https://www.filtalgo.com/) · [Skill 主入口](SKILL.md) · [展示与卡片增强](references/presentation.md) · [公开接口协议](references/protocol.md)

**用自然语言完成从选品到购物的对话，首轮直接在聊天正文中呈现可读商品信息与真实入口。**

Filtmall Shopping 是筛电通用托管购物 Agent Skill。默认连接**生产环境**，通过 Python 3.10+ 标准库自动申请和刷新访客身份；会员业务需单独完成用户授权，所有写操作须经用户明确确认。

本目录 Skill 版本为 **2.4.3**。搜索正文逐款展示标题、价格、商品图与详情文字链接，图片使用简单 Markdown 语法。生产 H5 业务文字链接经公开 Gateway 转为电脑 H5／手机小程序双入口，失败保留原链接。宿主展示要求统一维护在 [presentation.md](references/presentation.md)；WorkBuddy 和豆包工作还须主动展示 HTML 商品卡片。

## 安装

将本目录完整复制到宿主的 Skill 目录，保留安装名称 `filtmall-shopping`（须一并保留 `data/`、`third_party/` 与 `LICENSE`）。无需 `pip install`、SSH 或渠道 AK/SK。

如需切换其他已开放环境，须同时指定 `--control-url` 与 `--agent-id`，并由可信宿主同步设置 `FILTALGO_BUYER_MOBILE_ORIGIN`。

## 开发者快速开始

推荐使用单次调用与 Markdown 正文模式，从标准输入传入一行 UTF-8 JSON：

```bash
python3 "<skill-dir>/scripts/service.py" --once --format md
```

```json
{"conversation":"<宿主为当前用户与对话生成的独立标识>","text":"推荐100元以内的保湿面膜，只查询。"}
```

- **统一正文入口 `display_file`**：默认 `--format md`，服务在 JSON 应答中返回 `display_file`（UTF-8 Markdown），合并本轮公开解释、单列分段商品信息（名称、价格、规格、推荐理由、真实商城 H5 链接）与已校验业务快照；宿主只需读取 `display_file` 在聊天正文直接呈现，不依赖下载附件或打开侧栏。`answer_file`、`html_file`、`cart_file` 等历史字段继续兼容返回。
- **按宿主展示 HTML 卡片**：WorkBuddy 和豆包工作必须生成并通过真实宿主能力展示卡片；其他宿主按需增强。按 [references/presentation.md](references/presentation.md) 传入 `"format":"widget"` 或 `"format":"html"`（含 Qoder `out_dirs.fragment_path` 用法）。切换格式对同一 `conversation` 调用 `resume`，不重新 `send` 原业务请求；文件生成和实际展示分别核验。
- **异常恢复与授权**：超时或状态不明时按 [references/recovery.md](references/recovery.md) 调用 `resume`；出现 `authorization_url` 时按 [references/authorization.md](references/authorization.md) 引导用户完成授权后通过 `resume` 恢复原任务。
- **地区解析与更新提醒**：离线省市区拆分与静态地址列表见 [references/address.md](references/address.md)；GitHub 正式 Release 检查与本地提醒管理（`check`/`shown`/`later`/`ignore`/`reset`）见 [references/maintenance.md](references/maintenance.md)。

## 能做什么

| 阶段 | 用户可以做什么 |
| --- | --- |
| 发现与对比 | 用自然语言描述品类、预算与偏好，单列查看商品价格、规格、库存、推荐理由、品牌背景与可用比价证据 |
| 详情与咨询 | 打开真实商城 H5 详情入口，获取商品、店铺、订单或售后的客服咨询链接 |
| 购物车与地址 | 授权后查看和管理购物车、收货地址列表，使用内置离线快照解析三级省市区 |
| 结算与跟进 | 预览并确认提交订单、获取 H5 收银台支付入口、查看订单物流时间轴与售后状态 |

## 用户控制与数据边界

- 修改购物车、地址、订单或发起售后前，必须取得用户明确同意。
- 访客身份不等于会员授权；展示收银台链接或创建结算不代表已完成支付，售后申请或完成不代表银行实际到账。
- 访客凭据、授权状态与未结算请求保存在当前系统用户的私有状态目录（`0700`/`0600`），不写入聊天或共享日志；地址号码校验依赖 `third_party/` 离线库。

## 目录结构

```text
SKILL.md                            # 常规调用、正文要求、按需参考路由与安全底线
README.md                           # 人类安装、快速开始与目录说明
defaults.json                       # 公开默认生产环境配置
agents/openai.yaml                  # 宿主展示元数据与默认提示
references/
  presentation.md                   # 正文细则、HTML 商品卡片与宿主适配
  authorization.md                  # 会员授权、恢复原任务、下单确认与支付边界
  recovery.md                       # 未知态恢复、超时、取消、清空与常驻模式
  address.md                        # 离线省市区解析、地址确认与隐私规则
  maintenance.md                    # 正式版本更新检查、提醒选择与替换安装
  protocol.md                       # Control 公开会话与业务文档完整协议
  xiaoyi.md                         # 小艺专用 A2A 渠道说明
scripts/
  service.py                        # 单次调用与常驻服务统一入口
  link_response.py                  # Markdown 电脑 H5／手机小程序双入口与去重回退
  client.py                         # 访客身份、会话、增量文档与授权恢复
  control_agent.py                  # 轻量公开访客命令行客户端保留入口
  cards.py                          # 商品数据收集、Markdown 与 HTML 卡片渲染
  commerce_render.py                # 购物车、结算与售后的三格式渲染
  commerce_ui.py                    # HTML 卡片共用主题变量与页面外壳
  address_cards.py                  # 收货地址快照校验与静态展示
  logistics_cards.py                # 订单物流快照校验与包裹时间轴展示
  customer_service_cards.py         # 客服入口校验与渠道链接展示
  region_lookup.py                  # 离线省市区名称转三级 ID 与地址拆分
  phone_privacy.py                  # 离线电话号码识别组件加载与完整性校验
  update_check.py                   # GitHub 正式 Release 检查与提醒偏好记录
data/
  regions-prod.json                 # 生产地区目录只读快照
  regions-pre.json                  # 预发地区目录只读快照
third_party/                        # 离线 phonenumberslite wheel 与许可证
tests/                              # 离线单元与契约测试及匿名复现样例
```

本 Skill 采用 [Apache-2.0 许可证](LICENSE)。直接调用底层购物工具的独立 CLI Skill 为 `filtmall-shopping-cli`，与本 Skill 的身份和会话相互独立。

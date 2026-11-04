# 筛电托管 Agent Skill

版本：3.0.0；安装名称：`filtmall-shopping`；许可证：[Apache-2.0](LICENSE)。

唯一入口是 `scripts/service.py`。**推荐优先使用 `--once` 单次调用模式**，每次处理一条 JSON 请求后退出，无需维护后台进程；仅在宿主需要且能可靠维护持久进程时使用常驻模式。服务内部完成身份申请、提交、轮询终态和商品卡片渲染。服务依赖的两个模块 `scripts/client.py`（API 客户端）和 `scripts/cards.py`（卡片渲染）只作为库导入，没有命令行入口。

将整个目录复制到外部 Agent 的 Skill 目录，具备 Python 3.10+ 即可，无需安装额外依赖。通用接入不需要 SSH、预分配渠道密钥或配置 AK/SK；服务通过公开接口自动申请、私有保存和刷新访客 token。

本包的公开默认配置见 `defaults.json`，明确为 **pre 测试环境**：`https://pre-control.filtalgo.com` / `pre-shopping-commerce`。这些是公开地址与目标标识，不是凭据。外部 Agent 可以直接开始试用；不自动访问生产。切换到其他已开放目标时同时传 `--control-url` 与 `--agent-id`。

```bash
python3 "<skill-dir>/scripts/service.py" --format widget
```

推荐使用 `python3 "<skill-dir>/scripts/service.py" --once --format widget`，向 stdin 写入一行 `{"conversation":"<对话标识>","text":"用户问题"}`，读取一行应答后进程退出。续聊使用同一个对话标识；状态未知或请求未完成时，单次调用 `{"op":"resume","conversation":"<同一对话标识>"}` 恢复原请求。也可使用上面的常驻模式。不要自行编写包装器、代理或临时脚本，也不要直接调用内部客户端或 HTTP 接口。具体请求及错误处理见 [SKILL.md](SKILL.md)。

启动后每次写入一行 JSON、读取一行应答：

```json
{"op":"send","conversation":"<宿主生成的对话标识>","text":"推荐100元以内的洗发水，只查询。"}
{"op":"resume","conversation":"<宿主生成的对话标识>"}
```

成功应答形如 `{"id":1,"ok":true,"status":"completed","card_count":3,"html_file":"…cards.html","answer_file":"…answer.md"}`：卡片分别写入 fragment_file（片段）和 page_file（完整页面），正文写入 answer_file，应答只回路径，大段 HTML 和 Markdown 不经过宿主上下文；失败应答为 `{"id":1,"ok":false,"error":{"code":"…","message":"…"}}`。后续消息继续 `send` 并沿用对话标识；断线、超时或 accepted 后只用 `resume`；停止用 `cancel` 再 `resume` 确认；清空用 `clear`；`status` 查状态；`ping` 查进程存活。动态文本只作为 JSON 字段传入，不拼接 Shell。多用户宿主必须传独立、可信的 `--user-key`；多进程对同一用户的身份刷新由文件锁串行化，长时间等结果不占锁。

宿主 Agent 支持在对话窗口内内联 HTML 片段时，必须原样使用 `fragment_file`，不要自行修改或重新生成片段，也不要展示 `page_file` 或 `html_file` 指向的完整网页。仅在不能内联片段且需要独立页面时使用 `page_file`。

需要地区时，服务返回 `region_selection_required`；Agent 使用 `scripts/region_lookup.py` 查询包内 pre 地区数据，逐级向用户询问省、市、区，再让用户填写详细地址，校验完整路径后提交同一会话。数据来源、工具请求格式、环境限制及交互规则见 [SKILL.md](SKILL.md)。

商品卡片随应答一起返回，不需要宿主自己解析 schema：`format` 可选 `widget`、`markdown`（`.cards.md`）、`text`（`.cards.txt`）和 `json`（`.cards.json`），都通过 `html_file` 返回；`"all":true` 关闭引用过滤，`"max":N` 限制条数，`--out-dir` 或请求 `out_dir` 指定输出目录。`widget` 将商品图片缩小压缩后以 data URI 嵌入 HTML；仅允许指定商品图片源，下载或压缩失败时显示占位块。宿主须支持显示 `data:` 图片。

凭据默认位于当前用户的 `~/.local/state/filtalgo-agent/<命名空间>/state.json`。命名空间绑定 HTTPS 地址、Agent 和用户，Unix 文件 0600/目录 0700；Windows 使用宿主用户目录的私有 ACL。`--state-dir` 用于可信宿主指定私有目录，不能共享给其他用户。不将 token 放进模型消息、日志或命令行。访客身份不等于会员授权。请求会员工具时，如返回 `authorization_required`，展示 `authorization_url` 并结束本轮；用户授权后用原会话发送下一条消息，由客户端确认授权后继续。

使用约束见 [SKILL.md](SKILL.md)，原生公开 API 见 [协议说明](references/protocol.md)。公开会话 API 与标准 A2A Agent Card 协议不同。

独立购物 CLI Skill 仍叫 `filtmall-shopping-cli`，不受此修改影响。不从它迁用 OAuth 会话或 token，也不为同一用户动作同时执行两种方式。线上业务能力根据目标 Agent 和用户授权单独验收。

宿主须能够读取返回路径并使用 UTF-8。图片通过 OSS 服务端缩图控制在最长边 160 像素、图片数据 12 KiB 以内；无法获得符合限制的图片时使用占位块。卡片总数可通过 `max` 控制。链接采用标准 HTML 链接，不支持时展示响应中的 `product_links`。

# 更新记录

## 2.4.3

- 会话级客户端标识改为 `filtalgo.skill.<host>`，远端可按宿主区分会话。
- 每次调用追加本地 `calls.jsonl`（host / host_source / format / card_count / card_source / status / error_code / version），不记录用户文本；`FILTALGO_NO_LOG=1` 可关闭。

## 2.4.2

- 追问轮增量结果没有商品块时，从会话文档库读取最近一组商品块重建卡片，替代本地快照。
- 卡片兜底顺序调整为：会话库 → 本地快照 → 无。

## 2.4.1

- 新增宿主路由表（`scripts/hosts.py`）：`today` / `workbuddy` / `doubao` / `qianwen` / `lingguang` / `default`，含中文与大小写别名归一。
- 识别到宿主时展示格式由路由表固定（WorkBuddy 使用 `html`），请求里的 `format` 默认忽略，仅 `FILTALGO_FORMAT_OVERRIDE=1` 时生效；`default` 保留原有行为。
- 宿主按会话锁定：首次确定后后续轮自动沿用，前后不一致以首次为准。

## 2.3.21–2.3.35

- 豆包端正文图片改为先下载到会话工作目录再插入，PC 与手机端一致。
- 渲染层补比价来源链接；单款详情固定顺序（标题与价格、图、比价、入口）；购物车卡片增加勾选态与图例。
- 追问轮复用上一轮商品事实并标注快照时间；Markdown 双入口链接压缩为一行的“电脑端 ｜ 手机端”。

## 2.3.3

- Markdown 业务链接增加电脑 H5 与手机小程序双入口，通过公开 Gateway 匿名解析，不依赖 CLI、会员登录或 Control 凭据。
- 同轮跨 Markdown 产物共享解析缓存，最多解析 10 个不同链接；重复处理已有双入口保持不变，失败保留原 H5 链接。
- 授权链接、图片、代码和非生产域名不转换；HTML 卡片保留原 H5 入口。

# 版本更新检查、提醒选择与替换安装

仅当响应中的可选字段 `skill_update` 显示 `status="available"` 且 `notify=true`，或用户主动询问检查/更新本 Skill 时，读取本参考。

## 自动检查与提醒时机

- 每次有效 `send` 前，`scripts/service.py` 在独立子进程中检查官方正式 Release（`https://api.github.com/repos/filtalgo/Filtmall-Shopping-Skill/releases/latest`），默认总预算 2 秒（可通过 `--update-timeout` 在 `(0,30]` 秒内调整），不携带任何业务凭据或对话文本。`resume`、`cancel` 等非 `send` 操作不等待检查；检查超时或失败降级为 `unknown`，不影响业务结果与本轮产物。
- **业务优先**：先处理业务响应、异常恢复和会员授权，最后再看 `skill_update`。
- **克制提醒**：仅当 `skill_update.status == "available"` 且 `skill_update.notify == true` 时，在回复末尾简短附一句“Skill 有新版（`<release_tag>`），可选择现在更新、稍后或忽略此版本”并给出真实 `release_url`；其余状态一律不提示。
- **实际展示后立即记 `shown`**：一旦向用户展示了更新提示，立即执行一次本地管理命令记录 `shown`，避免同会话重复打扰；未向用户展示则不要记录 `shown`。

## 本地记录用户提醒选择

“现在更新 / 稍后 / 忽略此版本”完全由宿主在本地处理，**严禁把这些选择当作购物消息再次 `send` 给远端 Agent**。

管理命令复用原业务调用的安装目录及完全一致的命名空间参数（`--state-dir`、`--user-key`，若切换过环境还须成对带上原 `--control-url` 与 `--agent-id`；默认环境则均省略），不读取 stdin、不创建业务身份或心跳，输出一行 JSON 后退出：

```bash
# 独立检查最新版本
python3 "<skill-dir>/scripts/service.py" --state-dir "<原 state-dir>" --user-key "<原 user-key>" --update-action check --update-conversation "<当前 conversation>"

# 实际向用户展示更新提醒后记录 shown（抑制当前 conversation 对该版本的重复提醒）
python3 "<skill-dir>/scripts/service.py" --state-dir "<原 state-dir>" --user-key "<原 user-key>" --update-action shown --update-version "<release_tag>" --update-conversation "<当前 conversation>"

# 用户选择“稍后”时记录 later（抑制当前 conversation 对该版本的提醒）
python3 "<skill-dir>/scripts/service.py" --state-dir "<原 state-dir>" --user-key "<原 user-key>" --update-action later --update-version "<release_tag>" --update-conversation "<当前 conversation>"

# 用户选择“忽略此版本”时记录 ignore（对当前本机用户及安装路径抑制该版本提醒，后续有更高版本仍会提醒）
python3 "<skill-dir>/scripts/service.py" --state-dir "<原 state-dir>" --user-key "<原 user-key>" --update-action ignore --update-version "<release_tag>" --update-conversation "<当前 conversation>"

# 用户要求恢复全部更新提醒时执行 reset
python3 "<skill-dir>/scripts/service.py" --state-dir "<原 state-dir>" --user-key "<原 user-key>" --update-action reset
```

未自定义 `--state-dir` 或 `--user-key` 时省略对应参数以沿用默认命名空间；`<release_tag>` 原样使用 `skill_update.release_tag`（保留可选 `v` 前缀）。管理命令返回 `ok=false` 时如实说明，不宣称已保存。字段定义见 [protocol.md](protocol.md#skill-更新检查与本地提醒)。

## 执行“现在更新”与回退安全步骤

本包不内置自动覆盖安装器。用户确认“现在更新”时，按原安装渠道稳妥替换：

1. **先结清当前请求并停旧进程**：若上一轮业务状态未知或挂起，先用原 `conversation` 执行 `resume` 确认终态；若使用了常驻服务进程，先正常退出旧进程。
2. **备份旧包、保留私有状态**：备份当前 `filtmall-shopping` 安装目录及本地定制，**完整保留宿主私有 `state` 目录**（切勿删除 `state.json` 或身份文件）。
3. **固定原始 `release_tag` 获取对应包**：按原安装渠道下载或检出本次 `release_tag` 对应的发行包（手动目录安装则完整替换 `filtmall-shopping/` 目录，确保保留 `data/`、`third_party/` 与 `LICENSE`），不得默认拉取未发布 `main` 分支或套用未经核实的通用更新命令。
4. **核对版本并重新加载**：检查新包 `SKILL.md` 的 `name: filtmall-shopping` 及 `metadata.version` 与目标 Release 一致，重新读取新 `SKILL.md` 后再发起调用。若当前宿主环境无权替换安装目录，向用户提供 `release_url` 与上述人工替换步骤，不伪称已完成更新。

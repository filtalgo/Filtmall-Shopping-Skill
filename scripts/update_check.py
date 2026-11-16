"""托管 Skill 的正式发行检查及私有提醒选择；不读取业务身份。"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


API_URL = "https://api.github.com/repos/filtalgo/Filtmall-Shopping-Skill/releases/latest"
RELEASE_URL = "https://github.com/filtalgo/Filtmall-Shopping-Skill/releases/tag/"
MAX_RESPONSE = 64 * 1024
MAX_REMINDERS = 128
VERSION = re.compile(r"v?(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\Z")


def _version(value):
    # 版本仅接受数字三段；原 tag 留给返回值和链接。
    match = VERSION.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError("unsupported version")
    return tuple(int(part) for part in match.groups())


def _digest(value):
    # 对话、用户和安装路径仅存摘要，原文不落盘也不发往远端。
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 官方 API 的跳转也视为异常，不向其他地址转发请求。
        return None


def _fetch_release(timeout):
    # 子进程只访问这一固定公开 API，不使用 Cookie 或 Authorization。
    # 尊重宿主已有代理；不新增或更改代理配置，不输出代理地址或凭据。
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(), _NoRedirect())
    request = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "filtmall-shopping-update-check",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with opener.open(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError("unexpected HTTP status")
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError("response too large")
    release = json.loads(raw)
    # 不将 Release 正文带回父进程，缩小输入和输出边界。
    if not isinstance(release, dict):
        raise ValueError("invalid release")
    return {key: release.get(key) for key in ("tag_name", "draft", "prerelease")}


def _safe_path(path):
    # 拒绝已有路径中的符号链接、Windows junction/reparse point。
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("unsafe state path")


class UpdateChecker:
    def __init__(self, skill_dir, state_dir, user_key="local", timeout=2.0):
        # 安装目录按实际目标隔离，提醒文件不复用 client.Store 文件。
        self.skill_dir = Path(skill_dir).resolve()
        self.state_dir = Path(os.path.abspath(state_dir)) / "skill-update-reminders"
        self.state_path = self.state_dir / (_digest(str(self.skill_dir) + "\0" + str(user_key)) + ".json")
        self.timeout = float(timeout)
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 30:
            raise ValueError("timeout must be finite and within (0, 30]")

    def _local_version(self):
        # 只读取 YAML frontmatter 中 metadata 下的 version，不依赖 YAML 包。
        text = (self.skill_dir / "SKILL.md").read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines or lines[0] != "---":
            raise ValueError("missing metadata")
        metadata = False
        metadata_count = 0
        names = []
        closed = False
        versions = []
        for line in lines[1:]:
            if line == "---":
                closed = True
                break
            if line and not line[0].isspace():
                metadata = line == "metadata:"
                metadata_count += int(metadata)
                name = re.fullmatch(r"name:\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s#]+))\s*", line)
                if name:
                    names.append(next(value for value in name.groups() if value is not None))
            if metadata:
                match = re.fullmatch(r"  version:\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s#]+))\s*", line)
                if match:
                    versions.append(next(value for value in match.groups() if value is not None))
        if not closed or names != ["filtmall-shopping"] or metadata_count != 1 or len(versions) != 1:
            raise ValueError("missing or ambiguous version")
        _version(versions[0])
        return versions[0]

    def _read_state(self):
        # 文件缺失为首次使用；损坏明确报错，由 check 降级、record 诚实返回。
        _safe_path(self.state_path)
        try:
            if not stat.S_ISREG(self.state_path.stat().st_mode):
                raise ValueError("invalid state file")
            with self.state_path.open("rb") as stream:
                raw = stream.read(MAX_RESPONSE + 1)
        except FileNotFoundError:
            return {"ignored": [], "shown": {}}
        if len(raw) > MAX_RESPONSE:
            raise ValueError("state too large")
        state = json.loads(raw)
        if not isinstance(state, dict) or set(state) != {"ignored", "shown"}:
            raise ValueError("invalid state")
        if not isinstance(state["ignored"], list) or not isinstance(state["shown"], dict):
            raise ValueError("invalid state")
        if len(state["ignored"]) > MAX_REMINDERS or len(state["shown"]) > MAX_REMINDERS:
            raise ValueError("state too large")
        for version in state["ignored"]:
            _version(version)
        for key, version in state["shown"].items():
            if not re.fullmatch(r"[a-f0-9]{64}", key):
                raise ValueError("invalid reminder")
            _version(version)
        return state

    @contextmanager
    def _locked_state(self):
        # 锁文件常驻；操作系统在进程退出时释放锁，避免崩溃遗留占位锁。
        _safe_path(self.state_dir)
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        _safe_path(self.state_dir)
        lock = self.state_path.with_suffix(".lock")
        _safe_path(lock)
        fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        acquired = False
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"0")
            deadline = time.monotonic() + 0.5
            while True:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise ValueError("state busy")
                    time.sleep(0.01)
            yield
        finally:
            try:
                if acquired:
                    if os.name == "nt":
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def check(self, conversation=None):
        # 每次创建独立联网子进程；run超时会终止并回收子进程，不缓存结果。
        result = {"status": "unknown", "notify": False,
                  "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}
        try:
            current = self._local_version()
            result["current_version"] = current
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--worker"],
                input=json.dumps({"timeout": self.timeout}) + "\n", capture_output=True,
                text=True, encoding="utf-8", timeout=self.timeout,
            )
            if process.returncode != 0 or len(process.stdout) > MAX_RESPONSE:
                raise ValueError("worker failed")
            release = json.loads(process.stdout)
            if not isinstance(release, dict) or release.get("draft") is not False or release.get("prerelease") is not False:
                raise ValueError("not a stable release")
            tag = release.get("tag_name")
            remote = _version(tag)
            local = _version(current)
            status = "available" if remote > local else "local_newer" if remote < local else "up_to_date"
            result.update(status=status, latest_version=tag.removeprefix("v"), release_tag=tag, release_url=RELEASE_URL + tag)
            if status == "available":
                result["notify"] = True
                try:
                    state = self._read_state()
                    ignored = any(_version(value) == remote for value in state["ignored"])
                    shown = state["shown"].get(_digest(str(conversation))) if conversation else None
                    result["notify"] = not (ignored or (shown and _version(shown) == remote))
                except (OSError, ValueError, TypeError):
                    pass
                result["message"] = "发现托管 Skill 新版，可按官方安装方式更新。"
        except subprocess.TimeoutExpired:
            result["reason"] = "timeout"
        except (OSError, ValueError, TypeError, UnicodeError):
            result["reason"] = "check_failed"
        return result

    def record(self, action, version=None, conversation=None):
        # 管理操作仅写提醒，不联网、不读取身份、不重新提交购物请求。
        try:
            if action not in ("shown", "later", "ignore", "reset"):
                raise ValueError("invalid action")
            if action != "reset":
                normalized = ".".join(map(str, _version(version)))
                if action in ("shown", "later") and not conversation:
                    raise ValueError("conversation required")
            with self._locked_state():
                state = {"ignored": [], "shown": {}} if action == "reset" else self._read_state()
                if action == "ignore":
                    state["ignored"] = [item for item in state["ignored"] if item != normalized] + [normalized]
                    state["ignored"] = state["ignored"][-MAX_REMINDERS:]
                elif action in ("shown", "later"):
                    key = _digest(str(conversation))
                    state["shown"].pop(key, None)
                    state["shown"][key] = normalized
                    state["shown"] = dict(list(state["shown"].items())[-MAX_REMINDERS:])
                _safe_path(self.state_path)
                fd, name = tempfile.mkstemp(prefix=".reminder-", dir=self.state_dir)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as stream:
                        json.dump(state, stream, ensure_ascii=True)
                        stream.flush()
                        os.fsync(stream.fileno())
                    _safe_path(self.state_path)
                    os.replace(name, self.state_path)
                finally:
                    if os.path.exists(name):
                        os.unlink(name)
            return {"ok": True, "action": action}
        except (OSError, ValueError, TypeError, UnicodeError):
            return {"ok": False, "action": action, "error": "reminder_not_saved"}


def main():
    # 独立命令和worker都只输出一条JSON，不暴露远端异常正文。
    if sys.argv[1:] == ["--worker"]:
        try:
            request = json.loads(sys.stdin.readline(1024))
            timeout = float(request["timeout"])
            if not math.isfinite(timeout) or not 0 < timeout <= 30:
                raise ValueError("invalid timeout")
            result = _fetch_release(timeout)
        except Exception:
            result = {"error": "fetch_failed"}
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument("--state-dir", required=True)
        parser.add_argument("--user-key", default="local")
        parser.add_argument("--conversation")
        parser.add_argument("--action", choices=("check", "shown", "later", "ignore", "reset"), default="check")
        parser.add_argument("--version")
        parser.add_argument("--timeout", type=float, default=2.0)
        args = parser.parse_args()
        try:
            checker = UpdateChecker(Path(__file__).resolve().parents[1], args.state_dir, args.user_key, args.timeout)
            result = checker.check(args.conversation) if args.action == "check" else checker.record(args.action, args.version, args.conversation)
        except (OSError, ValueError, TypeError):
            result = {"ok": False, "error": "invalid_configuration"}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()

"""Official Codex app-server, JSON-RPC over stdio. No token extraction or API keys."""

import asyncio
import contextlib
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

from .paths import runtime_directory


class BridgeError(Exception):
    pass


class CodexBridge:
    def __init__(self):
        self.binary = os.getenv("STUDY_CODEX_BIN") or shutil.which("codex")
        if not self.binary:
            for candidate in [
                "/Applications/ChatGPT.app/Contents/Resources/codex",
                "/Applications/Codex.app/Contents/Resources/codex",
            ]:
                if Path(candidate).is_file():
                    self.binary = candidate
                    break
        # Separate auth/config from the user's daily Codex workspace.
        self.runtime = runtime_directory()
        self.proc = None
        self.reader = None
        self.pending = {}
        self.queues = {}
        self.start_lock = asyncio.Lock()
        self.counter = 0
        self.login_id = None

    async def start(self):
        async with self.start_lock:
            if self.proc and self.proc.returncode is None:
                return
            if not self.binary:
                raise BridgeError("找不到 Codex。請安裝 Codex CLI 或桌面版後再試。")
            self.runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
            runtime_home = self.runtime / "codex-home"
            runtime_home.mkdir(mode=0o700, exist_ok=True)
            runtime_home.chmod(0o700)
            workspace = self.runtime / "workspace"
            workspace.mkdir(mode=0o700, exist_ok=True)
            config = """forced_login_method = "chatgpt"
cli_auth_credentials_store = "auto"
web_search = "disabled"
project_doc_max_bytes = 0
model_provider = "openai"
[history]
persistence = "none"
[analytics]
enabled = false
[features]
shell_tool = false
unified_exec = false
apps = false
plugins = false
hooks = false
memories = false
multi_agent = false
multi_agent_v2 = false
browser_use = false
browser_use_external = false
computer_use = false
code_mode = false
code_mode_host = false
image_generation = false
view_image = false
skip_host_skill_discovery = true
"""
            (runtime_home / "config.toml").write_text(config)
            # Do not pass API credentials, inherited model config, or connector secrets.
            env = {
                k: v
                for k, v in os.environ.items()
                if k
                in {
                    "PATH",
                    "HOME",
                    "USER",
                    "LOGNAME",
                    "SHELL",
                    "TMPDIR",
                    "LANG",
                    "LC_ALL",
                    "SSL_CERT_FILE",
                    "CODEX_CA_CERTIFICATE",
                }
            }
            env["CODEX_HOME"] = str(runtime_home)
            self.proc = await asyncio.create_subprocess_exec(
                self.binary,
                "app-server",
                "--listen",
                "stdio://",
                cwd=workspace,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=8_000_000,
            )
            self.reader = asyncio.create_task(self._read())
            try:
                await self.rpc(
                    "initialize",
                    {
                        "clientInfo": {
                            "name": "ai_study_partner",
                            "title": "AIStudyPartner",
                            "version": "0.1.0",
                        }
                    },
                )
                await self.send({"method": "initialized", "params": {}})
            except Exception:
                await self.close()
                raise

    async def send(self, message):
        if not self.proc or not self.proc.stdin or self.proc.returncode is not None:
            raise BridgeError("Codex 引擎未啟動。")
        self.proc.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode())
        await self.proc.stdin.drain()

    async def rpc(self, method, params=None, timeout=20):
        self.counter += 1
        request_id = self.counter
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.send({"id": request_id, "method": method, "params": params or {}})
            return await asyncio.wait_for(future, timeout)
        except (TimeoutError, BrokenPipeError, ConnectionError) as exc:
            raise BridgeError("Codex 回應逾時或連線中斷，請重新啟動本機服務。") from exc
        finally:
            self.pending.pop(request_id, None)

    async def _read(self):
        try:
            while line := await self.proc.stdout.readline():
                message = json.loads(line)
                if "id" in message and "method" not in message:
                    future = self.pending.get(message["id"])
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(
                                BridgeError("Codex 拒絕請求，請檢查登入、版本及模型權限。")
                            )
                        else:
                            future.set_result(message.get("result", {}))
                elif "id" in message:
                    # This tutoring integration never grants tool, file, or permission requests.
                    await self.send(
                        {
                            "id": message["id"],
                            "error": {
                                "code": -32601,
                                "message": "Tools and permission escalation are disabled.",
                            },
                        }
                    )
                else:
                    params = message.get("params", {})
                    queue = self.queues.get(params.get("threadId"))
                    if queue and message.get("method") in {
                        "item/completed",
                        "thread/tokenUsage/updated",
                        "turn/completed",
                    }:
                        try:
                            queue.put_nowait(message)
                        except asyncio.QueueFull:
                            raise BridgeError("Codex 事件超過上限。") from None
        except (asyncio.CancelledError, ValueError, BridgeError):
            pass
        finally:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(BridgeError("Codex 引擎已停止。"))
            for queue in self.queues.values():
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait({"method": "bridge/closed"})

    async def account(self):
        await self.start()
        result = await self.rpc("account/read", {"refreshToken": False})
        account = result.get("account") or {}
        # Only expose the auth mode and plan, never email or credentials.
        return {
            "authenticated": account.get("type") == "chatgpt",
            "plan": account.get("planType"),
            "auth_mode": account.get("type"),
        }

    async def login(self):
        await self.start()
        if self.login_id:
            await self.rpc("account/login/cancel", {"loginId": self.login_id})
        result = await self.rpc("account/login/start", {"type": "chatgpt"})
        self.login_id = result.get("loginId")
        url = result.get("authUrl", "")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"auth.openai.com", "chatgpt.com"}:
            raise BridgeError("登入網址不符合官方網域，已停止開啟。")
        return {"auth_url": url}

    async def logout(self):
        await self.start()
        if self.login_id:
            with contextlib.suppress(BridgeError):
                await self.rpc("account/login/cancel", {"loginId": self.login_id})
            self.login_id = None
        await self.rpc("account/logout")

    async def generate(self, model, instructions, payload, schema, image, effort):
        await self.start()
        if not (await self.account())["authenticated"]:
            raise BridgeError("請先按「登入 ChatGPT」完成瀏覽器認證。")
        started = await self.rpc(
            "thread/start",
            {
                "model": model,
                "modelProvider": "openai",
                "ephemeral": True,
                "cwd": str(self.runtime / "workspace"),
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "baseInstructions": instructions,
                "developerInstructions": "只做影像與文字教學。不得使用任何工具、讀寫檔案或執行命令。",
            },
        )
        thread_id = started["thread"]["id"]
        queue = asyncio.Queue(maxsize=2000)
        self.queues[thread_id] = queue
        content = [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]
        if image:
            content.append(
                {"type": "image", "url": f"data:image/jpeg;base64,{image}", "detail": "high"}
            )
        turn_id = None
        output = ""
        usage = {}
        try:
            turn = await self.rpc(
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": content,
                    "model": model,
                    "effort": effort,
                    "outputSchema": schema,
                    "approvalPolicy": "never",
                    "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
                },
            )
            turn_id = turn["turn"]["id"]
            async with asyncio.timeout(120):
                while True:
                    message = await queue.get()
                    method, params = message["method"], message.get("params", {})
                    if method == "item/completed":
                        item = params.get("item", {})
                        if item.get("type") == "agentMessage" and item.get("phase") != "commentary":
                            output = item.get("text", "")
                    elif method == "thread/tokenUsage/updated":
                        usage = params.get("tokenUsage", {}).get("total", {})
                    elif method == "turn/completed":
                        if params["turn"]["status"] != "completed":
                            raise BridgeError(
                                "模型未完成回應。請檢查方案額度、模型權限或稍後再試。"
                            )
                        if not output:
                            raise BridgeError("模型沒有回傳完整教學內容。")
                        return output, usage
                    elif method == "bridge/closed":
                        raise BridgeError("Codex 引擎已停止，請重新啟動。")
        except TimeoutError as exc:
            raise BridgeError("AI 回應逾時，已停止自動分析。") from exc
        finally:
            if turn_id:
                with contextlib.suppress(BridgeError):
                    await self.rpc(
                        "turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=5
                    )
            with contextlib.suppress(BridgeError):
                await self.rpc("thread/unsubscribe", {"threadId": thread_id}, timeout=5)
            self.queues.pop(thread_id, None)

    async def close(self):
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), 5)
            except TimeoutError:
                self.proc.kill()
                await self.proc.wait()
        if self.reader:
            self.reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.reader
        self.proc = None

import asyncio
from types import SimpleNamespace

import pytest

from study_partner.codex_bridge import BridgeError, CodexBridge


@pytest.mark.asyncio
async def test_rpc_demultiplexes_response_and_event():
    bridge = CodexBridge()
    reader = asyncio.StreamReader()
    bridge.proc = SimpleNamespace(stdout=reader)
    response = asyncio.get_running_loop().create_future()
    bridge.pending[7] = response
    bridge.queues["t1"] = asyncio.Queue()
    reader.feed_data(b'{"id":7,"result":{"ok":true}}\n')
    reader.feed_data(
        b'{"method":"turn/completed","params":{"threadId":"t1","turn":{"status":"completed"}}}\n'
    )
    reader.feed_eof()
    await bridge._read()
    assert await response == {"ok": True}
    assert (await bridge.queues["t1"].get())["method"] == "turn/completed"


@pytest.mark.asyncio
async def test_server_tool_requests_are_rejected(monkeypatch):
    bridge = CodexBridge()
    reader = asyncio.StreamReader()
    bridge.proc = SimpleNamespace(stdout=reader)
    sent = []

    async def send(message):
        sent.append(message)

    monkeypatch.setattr(bridge, "send", send)
    reader.feed_data(b'{"id":8,"method":"item/commandExecution/requestApproval","params":{}}\n')
    reader.feed_eof()
    await bridge._read()
    assert sent[0]["error"]["code"] == -32601
    assert "result" not in sent[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://auth.openai.com/a",
        "https://evil.example/a",
        "https://auth.openai.com.evil.example/a",
    ],
)
async def test_login_url_allowlist(monkeypatch, url):
    bridge = CodexBridge()

    async def start():
        pass

    async def rpc(*args, **kwargs):
        return {"loginId": "l1", "authUrl": url}

    monkeypatch.setattr(bridge, "start", start)
    monkeypatch.setattr(bridge, "rpc", rpc)
    with pytest.raises(BridgeError, match="網域"):
        await bridge.login()


@pytest.mark.asyncio
async def test_generate_ephemeral_image_and_cleanup(monkeypatch):
    bridge = CodexBridge()
    calls = []

    async def start():
        pass

    async def account():
        return {"authenticated": True}

    async def rpc(method, params, **kwargs):
        calls.append((method, params))
        if method == "thread/start":
            assert params["ephemeral"] is True
            assert params["model"] == "gpt-6-astra"
            assert params["sandbox"] == "read-only"
            return {"thread": {"id": "t1"}}
        if method == "turn/start":
            assert params["input"][1]["type"] == "image"
            assert params["input"][1]["url"] == "data:image/jpeg;base64,test-image"
            assert params["outputSchema"] == {"type": "object"}
            q = bridge.queues["t1"]
            await q.put(
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "type": "agentMessage",
                            "phase": "final_answer",
                            "text": '{"answer":13}',
                        }
                    },
                }
            )
            await q.put(
                {
                    "method": "thread/tokenUsage/updated",
                    "params": {"tokenUsage": {"total": {"inputTokens": 12, "outputTokens": 4}}},
                }
            )
            await q.put({"method": "turn/completed", "params": {"turn": {"status": "completed"}}})
            return {"turn": {"id": "turn1"}}
        return {}

    monkeypatch.setattr(bridge, "start", start)
    monkeypatch.setattr(bridge, "account", account)
    monkeypatch.setattr(bridge, "rpc", rpc)
    text, usage = await bridge.generate(
        "gpt-6-astra", "instructions", {"task": "read"}, {"type": "object"}, "test-image", "low"
    )
    assert text == '{"answer":13}' and usage["inputTokens"] == 12
    assert calls[-1][0] == "thread/unsubscribe"
    assert not bridge.queues


@pytest.mark.asyncio
async def test_api_key_auth_is_not_accepted(monkeypatch):
    bridge = CodexBridge()

    async def start():
        pass

    async def rpc(*args, **kwargs):
        return {"account": {"type": "apiKey"}}

    monkeypatch.setattr(bridge, "start", start)
    monkeypatch.setattr(bridge, "rpc", rpc)
    assert (await bridge.account())["authenticated"] is False

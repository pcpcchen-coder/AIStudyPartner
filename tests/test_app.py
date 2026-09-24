import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import study_partner.app as module
from study_partner.arithmetic import check
from study_partner.demo import demo
from study_partner.provider import CodexProvider, ProviderError, normalize_image
from study_partner.schemas import Observation, ObserveRequest


@pytest.fixture
def client(monkeypatch):
    async def account():
        return {"authenticated": False, "plan": None, "auth_mode": None}

    monkeypatch.setattr(module.provider.bridge, "account", account)
    module.cache.clear()
    with TestClient(module.app, base_url="http://127.0.0.1:8765") as client:
        yield client


def headers(client, cloud=True):
    token = client.get("/api/config").json()["token"]
    return {"X-Study-Token": token, "X-Study-Cloud": "enabled" if cloud else "disabled"}


def picture():
    output = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()


def payload(subject="數學", **kwargs):
    observation, _ = demo(subject)
    return {
        "question": observation.question,
        "student_answer": observation.student_answer,
        "subject": subject,
        "confirmed": True,
        "demo": True,
        **kwargs,
    }


@pytest.mark.parametrize(
    ("question", "answer", "expected"),
    [
        ("24 ÷ 3 + 5 = ?", "13", True),
        ("24 ÷ 3 + 5 = ?", "3", False),
        ("0.1+0.2", "0.3", True),
        ("1/3+1/3", "2/3", True),
        ("100 公分等於幾公尺？", "1", None),
        ('__import__("os")', "0", None),
        ("2**999999", "0", None),
        ("1/0", "0", None),
        ("5//2", "2", None),
    ],
)
def test_exact_arithmetic(question, answer, expected):
    assert check(question, answer) is expected


def test_demo_confirmation_and_solution_gate(client):
    h = headers(client)
    result = client.post("/api/tutor", headers=h, json=payload(hint_level=1)).json()
    assert result["source"] == "demo"
    assert result["verification"] == "exact_arithmetic"
    assert result["explanation"] is None and result["exercises"] == []
    unconfirmed = client.post(
        "/api/tutor", headers=h, json=payload(confirmed=False, hint_level=3)
    ).json()
    assert unconfirmed["verdict"] == "uncertain"
    assert unconfirmed["explanation"] is None
    full = client.post("/api/tutor", headers=h, json=payload(hint_level=3)).json()
    assert "13" in full["explanation"] and len(full["exercises"]) == 2


@pytest.mark.parametrize("subject", ["數學", "國語", "英文", "自然", "社會", "其他"])
def test_all_demo_subjects(client, subject):
    assert client.get(f"/api/demo/{subject}").status_code == 200
    result = client.post("/api/tutor", headers=headers(client), json=payload(subject, hint_level=3))
    assert result.status_code == 200
    assert result.json()["exercises"]


def test_demo_rejects_arbitrary_question(client):
    result = client.post("/api/tutor", headers=headers(client), json=payload(question="unseen"))
    assert result.status_code == 422


def test_cloud_consent_and_local_boundary(client):
    data = {"image": picture()}
    assert client.post("/api/observe", json=data).status_code == 403
    assert client.post("/api/observe", headers=headers(client, False), json=data).status_code == 403
    assert client.get("/api/config", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/config", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/config", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/").headers["Cache-Control"] == "no-store"
    assert client.post("/api/clear", headers=headers(client), content="{}").status_code == 415


def test_no_raw_input_in_validation_errors(client):
    result = client.post(
        "/api/observe",
        headers=headers(client),
        json={"image": "secret-homework", "extra": "secret"},
    )
    assert result.status_code == 422
    assert "secret" not in result.text


def test_streamed_body_limit(client):
    h = {**headers(client), "Content-Type": "application/json"}
    result = client.post("/api/observe", headers=h, content=iter([b"x" * 2_100_000] * 2))
    assert result.status_code == 413


def test_images_normalized_and_invalid_rejected(client):
    normalized = normalize_image(picture())
    with Image.open(io.BytesIO(base64.b64decode(normalized))) as image:
        assert image.format == "JPEG"
    for invalid in [
        "https://evil.example/a.jpg",
        "data:image/jpeg;base64,???",
        "data:image/png;base64,YWJj",
    ]:
        result = client.post("/api/observe", headers=headers(client), json={"image": invalid})
        assert result.status_code == 422


def test_tutor_cache_and_clear(client, monkeypatch):
    calls = []

    async def tutor(body, image):
        calls.append(body)
        return demo("英文")[1]

    monkeypatch.setattr(module.provider, "tutor", tutor)
    data = payload("英文", demo=False)
    h = headers(client)
    assert client.post("/api/tutor", headers=h, json=data).status_code == 200
    assert client.post("/api/tutor", headers=h, json={**data, "hint_level": 3}).status_code == 200
    assert len(calls) == 1
    client.post("/api/clear", headers=h, json={})
    client.post("/api/tutor", headers=h, json=data)
    assert len(calls) == 2


def test_low_confidence_never_grades(client, monkeypatch):
    async def tutor(body, image):
        result = demo("數學")[1]
        result.confidence = 0.2
        return result

    monkeypatch.setattr(module.provider, "tutor", tutor)
    result = client.post("/api/tutor", headers=headers(client), json=payload(demo=False)).json()
    assert result["verdict"] == "uncertain"


@pytest.mark.asyncio
async def test_codex_contract_and_usage(monkeypatch):
    observation = demo("數學")[0]
    provider = CodexProvider()

    async def generate(model, instructions, payload, schema, image, effort):
        assert model == "gpt-6-astra"
        assert schema["additionalProperties"] is False
        assert image
        assert effort == "low"
        return observation.model_dump_json(), {"inputTokens": 123, "outputTokens": 45}

    monkeypatch.setattr(provider.bridge, "generate", generate)
    result = await provider.observe(ObserveRequest(image=picture()), normalize_image(picture()))
    assert result == observation
    assert provider.calls == 1 and provider.input_tokens == 123 and provider.output_tokens == 45


@pytest.mark.asyncio
async def test_codex_failure_and_call_cap(monkeypatch):
    from study_partner.codex_bridge import BridgeError

    provider = CodexProvider()

    async def fail(*args):
        raise BridgeError("請先登入 ChatGPT")

    monkeypatch.setattr(provider.bridge, "generate", fail)
    with pytest.raises(ProviderError, match="登入"):
        await provider.generate(Observation, {})
    provider.calls = provider.max_calls
    with pytest.raises(ProviderError, match="上限"):
        await provider.generate(Observation, {})


def test_browser_login_boundary(client, monkeypatch):
    async def login():
        return {"auth_url": "https://auth.openai.com/authorize?state=test"}

    monkeypatch.setattr(module.provider.bridge, "login", login)
    assert client.post("/api/auth/login", json={}).status_code == 403
    response = client.post("/api/auth/login", headers=headers(client), json={})
    assert response.json()["auth_url"].startswith("https://auth.openai.com/")


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-6-sol", "gpt-6-luna"])
def test_selected_model_reaches_both_inference_stages(client, monkeypatch, model):
    calls = []

    async def generate(selected, instructions, data, schema, image, effort):
        calls.append(selected)
        fixture = demo("數學")[0 if effort == "low" else 1]
        return fixture.model_dump_json(), {}

    monkeypatch.setattr(module.provider.bridge, "generate", generate)
    h = headers(client)
    read = client.post("/api/observe", headers=h, json={"image": picture(), "model": model})
    teach = client.post("/api/tutor", headers=h, json=payload(demo=False, model=model))
    assert read.status_code == teach.status_code == 200
    assert read.json()["model"] == teach.json()["model"] == model
    assert calls == [model, model]


def test_model_cache_isolation_and_invalid_selection(client, monkeypatch):
    calls = []

    async def generate(selected, *args):
        calls.append(selected)
        return demo("數學")[1].model_dump_json(), {}

    monkeypatch.setattr(module.provider.bridge, "generate", generate)
    h = headers(client)
    for model in ["gpt-6-sol", "gpt-6-luna", "gpt-6-sol"]:
        response = client.post("/api/tutor", headers=h, json=payload(demo=False, model=model))
        assert response.status_code == 200
        assert response.json()["model"] == model
    assert calls == ["gpt-6-sol", "gpt-6-luna"]
    assert client.post("/api/tutor", headers=h, json=payload(demo=False, model="unknown")).status_code == 422
    assert client.post("/api/observe", headers=h, json={"image": picture(), "model": "unknown"}).status_code == 422
    assert calls == ["gpt-6-sol", "gpt-6-luna"]


def test_unavailable_selected_model_never_falls_back(client, monkeypatch):
    from study_partner.codex_bridge import BridgeError

    calls = []

    async def unavailable(model, *args):
        calls.append(model)
        raise BridgeError("所選模型暫時無法使用")

    monkeypatch.setattr(module.provider.bridge, "generate", unavailable)
    response = client.post("/api/tutor", headers=headers(client), json=payload(demo=False, model="gpt-6-luna"))
    assert response.status_code == 503
    assert calls == ["gpt-6-luna"]

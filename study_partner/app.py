import asyncio
import hashlib
import secrets
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .arithmetic import check
from .codex_bridge import BridgeError
from .demo import demo
from .provider import CodexProvider, ProviderError, normalize_image
from .schemas import ObserveRequest, TutorRequest


@asynccontextmanager
async def lifespan(app):
    yield
    await provider.bridge.close()


app = FastAPI(
    lifespan=lifespan, title="AIStudyPartner", docs_url=None, redoc_url=None, openapi_url=None
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])
provider = CodexProvider()
token = secrets.token_urlsafe(32)
lock = asyncio.Lock()
cache = OrderedDict()
cache_generation = 0
MAX_BODY = 4_100_000


@app.middleware("http")
async def boundary(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.headers.get('host')}"
        if (origin and origin != expected) or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "只允許本機頁面存取。"}, 403)
        if request.method == "POST":
            if not secrets.compare_digest(request.headers.get("x-study-token", ""), token):
                return JSONResponse({"detail": "頁面已過期，請重新整理。"}, 403)
            if not request.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse({"detail": "只接受 JSON。"}, 415)
            # Bound streaming bodies too; never log raw student data in validation errors.
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BODY:
                    return JSONResponse({"detail": "圖片過大，請縮小範圍。"}, 413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({"detail": "輸入格式或長度不正確，請檢查題目與圖片。"}, 422)


@app.exception_handler(BridgeError)
@app.exception_handler(ProviderError)
async def provider_error(request, exc):
    return JSONResponse({"detail": str(exc)}, 503)


def require_cloud(request: Request):
    if request.headers.get("x-study-cloud") != "enabled":
        raise HTTPException(403, "請先開啟『允許傳送作業至 OpenAI』。")


@app.get("/api/config")
async def config():
    return {"token": token, **await provider.health()}


@app.post("/api/auth/login")
async def login():
    try:
        return await provider.bridge.login()
    except (BridgeError, OSError):
        raise HTTPException(503, "無法啟動 ChatGPT 登入，請檢查 Codex 安裝或重新啟動。") from None


@app.post("/api/auth/logout")
async def logout():
    if lock.locked():
        raise HTTPException(409, "請等目前分析結束再登出。")
    await provider.bridge.logout()
    await clear()
    return {"logged_out": True}


@app.get("/api/demo/{subject}")
async def sample(subject: str):
    try:
        observation, _ = demo(subject)
    except KeyError:
        raise HTTPException(404, "沒有這個示範科目。") from None
    return {"observation": observation, "source": "demo"}


@app.post("/api/observe")
async def observe(body: ObserveRequest, request: Request):
    require_cloud(request)
    try:
        image = normalize_image(body.image)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if lock.locked():
        raise HTTPException(429, "目前正在分析，請等這一題完成。")
    async with lock:
        result = await provider.observe(body, image)
    return {"observation": result, "source": "openai", "model": body.model or provider.model}


@app.post("/api/tutor")
async def tutor(body: TutorRequest, request: Request):
    if body.demo:
        observation, result = demo(body.subject)
        if (body.question, body.student_answer) != (
            observation.question,
            observation.student_answer,
        ):
            raise HTTPException(422, "示範只支援原始範例；自訂題目請切換雲端分析。")
        source = "demo"
    else:
        require_cloud(request)
        image = None
        if body.image:
            try:
                image = normalize_image(body.image)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
        # A short-lived bounded memory cache avoids paying again for each hint level.
        key = hashlib.sha256(
            body.model_copy(update={"model": body.model or provider.model})
            .model_dump_json(exclude={"hint_level", "confirmed"}).encode()
        ).hexdigest()
        now = time.monotonic()
        for old in list(cache):
            if now - cache[old][0] > 900:
                del cache[old]
        if key in cache:
            result = cache[key][1]
        else:
            if lock.locked():
                raise HTTPException(429, "目前正在分析，請等這一題完成。")
            epoch = cache_generation
            async with lock:
                result = await provider.tutor(body, image)
            if epoch == cache_generation:
                cache[key] = (time.monotonic(), result)
            while len(cache) > 16:
                cache.popitem(last=False)
        result = result.model_copy(deep=True)
        source = "openai"
    verification = "ai_advisory"
    if not body.confirmed or result.confidence < 0.85:
        result.verdict = "uncertain"
        result.feedback = "先確認辨識到的題目與作答，我們再一起檢查。"
    elif (
        body.subject == "數學"
        and (verified := check(body.question, body.student_answer)) is not None
    ):
        result.verdict = "correct" if verified else "needs_work"
        result.feedback = (
            "這個算式的答案相符。" if verified else "答案與算式的計算結果不同，再檢查一次運算順序。"
        )
        verification = "exact_arithmetic"
    elif not body.student_answer.strip():
        result.verdict = "in_progress"
    return {
        "source": source,
        "model": (body.model or provider.model) if source == "openai" else "示範資料",
        "verdict": result.verdict,
        "verification": verification,
        "concept": result.concept,
        "feedback": result.feedback,
        "hint": result.hints[min(body.hint_level, 2) - 1],
        "hint_level": body.hint_level,
        "explanation": result.explanation if body.hint_level == 3 and body.confirmed else None,
        "exercises": result.exercises if body.hint_level == 3 and body.confirmed else [],
        "confidence": result.confidence,
    }


@app.post("/api/clear")
async def clear():
    global cache_generation
    cache_generation += 1
    cache.clear()
    return {"cleared": True}


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="web")

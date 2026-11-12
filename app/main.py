from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .agent import build_model
from .config import Settings, get_settings
from .database import Base, make_session_factory
from .routers import chat
from .seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(app.state.engine)
    seed(app.state.session_factory)  # nạp dữ liệu mẫu nếu bảng còn trống
    yield
    app.state.engine.dispose()


def create_app(settings: Settings, model_factory=None, schema: str | None = None) -> FastAPI:
    app = FastAPI(title="LangChain Tool Calling và Thuật toán", lifespan=lifespan)

    engine, session_factory = make_session_factory(settings.database_url, schema=schema)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = settings
    # model_factory(settings, tools) -> model; test có thể truyền model giả vào
    app.state.model_factory = model_factory or build_model
    app.state.ai_calls = deque()

    @app.get("/api/health")
    def health():
        return {"status": "ok", "ai_mode": settings.ai_mode}

    app.include_router(chat.router)
    return app


app = create_app(get_settings())

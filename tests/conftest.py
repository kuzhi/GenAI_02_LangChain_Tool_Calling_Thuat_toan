import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import Settings, get_settings
from app.database import Base, make_session_factory
from app.main import create_app

# Test chạy trên chính Supabase trong .env nhưng ở schema riêng, tách khỏi bảng thật (schema public)
TEST_SCHEMA = "pytest_tool_calling"


def make_settings(**overrides) -> Settings:
    real = get_settings()
    values = dict(database_url=real.database_url, openai_api_key=None, openai_model="gpt-5-mini",
                  ai_mode="mock", cookie_secure="false", ai_max_requests_per_hour=60)
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(scope="session")
def test_database():
    settings = make_settings()
    assert settings.database_url.startswith("postgresql"), "DATABASE_URL trong .env phải là chuỗi Supabase/PostgreSQL"
    engine, _ = make_session_factory(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{TEST_SCHEMA}"'))
    scoped, _ = make_session_factory(settings.database_url, schema=TEST_SCHEMA)
    Base.metadata.create_all(scoped)
    yield scoped
    scoped.dispose()
    engine.dispose()


@pytest.fixture
def clean_database(test_database):
    """Mỗi test API bắt đầu với bảng trống (app tự nạp lại dữ liệu mẫu khi khởi động)."""
    tables = ", ".join(f'"{TEST_SCHEMA}"."{table.name}"' for table in Base.metadata.sorted_tables)
    with test_database.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client_factory(clean_database):
    clients = []

    def factory(model_factory=None, **settings):
        c = TestClient(create_app(make_settings(**settings), model_factory=model_factory, schema=TEST_SCHEMA))
        c.__enter__()
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(client_factory):
    return client_factory()

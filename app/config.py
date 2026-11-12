import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

##Quy định các thuộc tính app cần phải nhận được trước khi khởi tạo session
@dataclass(frozen=True)
class Settings:
    database_url: str
    openai_api_key: str | None
    openai_model: str
    ai_mode: str
    cookie_secure: str
    ai_max_requests_per_hour: int


#Load cac biến môi trường từ file .env vào dataclass Settings
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL"),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL") or "gpt-5-mini",
        # mock: đọc dữ liệu mẫu bằng luật cục bộ, không tốn tiền; openai: gọi model thật
        ai_mode=(os.getenv("AI_MODE") or "mock").strip().lower(),
        cookie_secure=os.getenv("COOKIE_SECURE", "false"),
        ai_max_requests_per_hour=int(os.getenv("AI_MAX_REQUESTS_PER_HOUR", 60))
    )

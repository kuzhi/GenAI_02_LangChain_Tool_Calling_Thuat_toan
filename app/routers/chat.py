import time
from collections import deque

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent import run_agent
from ..dependencies import get_db
from ..errors import api_error
from ..models import ChatRecord, Proposal
from ..schema import ChatRequest, ReviewRequest
from ..timeutil import now_utc
from ..tools import ToolError, build_tools

router = APIRouter(tags=["chat"])

SAMPLE_QUESTIONS = [
    "Kiểm tra hóa đơn I-77",
    "Kiểm tra hóa đơn I-77 và hãy ghi nhận luôn",
    "Kiểm tra hóa đơn I-79",
    "Kiểm tra hóa đơn I-78",
    "Với dây chuyền L1, ca S1, máy nào xử lý xong trước khi hết ca?",
    "Dây chuyền L1 ca S1, hãy đặt máy M2",
    "Dây chuyền L2 ca S2 có kịp không?",
    "Hôm nay nên xếp các tin của chiến dịch CMP-1 vào khung giờ nào?",
    "Chiến dịch CMP-2 gửi ngay đi",
    "Sự cố INC-9 ảnh hưởng đến đâu?",
    "Sự cố INC-10 ảnh hưởng đến đâu?",
]


def ai_quota(request: Request) -> None:
    """Giới hạn số câu hỏi gọi model trả phí mỗi giờ (AI_MAX_REQUESTS_PER_HOUR)."""
    settings = request.app.state.settings
    if settings.ai_mode != "openai":
        return
    calls: deque = request.app.state.ai_calls
    now = time.monotonic()
    while calls and now - calls[0] > 3600:
        calls.popleft()
    if len(calls) >= settings.ai_max_requests_per_hour:
        raise api_error(429, "ai_rate_limited", f"Đã dùng hết {settings.ai_max_requests_per_hour} lượt/giờ, hãy thử lại sau")
    calls.append(now)


def chat_view(chat: ChatRecord, proposals: list[Proposal]) -> dict:
    return {"chat_id": chat.id, "question": chat.question, "answer": chat.answer, "status": chat.status,
            "error": chat.error, "created_at": chat.created_at,
            # data_used: dữ liệu công cụ đã trả về, theo thứ tự gọi
            "tool_calls": chat.tool_calls or [],
            "data_used": [{"tool": c["name"], "data": c.get("result")} for c in (chat.tool_calls or []) if "result" in c],
            "proposals": [proposal_view(p) for p in proposals]}


def proposal_view(p: Proposal) -> dict:
    return {"id": p.id, "chat_id": p.chat_id, "kind": p.kind, "status": p.status, "payload": p.payload,
            "created_at": p.created_at, "reviewed_at": p.reviewed_at}


@router.get("/api/samples")
def samples():
    return {"questions": SAMPLE_QUESTIONS}


@router.post("/api/chat")
def chat(body: ChatRequest, request: Request, db: Session = Depends(get_db)):
    ai_quota(request)
    record = ChatRecord(question=body.message)
    db.add(record)
    db.commit()
    db.refresh(record)

    ctx = {"chat_id": record.id, "proposals": []}
    tools = build_tools(db, ctx)
    try:
        model = request.app.state.model_factory(request.app.state.settings, tools)
        result = run_agent(body.message, model, tools)
        record.answer, record.tool_calls = result["answer"], result["tool_calls"]
        record.status = "failed" if result.get("truncated") else "done"
    except ToolError as exc:
        record.status, record.error = "failed", exc.message
        record.tool_calls = []
    except Exception as exc:  # lỗi model/mạng: lưu lại để xem, không làm lộ chi tiết nội bộ
        record.status, record.error = "failed", f"Model chưa xử lý được yêu cầu ({type(exc).__name__})"
        record.tool_calls = []
    db.commit()

    proposals = list(db.scalars(select(Proposal).where(Proposal.chat_id == record.id)))
    return chat_view(record, proposals)


@router.get("/api/chats")
def list_chats(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.scalars(select(ChatRecord).order_by(ChatRecord.id.desc()).limit(min(max(limit, 1), 100))).all()
    return [{"chat_id": r.id, "question": r.question, "status": r.status, "created_at": r.created_at,
             "tools_called": [c["name"] for c in (r.tool_calls or [])]} for r in rows]


@router.get("/api/chats/{chat_id}")
def get_chat(chat_id: int, db: Session = Depends(get_db)):
    record = db.get(ChatRecord, chat_id)
    if record is None:
        raise api_error(404, "chat_not_found", f"Không có cuộc chat #{chat_id}")
    return chat_view(record, list(db.scalars(select(Proposal).where(Proposal.chat_id == chat_id))))


@router.get("/api/proposals")
def list_proposals(status: str | None = None, db: Session = Depends(get_db)):
    query = select(Proposal).order_by(Proposal.id.desc())
    if status:
        query = query.where(Proposal.status == status)
    return [proposal_view(p) for p in db.scalars(query)]


@router.post("/api/proposals/{proposal_id}/review")
def review_proposal(proposal_id: int, body: ReviewRequest, db: Session = Depends(get_db)):
    """Người có quyền duyệt đánh dấu đề xuất."""
    p = db.get(Proposal, proposal_id)
    if p is None:
        raise api_error(404, "proposal_not_found", f"Không có đề xuất #{proposal_id}")
    if p.status != "pending":
        raise api_error(409, "already_reviewed", f"Đề xuất #{proposal_id} đã ở trạng thái '{p.status}'")
    p.status, p.reviewed_at = body.decision, now_utc()
    db.commit()
    return proposal_view(p)

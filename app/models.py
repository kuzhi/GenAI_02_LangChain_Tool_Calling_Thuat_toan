from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .timeutil import now_utc


# ---------- Lịch sử chat để xem lại ----------
class ChatRecord(Base):
    __tablename__ = "chat_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Mỗi phần tử: {step, id, name, args, result | error}
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | done | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(30))  # invoice_match | machine_assignment
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------- Bài 01 ----------
class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3))
    amount_due_minor: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20))  # open | paid


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    received_at: Mapped[str] = mapped_column(String(40))  # ISO 8601 cùng múi giờ nên so chuỗi đúng thứ tự
    customer_id: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20))  # unmatched | matched


# ---------- Bài 02 ----------
class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    line_id: Mapped[str] = mapped_column(String(40), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | done


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    line_id: Mapped[str] = mapped_column(String(40), index=True)
    hours_left: Mapped[int] = mapped_column(Integer)


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    line_id: Mapped[str] = mapped_column(String(40), index=True)
    rate: Mapped[int] = mapped_column(Integer)  # sản phẩm/giờ
    available: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------- Bài 03 ----------
class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    slots: Mapped[list] = mapped_column(JSON)  # nhãn từng ô, ví dụ ["09:00", ...]
    max_per_slot: Mapped[int] = mapped_column(Integer, default=1)
    gap: Mapped[int] = mapped_column(Integer, default=2)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(String(40), index=True)
    customer_id: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending")


class OptIn(Base):
    __tablename__ = "opt_ins"

    customer_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    opted_in: Mapped[bool] = mapped_column(Boolean)


# ---------- Bài 04 ----------
class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    system_id: Mapped[str] = mapped_column(String(40))
    service: Mapped[str] = mapped_column(String(80))
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20))


class ServiceGraph(Base):
    __tablename__ = "service_graphs"

    system_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[str] = mapped_column(String(20))
    nodes: Mapped[list] = mapped_column(JSON)
    edges: Mapped[list] = mapped_column(JSON)  # [[A, B], ...]: B phụ thuộc A
    customer_facing: Mapped[list] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

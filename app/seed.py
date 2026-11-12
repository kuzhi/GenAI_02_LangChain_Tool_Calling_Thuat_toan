from datetime import datetime

from sqlalchemy import select

from .models import (Batch, Campaign, Incident, Invoice, Machine, Message, OptIn, ServiceGraph, Shift, Transfer)

TZ = "+07:00"


def seed(session_factory) -> None:
    with session_factory() as db:
        if db.scalar(select(Invoice.id).limit(1)) is not None:
            return

        # Bài 01: I-77 là ca của đề; I-78 đã trả; I-79 không có cặp
        db.add_all([
            Invoice(id="I-77", customer_id="C-12", currency="VND", amount_due_minor=1_500_000, status="open"),
            Invoice(id="I-78", customer_id="C-12", currency="VND", amount_due_minor=500_000, status="paid"),
            Invoice(id="I-79", customer_id="C-20", currency="VND", amount_due_minor=1_000_000, status="open"),
        ])
        db.add_all([Transfer(id=i, received_at=f"2026-10-21T{t}:00{TZ}", customer_id=c, currency=cur,
                             amount_minor=a, status=s) for i, t, c, cur, a, s in [
            ("P1", "09:00", "C-12", "VND", 900_000, "unmatched"),
            ("P4", "09:02", "C-99", "VND", 600_000, "unmatched"),
            ("P5", "09:03", "C-12", "USD", 600_000, "unmatched"),
            ("P2", "09:05", "C-12", "VND", 600_000, "unmatched"),
            ("P3", "09:10", "C-12", "VND", 600_000, "unmatched"),
            ("P6", "09:15", "C-12", "VND", 600_000, "matched"),    # đã ghép: phải bị bỏ qua
            ("P7", "09:20", "C-20", "VND", 300_000, "unmatched"),  # I-79 chỉ có một giao dịch: no_match
        ]])

        # Bài 02: L1 là ca của đề (min rate 11 -> M2); L2 thiếu công suất; L3 không có lô
        db.add_all([Batch(id=f"B{i}", line_id="L1", quantity=q) for i, q in enumerate([30, 11, 23, 4], 1)])
        db.add(Batch(id="B5", line_id="L2", quantity=50))
        db.add_all([Shift(id="S1", line_id="L1", hours_left=8), Shift(id="S2", line_id="L2", hours_left=2),
                    Shift(id="S3", line_id="L3", hours_left=8)])
        db.add_all([Machine(id="M1", line_id="L1", rate=8), Machine(id="M2", line_id="L1", rate=12),
                    Machine(id="M3", line_id="L1", rate=16), Machine(id="M4", line_id="L1", rate=20, available=False),
                    Machine(id="M5", line_id="L2", rate=10)])

        # Bài 03: CMP-1 là ca của đề; CMP-2 có khách từ chối và hết ô
        hours = [f"{h:02d}:00" for h in range(9, 17)]
        db.add_all([Campaign(id="CMP-1", slots=hours, max_per_slot=1, gap=2),
                    Campaign(id="CMP-2", slots=hours[:3], max_per_slot=1, gap=2)])
        db.add_all([Message(id=m, campaign_id="CMP-1", customer_id=m[0]) for m in ["A1", "A2", "A3", "B1", "B2", "B3"]])
        db.add_all([Message(id="X1", campaign_id="CMP-2", customer_id="X"),
                    Message(id="X2", campaign_id="CMP-2", customer_id="X"),
                    Message(id="Y1", campaign_id="CMP-2", customer_id="Y")])
        db.add_all([OptIn(customer_id="A", opted_in=True), OptIn(customer_id="B", opted_in=True),
                    OptIn(customer_id="X", opted_in=True), OptIn(customer_id="Y", opted_in=False)])

        # Bài 04: INC-9 là ca của đề; INC-10 có sơ đồ thiếu node
        db.add_all([
            Incident(id="INC-9", system_id="SHOP", service="DB", occurred_at=datetime(2026, 10, 21, 2, 0), status="open"),
            Incident(id="INC-10", system_id="OLDSHOP", service="DB", occurred_at=datetime(2026, 10, 21, 3, 0), status="open"),
        ])
        db.add_all([
            ServiceGraph(system_id="SHOP", version="v7", updated_at=datetime(2026, 10, 20),
                         nodes=["DB", "Auth", "Reports", "Checkout", "MobileApp", "WebStore"],
                         edges=[["DB", "Auth"], ["DB", "Reports"], ["Auth", "Checkout"], ["Auth", "MobileApp"],
                                ["Checkout", "WebStore"]],
                         customer_facing=["Reports", "MobileApp", "WebStore"]),
            # Checkout xuất hiện trong cạnh nhưng không có trong nodes => dữ liệu thiếu
            ServiceGraph(system_id="OLDSHOP", version="v2", updated_at=datetime(2026, 10, 20),
                         nodes=["DB", "Auth", "WebStore"],
                         edges=[["DB", "Auth"], ["Auth", "Checkout"], ["Checkout", "WebStore"]],
                         customer_facing=["WebStore"]),
        ])
        db.commit()


from datetime import timedelta

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.orm import Session

from .algorithms.bfs import trace_impact as bfs_trace_impact
from .algorithms.binary_search import min_required_rate
from .algorithms.scheduler import build_schedule
from .algorithms.two_sum import find_two_transfer_match as two_sum_match
from .models import (Batch, Campaign, Incident, Invoice, Machine, Message, OptIn, Proposal, ServiceGraph, Shift,
                     Transfer)


class ToolError(Exception):
    """Lỗi nghiệp vụ của công cụ (không tìm thấy dữ liệu, dữ liệu không hợp lệ...)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _transfer_dict(t: Transfer) -> dict:
    return {"id": t.id, "received_at": t.received_at, "customer_id": t.customer_id, "currency": t.currency,
            "amount_minor": t.amount_minor, "status": t.status}


def _create_proposal(db: Session, ctx: dict, kind: str, payload: dict) -> dict:
    proposal = Proposal(chat_id=ctx.get("chat_id"), kind=kind, payload=payload, status="pending")
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    ctx.setdefault("proposals", []).append(proposal.id)
    return {"proposal_id": proposal.id, "kind": kind, "status": "pending", "payload": payload,
            "note": "Bản nháp chờ người có quyền duyệt; chưa thay đổi dữ liệu nào"}


# ======================================================================
# Bài 01 - đối soát hóa đơn
# ======================================================================
def get_open_invoice(db: Session, invoice_id: str) -> dict:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise ToolError("invoice_not_found", f"Không có hóa đơn {invoice_id}")
    if invoice.status != "open":
        raise ToolError("invoice_not_open", f"Hóa đơn {invoice_id} có trạng thái '{invoice.status}', không còn cần đối soát")
    return {"invoice_id": invoice.id, "customer_id": invoice.customer_id, "currency": invoice.currency,
            "amount_due_minor": invoice.amount_due_minor, "status": invoice.status}


def list_unmatched_transfers(db: Session, customer_id: str, currency: str) -> dict:
    rows = db.scalars(select(Transfer).where(Transfer.status == "unmatched", Transfer.customer_id == customer_id,
                                             Transfer.currency == currency)
                      .order_by(Transfer.received_at, Transfer.id)).all()
    return {"customer_id": customer_id, "currency": currency, "transfers": [_transfer_dict(t) for t in rows]}


def find_two_transfer_match(db: Session, invoice_id: str) -> dict:
    invoice = get_open_invoice(db, invoice_id)  # đọc lại hóa đơn từ backend
    transfers = [_transfer_dict(t) for t in db.scalars(select(Transfer)).all()]
    result = two_sum_match(transfers, invoice["customer_id"], invoice["currency"], invoice["amount_due_minor"])
    return {"invoice_id": invoice_id, "amount_due_minor": invoice["amount_due_minor"], **result}


def propose_invoice_match(db: Session, ctx: dict, invoice_id: str, transfer_ids: list[str]) -> dict:
    invoice = get_open_invoice(db, invoice_id)
    if len(set(transfer_ids)) != len(transfer_ids) or len(transfer_ids) != 2:
        raise ToolError("invalid_transfers", "Cần đúng hai mã giao dịch khác nhau")
    rows = [db.get(Transfer, tid) for tid in transfer_ids]
    if any(r is None for r in rows):
        raise ToolError("transfer_not_found", "Có mã giao dịch không tồn tại")
    for r in rows:
        if r.status != "unmatched" or r.customer_id != invoice["customer_id"] or r.currency != invoice["currency"]:
            raise ToolError("transfer_not_eligible", f"Giao dịch {r.id} đã ghép, hoặc sai khách/loại tiền")
    total = sum(r.amount_minor for r in rows)
    if total != invoice["amount_due_minor"]:
        raise ToolError("amount_mismatch", f"Tổng {total} khác số tiền còn thiếu {invoice['amount_due_minor']}")
    return _create_proposal(db, ctx, "invoice_match", {
        "invoice_id": invoice_id, "transfer_ids": transfer_ids, "total_minor": total, "currency": invoice["currency"]})


# ======================================================================
# Bài 02 - công suất sản xuất
# ======================================================================
def _check_line(db: Session, line_id: str) -> None:
    known = any(db.scalar(select(m.line_id).where(m.line_id == line_id).limit(1)) is not None
                for m in (Batch, Shift, Machine))
    if not known:
        raise ToolError("line_not_found", f"Không có dây chuyền {line_id}")


def get_open_batches(db: Session, line_id: str) -> dict:
    _check_line(db, line_id)
    rows = db.scalars(select(Batch).where(Batch.line_id == line_id, Batch.status == "open").order_by(Batch.id)).all()
    return {"line_id": line_id, "batches": [{"id": b.id, "quantity": b.quantity} for b in rows]}


def get_shift_hours(db: Session, line_id: str, shift_id: str) -> dict:
    shift = db.get(Shift, shift_id)
    if shift is None or shift.line_id != line_id:
        raise ToolError("shift_not_found", f"Không có ca {shift_id} của dây chuyền {line_id}")
    return {"line_id": line_id, "shift_id": shift_id, "hours_left": shift.hours_left}


def get_available_machines(db: Session, line_id: str) -> dict:
    _check_line(db, line_id)
    rows = db.scalars(select(Machine).where(Machine.line_id == line_id, Machine.available.is_(True))
                      .order_by(Machine.rate, Machine.id)).all()
    return {"line_id": line_id, "machines": [{"id": m.id, "rate": m.rate} for m in rows]}


def calculate_min_required_rate(db: Session, line_id: str, shift_id: str) -> dict:
    # Đọc lại tất cả từ database tại thời điểm tính (máy/lô có thể đã đổi sau khi AI đọc)
    batches = get_open_batches(db, line_id)["batches"]
    hours = get_shift_hours(db, line_id, shift_id)["hours_left"]
    machines = get_available_machines(db, line_id)["machines"]

    result = min_required_rate([b["quantity"] for b in batches], hours)
    out = {"line_id": line_id, "shift_id": shift_id, "hours_left": hours, "batch_count": len(batches), **result}
    if result["status"] == "ok":
        fit = [m for m in machines if m["rate"] >= result["min_rate"]]  # đã sắp tốc độ tăng dần
        if fit:
            out["recommended_machine"] = fit[0]  # máy chậm nhất vẫn đạt
            out["qualified_machines"] = fit
        else:
            out["status"] = "capacity_shortage"
            out["reason"] = f"Cần tối thiểu {result['min_rate']} sản phẩm/giờ nhưng không máy rảnh nào đủ nhanh"
    return out


def propose_machine_assignment(db: Session, ctx: dict, line_id: str, shift_id: str, machine_id: str) -> dict:
    calc = calculate_min_required_rate(db, line_id, shift_id)
    machine = db.get(Machine, machine_id)
    if machine is None or machine.line_id != line_id or not machine.available:
        raise ToolError("machine_not_available", f"Máy {machine_id} không rảnh hoặc không thuộc dây chuyền {line_id}")
    if calc["status"] not in ("ok", "no_batches") or machine.rate < calc.get("min_rate", 0):
        raise ToolError("machine_too_slow", f"Máy {machine_id} ({machine.rate}/giờ) không đạt yêu cầu: {calc.get('reason') or calc['status']}")
    return _create_proposal(db, ctx, "machine_assignment", {
        "line_id": line_id, "shift_id": shift_id, "machine_id": machine_id, "machine_rate": machine.rate,
        "min_rate": calc.get("min_rate")})


# ======================================================================
# Bài 03 - lịch gửi thông báo
# ======================================================================
def _campaign(db: Session, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise ToolError("campaign_not_found", f"Không có chiến dịch {campaign_id}")
    return campaign


def _pending(db: Session, campaign_id: str) -> list[Message]:
    return list(db.scalars(select(Message).where(Message.campaign_id == campaign_id, Message.status == "pending")
                           .order_by(Message.customer_id, Message.id)).all())


def get_pending_messages(db: Session, campaign_id: str) -> dict:
    _campaign(db, campaign_id)
    return {"campaign_id": campaign_id,
            "messages": [{"id": m.id, "customer_id": m.customer_id} for m in _pending(db, campaign_id)]}


def get_contact_policy(db: Session, campaign_id: str) -> dict:
    c = _campaign(db, campaign_id)
    return {"campaign_id": campaign_id, "slots": c.slots, "max_per_slot": c.max_per_slot, "gap": c.gap}


def get_opt_in_status(db: Session, customer_ids: list[str]) -> dict:
    found = {o.customer_id: o.opted_in for o in db.scalars(select(OptIn).where(OptIn.customer_id.in_(customer_ids)))}
    # Khách không có bản ghi coi là chưa đồng ý
    return {"statuses": {cid: bool(found.get(cid, False)) for cid in customer_ids},
            "unknown": [cid for cid in customer_ids if cid not in found]}


def build_send_schedule(db: Session, campaign_id: str) -> dict:
    campaign = _campaign(db, campaign_id)
    messages = _pending(db, campaign_id)
    customers = sorted({m.customer_id for m in messages})
    opt = get_opt_in_status(db, customers)["statuses"]  # kiểm tra lại quyền nhận tin ở backend

    grouped: dict[str, list[str]] = {}
    excluded = []
    for m in messages:
        if opt[m.customer_id]:
            grouped.setdefault(m.customer_id, []).append(m.id)
        else:
            excluded.append({"customer_id": m.customer_id, "message_id": m.id})
    result = build_schedule(grouped, list(campaign.slots), campaign.gap, campaign.max_per_slot)
    return {"campaign_id": campaign_id, **result, "excluded_no_opt_in": excluded,
            "note": "Đây là lịch đề xuất, chưa gửi tin nào"}


# ======================================================================
# Bài 04 - tác động sự cố
# ======================================================================
def get_incident(db: Session, incident_id: str) -> dict:
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise ToolError("incident_not_found", f"Không có sự cố {incident_id}")
    return {"incident_id": inc.id, "system_id": inc.system_id, "service": inc.service,
            "occurred_at": inc.occurred_at.isoformat(), "status": inc.status}


def _graph(db: Session, system_id: str) -> ServiceGraph:
    graph = db.get(ServiceGraph, system_id)
    if graph is None:
        raise ToolError("graph_not_found", f"Không có sơ đồ dịch vụ của hệ thống {system_id}")
    return graph


def get_service_graph(db: Session, system_id: str) -> dict:
    g = _graph(db, system_id)
    return {"system_id": system_id, "version": g.version, "nodes": g.nodes, "edges": g.edges,
            "updated_at": g.updated_at.isoformat()}


def get_customer_facing_services(db: Session, system_id: str) -> dict:
    return {"system_id": system_id, "services": sorted(_graph(db, system_id).customer_facing)}


def trace_impact(db: Session, incident_id: str) -> dict:
    inc = get_incident(db, incident_id)  # đọc lại sự cố và sơ đồ từ backend
    g = _graph(db, inc["system_id"])

    warnings = []
    nodes = set(g.nodes)
    edges = [(a, b) for a, b in g.edges]
    missing = sorted({n for e in edges for n in e if n not in nodes} | {n for n in g.customer_facing if n not in nodes})
    if inc["service"] not in nodes:
        missing = sorted(set(missing) | {inc["service"]})
    if missing:
        warnings.append(f"Sơ đồ thiếu node: {', '.join(missing)}")
    if g.updated_at < db.get(Incident, incident_id).occurred_at - timedelta(days=7):
        warnings.append(f"Sơ đồ {g.version} cập nhật lần cuối {g.updated_at.date()}, đã quá cũ so với thời điểm sự cố")

    impacts = bfs_trace_impact(edges, inc["service"], g.customer_facing)
    return {"incident_id": incident_id, "failed_service": inc["service"], "incident_status": inc["status"],
            "graph_version": g.version, "status": "incomplete_data" if warnings else "ok", "warnings": warnings,
            "possibly_affected": impacts,
            "note": "Đây là phần CÓ THỂ bị ảnh hưởng theo sơ đồ phụ thuộc, chưa xác nhận đã hỏng"}


# ======================================================================
# Bọc bằng LangChain @tool (docstring là mô tả model nhìn thấy)
# ======================================================================
def build_tools(db: Session, ctx: dict) -> list:
    @tool("get_open_invoice")
    def get_open_invoice_tool(invoice_id: str) -> dict:
        """Đọc hóa đơn chưa thanh toán: mã khách, loại tiền, số tiền còn thiếu (đơn vị nhỏ nhất), trạng thái."""
        return get_open_invoice(db, invoice_id)

    @tool("list_unmatched_transfers")
    def list_unmatched_transfers_tool(customer_id: str, currency: str) -> dict:
        """Liệt kê các khoản chuyển tiền chưa ghép hóa đơn của một khách theo loại tiền."""
        return list_unmatched_transfers(db, customer_id, currency)

    @tool("find_two_transfer_match")
    def find_two_transfer_match_tool(invoice_id: str) -> dict:
        """Chạy thuật toán tìm hai khoản chuyển tiền cộng lại đúng số tiền còn thiếu của hóa đơn."""
        return find_two_transfer_match(db, invoice_id)

    @tool("propose_invoice_match")
    def propose_invoice_match_tool(invoice_id: str, transfer_ids: list[str]) -> dict:
        """Tạo đề xuất đối soát (bản nháp chờ kế toán duyệt). Không ghi nhận hóa đơn đã thanh toán."""
        return propose_invoice_match(db, ctx, invoice_id, transfer_ids)

    @tool("get_open_batches")
    def get_open_batches_tool(line_id: str) -> dict:
        """Đọc các lô chưa làm và số sản phẩm từng lô của một dây chuyền."""
        return get_open_batches(db, line_id)

    @tool("get_shift_hours")
    def get_shift_hours_tool(line_id: str, shift_id: str) -> dict:
        """Đọc số giờ còn dùng được trong một ca."""
        return get_shift_hours(db, line_id, shift_id)

    @tool("get_available_machines")
    def get_available_machines_tool(line_id: str) -> dict:
        """Đọc các máy đang rảnh và tốc độ (sản phẩm/giờ) của dây chuyền."""
        return get_available_machines(db, line_id)

    @tool("calculate_min_required_rate")
    def calculate_min_required_rate_tool(line_id: str, shift_id: str) -> dict:
        """Tính (bằng code) tốc độ tối thiểu để xong các lô trong ca và máy chậm nhất vẫn đạt."""
        return calculate_min_required_rate(db, line_id, shift_id)

    @tool("propose_machine_assignment")
    def propose_machine_assignment_tool(line_id: str, shift_id: str, machine_id: str) -> dict:
        """Tạo đề xuất đặt máy (bản nháp chờ trưởng ca xác nhận). Không khóa máy."""
        return propose_machine_assignment(db, ctx, line_id, shift_id, machine_id)

    @tool("get_pending_messages")
    def get_pending_messages_tool(campaign_id: str) -> dict:
        """Đọc các tin đang chờ gửi của chiến dịch: mã tin và mã người nhận."""
        return get_pending_messages(db, campaign_id)

    @tool("get_contact_policy")
    def get_contact_policy_tool(campaign_id: str) -> dict:
        """Đọc quy tắc liên hệ: các khung giờ, số tin tối đa mỗi khung, số ô phải cách giữa hai tin cùng khách."""
        return get_contact_policy(db, campaign_id)

    @tool("get_opt_in_status")
    def get_opt_in_status_tool(customer_ids: list[str]) -> dict:
        """Cho biết khách nào đã đồng ý nhận tin."""
        return get_opt_in_status(db, customer_ids)

    @tool("build_send_schedule")
    def build_send_schedule_tool(campaign_id: str) -> dict:
        """Tạo lịch gửi đề xuất bằng thuật toán từ dữ liệu mới nhất. Không gửi tin thật."""
        return build_send_schedule(db, campaign_id)

    @tool("get_incident")
    def get_incident_tool(incident_id: str) -> dict:
        """Đọc sự cố: dịch vụ lỗi, thời điểm, trạng thái."""
        return get_incident(db, incident_id)

    @tool("get_service_graph")
    def get_service_graph_tool(system_id: str) -> dict:
        """Đọc quan hệ phụ thuộc giữa các dịch vụ (cạnh A→B: B phụ thuộc A) và phiên bản sơ đồ."""
        return get_service_graph(db, system_id)

    @tool("get_customer_facing_services")
    def get_customer_facing_services_tool(system_id: str) -> dict:
        """Đọc các dịch vụ người dùng trực tiếp nhìn thấy."""
        return get_customer_facing_services(db, system_id)

    @tool("trace_impact")
    def trace_impact_tool(incident_id: str) -> dict:
        """Chạy BFS từ dịch vụ lỗi, trả các dịch vụ có thể bị ảnh hưởng và đường đi ngắn nhất."""
        return trace_impact(db, incident_id)

    tools = [get_open_invoice_tool, list_unmatched_transfers_tool, find_two_transfer_match_tool,
             propose_invoice_match_tool, get_open_batches_tool, get_shift_hours_tool, get_available_machines_tool,
             calculate_min_required_rate_tool, propose_machine_assignment_tool, get_pending_messages_tool,
             get_contact_policy_tool, get_opt_in_status_tool, build_send_schedule_tool, get_incident_tool,
             get_service_graph_tool, get_customer_facing_services_tool, trace_impact_tool]
    return tools

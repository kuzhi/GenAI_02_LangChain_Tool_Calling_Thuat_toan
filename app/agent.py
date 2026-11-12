
import json
import re
import unicodedata
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .config import Settings
from .tools import ToolError

MAX_STEPS = 8  # số lần gọi model tối đa cho một câu hỏi

SYSTEM_PROMPT = """Bạn là trợ lý vận hành doanh nghiệp, trả lời bằng tiếng Việt, dữ liệu chỉ là dữ liệu giả để luyện tập.
- Bạn KHÔNG có số liệu sẵn. Phải gọi công cụ để đọc dữ liệu; không tự điền số liệu, không tính nhẩm thay công cụ thuật toán.
- Dùng đúng mã người dùng hỏi (hóa đơn, dây chuyền, ca, chiến dịch, sự cố). Thiếu mã thì hỏi lại, không đoán.
- Đọc dữ liệu trước, rồi gọi công cụ thuật toán (find_two_transfer_match, calculate_min_required_rate, build_send_schedule, trace_impact).
- Công cụ lỗi hoặc không có đáp án (no_match, impossible_under_rules, capacity_shortage, incomplete_data) thì nói rõ, không bịa kết quả.
- Bạn chỉ được TẠO ĐỀ XUẤT (propose_*) chờ người có quyền duyệt. Không ghi nhận thanh toán, không khóa máy, không gửi tin thật;
  nếu người dùng yêu cầu làm luôn, giải thích bạn chỉ tạo đề xuất/lịch đề xuất.
- Tiền là số nguyên đơn vị nhỏ nhất. Nói rõ dịch vụ trong bài sự cố chỉ là "có thể bị ảnh hưởng"."""


def fold(text: str) -> str:
    """Hạ chữ thường, bỏ dấu tiếng Việt."""
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").lower()


def money(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# ======================================================================
# Mock: giả lập model quyết định công cụ theo luật
# ======================================================================
class MockModel:
    is_paid = False

    def invoke(self, messages: list) -> AIMessage:
        last_human = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        question = messages[last_human].content
        done: dict[str, dict] = {}
        for m in messages[last_human + 1:]:
            if isinstance(m, ToolMessage):
                done[m.name] = json.loads(m.content)

        for name, result in done.items():
            if "error" in result:
                return AIMessage(content=f"Công cụ {name} báo lỗi: {result['error']['message']}. "
                                         "Tôi không thể tiếp tục mà không bịa số liệu; vui lòng kiểm tra lại mã đã nhập.")

        step = self._plan(question, done)
        if isinstance(step, str):
            return AIMessage(content=step)
        name, args = step
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{uuid4().hex[:8]}",
                                                  "type": "tool_call"}])

    # --- chọn công cụ kế tiếp hoặc trả câu cuối ---
    def _plan(self, q: str, done: dict):
        f = fold(q)
        if m := re.search(r"\bI-\d+\b", q, re.I):
            return self._invoice(m.group().upper(), f, done)
        if m := re.search(r"\bINC-\d+\b", q, re.I):
            return self._incident(m.group().upper(), done)
        if m := re.search(r"\bCMP-\d+\b", q, re.I):
            return self._campaign(m.group().upper(), f, done)
        line, shift = re.search(r"\bL\d+\b", q, re.I), re.search(r"\bS\d+\b", q, re.I)
        if line and shift:
            machine = re.search(r"\bM\d+\b", q, re.I)
            return self._production(line.group().upper(), shift.group().upper(), machine and machine.group().upper(), f, done)
        # Chưa đủ mã: hỏi lại, không đoán
        if re.search(r"hoa don|chuyen (tien|khoan)", f):
            return "Bạn muốn kiểm tra hóa đơn nào? Vui lòng cho mã hóa đơn (ví dụ I-77)."
        if re.search(r"\bmay\b|\bca\b|day chuyen|lo hang", f):
            return "Vui lòng cho biết mã dây chuyền và mã ca (ví dụ: dây chuyền L1, ca S1)."
        if re.search(r"thong bao|gui tin|chien dich", f):
            return "Bạn muốn xếp lịch cho chiến dịch nào? Vui lòng cho mã chiến dịch (ví dụ CMP-1)."
        if re.search(r"su co|hong|anh huong", f):
            return "Bạn hỏi về sự cố nào? Vui lòng cho mã sự cố (ví dụ INC-9)."
        return ("Tôi hỗ trợ 4 việc: đối soát hóa đơn (I-77), công suất ca (L1, S1), lịch gửi thông báo (CMP-1) "
                "và tác động sự cố (INC-9). Hãy hỏi kèm mã tương ứng.")

    def _invoice(self, invoice_id: str, f: str, done: dict):
        if "get_open_invoice" not in done:
            return "get_open_invoice", {"invoice_id": invoice_id}
        inv = done["get_open_invoice"]
        if "list_unmatched_transfers" not in done:
            return "list_unmatched_transfers", {"customer_id": inv["customer_id"], "currency": inv["currency"]}
        if "find_two_transfer_match" not in done:
            return "find_two_transfer_match", {"invoice_id": invoice_id}
        match = done["find_two_transfer_match"]
        if match["status"] == "matched" and "propose_invoice_match" not in done:
            return "propose_invoice_match", {"invoice_id": invoice_id, "transfer_ids": match["pair"]}

        head = f"Hóa đơn {invoice_id} (khách {inv['customer_id']}) còn thiếu {money(inv['amount_due_minor'])} {inv['currency']}."
        if match["status"] != "matched":
            return f"{head} Kết quả: no_match. {match['reason']}. Tôi không chọn cặp gần đúng."
        a, b = match["pair"]
        text = (f"{head} Đề xuất đối soát: {a} + {b} = {money(match['total_minor'])} {inv['currency']}. "
                f"Lý do: {match['reason']}. Đây chỉ là đề xuất #{done['propose_invoice_match']['proposal_id']} chờ kế toán duyệt, "
                "hóa đơn chưa được ghi nhận đã thanh toán.")
        if "ghi nhan" in f:
            text += " Tôi không tự ghi nhận được; cần người có quyền duyệt."
        return text

    def _production(self, line: str, shift: str, machine: str | None, f: str, done: dict):
        if "get_open_batches" not in done:
            return "get_open_batches", {"line_id": line}
        if "get_shift_hours" not in done:
            return "get_shift_hours", {"line_id": line, "shift_id": shift}
        if "get_available_machines" not in done:
            return "get_available_machines", {"line_id": line}
        if "calculate_min_required_rate" not in done:
            return "calculate_min_required_rate", {"line_id": line, "shift_id": shift}
        calc = done["calculate_min_required_rate"]
        want_assign = machine is not None and ("dat" in f or "chon" in f)
        if want_assign and calc["status"] == "ok" and "propose_machine_assignment" not in done:
            return "propose_machine_assignment", {"line_id": line, "shift_id": shift, "machine_id": machine}

        head = f"Dây chuyền {line}, ca {shift}: còn {calc['hours_left']} giờ."
        if calc["status"] == "no_batches":
            return f"{head} Không có lô nào cần xử lý."
        if calc["status"] == "impossible_under_rules":
            return f"{head} impossible_under_rules: {calc['reason']}."
        steps = " + ".join(str(b["hours"]) for b in calc["per_batch_hours"])
        text = (f"{head} Tốc độ tối thiểu: {calc['min_rate']} sản phẩm/giờ (các lô {[b['quantity'] for b in calc['per_batch_hours']]} "
                f"cần {steps} = {calc['hours_needed']} giờ).")
        if calc["status"] == "capacity_shortage":
            return f"{text} Thiếu công suất: {calc['reason']}. Ca chưa khả thi."
        text += f" Máy đề xuất: {calc['recommended_machine']['id']} ({calc['recommended_machine']['rate']}/giờ), máy chậm nhất vẫn đạt."
        if "propose_machine_assignment" in done:
            text += f" Đã tạo đề xuất #{done['propose_machine_assignment']['proposal_id']} chờ trưởng ca xác nhận, chưa khóa máy."
        elif want_assign:
            text += " Máy bạn chọn không đạt yêu cầu nên không tạo đề xuất."
        return text

    def _campaign(self, campaign: str, f: str, done: dict):
        if "get_pending_messages" not in done:
            return "get_pending_messages", {"campaign_id": campaign}
        if "get_contact_policy" not in done:
            return "get_contact_policy", {"campaign_id": campaign}
        if "get_opt_in_status" not in done:
            ids = sorted({m["customer_id"] for m in done["get_pending_messages"]["messages"]})
            return "get_opt_in_status", {"customer_ids": ids}
        if "build_send_schedule" not in done:
            return "build_send_schedule", {"campaign_id": campaign}
        s = done["build_send_schedule"]
        cells = [f"{x['time']}: " + (", ".join(m["message_id"] for m in x["sent"]) if x["sent"] else "idle")
                 for x in s["schedule"]]
        text = f"Lịch ĐỀ XUẤT cho {campaign} (gap={s['gap']}, chưa gửi tin nào): " + "; ".join(cells) + "."
        if s["excluded_no_opt_in"]:
            text += " Đã loại tin của khách chưa đồng ý nhận: " + ", ".join(m["message_id"] for m in s["excluded_no_opt_in"]) + "."
        if s["unscheduled"]:
            text += " Hết khung giờ, chưa xếp được: " + ", ".join(m["message_id"] for m in s["unscheduled"]) + " (không tự đẩy sang ngày khác)."
        if re.search(r"gui ngay|gui luon", f):
            text += " Tôi không gửi tin thật; cần người có quyền duyệt."
        return text

    def _incident(self, incident: str, done: dict):
        if "get_incident" not in done:
            return "get_incident", {"incident_id": incident}
        inc = done["get_incident"]
        if "get_service_graph" not in done:
            return "get_service_graph", {"system_id": inc["system_id"]}
        if "get_customer_facing_services" not in done:
            return "get_customer_facing_services", {"system_id": inc["system_id"]}
        if "trace_impact" not in done:
            return "trace_impact", {"incident_id": incident}
        t = done["trace_impact"]
        text = f"Sự cố {incident} tại {t['failed_service']} (sơ đồ {t['graph_version']}). Các dịch vụ CÓ THỂ bị ảnh hưởng theo sơ đồ phụ thuộc (chưa xác nhận đã hỏng): "
        text += "; ".join(f"{' → '.join(i['path'])} ({i['edges']} cạnh)" for i in t["possibly_affected"]) or "không có"
        text += "."
        if t["status"] == "incomplete_data":
            text += " CẢNH BÁO incomplete_data: " + "; ".join(t["warnings"]) + ". Danh sách trên có thể chưa đầy đủ."
        return text


# ======================================================================
# Model thật
# ======================================================================
def build_model(settings: Settings, tools: list):
    if settings.ai_mode != "openai":
        return MockModel()
    if not settings.openai_api_key:
        raise ToolError("no_api_key", "Chưa cấu hình OPENAI_API_KEY ở backend (hoặc đặt AI_MODE=mock)")
    from langchain_openai import ChatOpenAI
    model = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, timeout=60, max_retries=1)
    return model.bind_tools(tools)


# ======================================================================
# Vòng lặp Tool Calling
# ======================================================================
def run_agent(question: str, model, tools: list, max_steps: int = MAX_STEPS) -> dict:
    registry = {t.name: t for t in tools}  # chỉ công cụ trong danh sách này được chạy
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=question)]
    log: list[dict] = []

    for _ in range(max_steps):
        ai = model.invoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            return {"answer": ai.content if isinstance(ai.content, str) else str(ai.content), "tool_calls": log}

        for call in ai.tool_calls:
            entry = {"step": len(log) + 1, "id": call["id"], "name": call["name"], "args": call["args"]}
            tool = registry.get(call["name"])
            if tool is None:
                entry["error"] = {"code": "unknown_tool", "message": f"Công cụ '{call['name']}' không có trong danh sách"}
            elif set(call["args"]) - set(tool.args):
                entry["error"] = {"code": "bad_arguments",
                                  "message": f"Tham số lạ: {sorted(set(call['args']) - set(tool.args))}"}
            else:
                try:
                    entry["result"] = tool.invoke(call["args"])
                except ToolError as exc:
                    entry["error"] = {"code": exc.code, "message": exc.message}
                except Exception as exc:  # tham số sai kiểu, lỗi database...
                    entry["error"] = {"code": "tool_failed", "message": f"{type(exc).__name__}: {str(exc)[:300]}"}
            log.append(entry)
            payload = {"error": entry["error"]} if "error" in entry else entry["result"]
            messages.append(ToolMessage(content=json.dumps(payload, ensure_ascii=False, default=str),
                                        tool_call_id=call["id"], name=call["name"]))

    return {"answer": f"Đã vượt giới hạn {max_steps} bước gọi công cụ nên dừng, chưa có câu trả lời cuối.",
            "tool_calls": log, "truncated": True}

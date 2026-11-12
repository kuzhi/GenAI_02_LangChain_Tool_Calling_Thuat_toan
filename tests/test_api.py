"""Test luồng chat đầu-cuối (mock model + Supabase schema test) và an toàn của vòng lặp Tool Calling."""
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage

from app.models import Incident, Invoice, Machine, Proposal, ServiceGraph, Transfer


def ask(client, text):
    r = client.post("/api/chat", json={"message": text})
    assert r.status_code == 200, r.text
    return r.json()


def names(body):
    return [c["name"] for c in body["tool_calls"]]


# ---------- Bài 01 ----------
def test_invoice_sample_flow(client):
    body = ask(client, "Kiểm tra hóa đơn I-77")
    assert names(body) == ["get_open_invoice", "list_unmatched_transfers", "find_two_transfer_match",
                           "propose_invoice_match"]
    assert body["tool_calls"][2]["result"]["pair"] == ["P1", "P2"]
    assert "P1 + P2" in body["answer"] and "chờ kế toán duyệt" in body["answer"]
    assert body["proposals"][0]["status"] == "pending" and body["proposals"][0]["payload"]["transfer_ids"] == ["P1", "P2"]


def test_invoice_record_is_not_changed_and_record_replayable(client):
    body = ask(client, "Kiểm tra hóa đơn I-77 và hãy ghi nhận luôn")
    assert "chờ" in body["answer"] and "không tự ghi nhận" in body["answer"]
    with client.app.state.session_factory() as db:
        assert db.get(Invoice, "I-77").status == "open"
        assert db.get(Transfer, "P1").status == "unmatched"
    again = client.get(f"/api/chats/{body['chat_id']}").json()
    assert again["answer"] == body["answer"] and again["tool_calls"] == body["tool_calls"]
    assert client.get("/api/chats").json()[0]["chat_id"] == body["chat_id"]


def test_invoice_errors(client):
    assert "không có hóa đơn" in ask(client, "Kiểm tra hóa đơn I-999")["answer"].lower()
    assert ask(client, "Kiểm tra hóa đơn I-78")["tool_calls"][0]["error"]["code"] == "invoice_not_open"
    no_match = ask(client, "Kiểm tra hóa đơn I-79")
    assert no_match["tool_calls"][2]["result"]["status"] == "no_match" and no_match["proposals"] == []
    assert "no_match" in no_match["answer"]


def test_invoice_missing_id_asks_back(client):
    body = ask(client, "Kiểm tra hóa đơn giúp tôi")
    assert body["tool_calls"] == [] and "mã hóa đơn" in body["answer"]


def test_match_reads_fresh_data_after_change(client):
    with client.app.state.session_factory() as db:
        db.get(Transfer, "P2").status = "matched"  # P2 đã bị ghép sau khi hệ thống nạp dữ liệu
        db.commit()
    body = ask(client, "Kiểm tra hóa đơn I-77")
    assert body["tool_calls"][2]["result"]["pair"] == ["P1", "P3"]


# ---------- Bài 02 ----------
def test_production_sample(client):
    body = ask(client, "Với dây chuyền L1, ca S1, máy nào xử lý xong trước khi hết ca?")
    calc = body["tool_calls"][3]["result"]
    assert calc["min_rate"] == 11 and calc["recommended_machine"]["id"] == "M2"
    assert "11" in body["answer"] and "M2" in body["answer"] and body["proposals"] == []


def test_production_assign_creates_proposal_only(client):
    body = ask(client, "Dây chuyền L1 ca S1, hãy đặt máy M2")
    assert body["proposals"][0]["kind"] == "machine_assignment" and body["proposals"][0]["status"] == "pending"
    with client.app.state.session_factory() as db:
        assert db.get(Machine, "M2").available is True  # không khóa máy


def test_production_too_slow_machine_rejected(client):
    body = ask(client, "Dây chuyền L1 ca S1, hãy đặt máy M1")
    assert body["proposals"] == [] and body["tool_calls"][-1]["error"]["code"] == "machine_too_slow"


def test_production_edge_cases(client):
    assert "thiếu công suất" in ask(client, "Dây chuyền L2 ca S2 có kịp không?")["answer"].lower()
    assert "không có lô" in ask(client, "Dây chuyền L3 ca S3 thế nào?")["answer"].lower()
    assert ask(client, "Dây chuyền L1 ca S9")["tool_calls"][1]["error"]["code"] == "shift_not_found"
    assert "mã dây chuyền và mã ca" in ask(client, "Máy nào kịp ca?")["answer"]


def test_production_zero_hours_and_machine_changed(client):
    with client.app.state.session_factory() as db:
        from app.models import Shift
        db.get(Shift, "S1").hours_left = 3  # ít hơn 4 lô
        db.commit()
    assert "impossible_under_rules" in ask(client, "Dây chuyền L1 ca S1")["answer"]
    with client.app.state.session_factory() as db:
        db.get(Shift, "S1").hours_left = 8
        db.get(Machine, "M2").available = False  # máy đổi sau khi AI đọc: tính lại từ database
        db.commit()
    assert ask(client, "Dây chuyền L1 ca S1")["tool_calls"][3]["result"]["recommended_machine"]["id"] == "M3"


# ---------- Bài 03 ----------
def test_schedule_sample(client):
    body = ask(client, "Hôm nay nên xếp các tin của chiến dịch CMP-1 vào khung giờ nào?")
    grid = [x["sent"][0]["message_id"] if x["sent"] else "idle" for x in body["tool_calls"][3]["result"]["schedule"]]
    assert grid == ["A1", "B1", "idle", "A2", "B2", "idle", "A3", "B3"]
    assert "ĐỀ XUẤT" in body["answer"] and "chưa gửi" in body["answer"]


def test_schedule_opt_out_and_out_of_slots(client):
    body = ask(client, "Chiến dịch CMP-2 gửi ngay đi")
    result = body["tool_calls"][3]["result"]
    assert result["excluded_no_opt_in"] == [{"customer_id": "Y", "message_id": "Y1"}]
    assert result["unscheduled"] == [{"customer_id": "X", "message_id": "X2"}]
    assert "không gửi tin thật" in body["answer"] and "chưa xếp được" in body["answer"]


def test_schedule_unknown_campaign(client):
    assert ask(client, "Lịch chiến dịch CMP-99")["tool_calls"][0]["error"]["code"] == "campaign_not_found"


# ---------- Bài 04 ----------
def test_incident_sample(client):
    body = ask(client, "Sự cố INC-9 ảnh hưởng đến đâu?")
    impact = body["tool_calls"][3]["result"]
    assert [(i["service"], i["edges"]) for i in impact["possibly_affected"]] == [
        ("Reports", 1), ("MobileApp", 2), ("WebStore", 3)]
    assert "CÓ THỂ" in body["answer"] and "DB → Auth → Checkout → WebStore" in body["answer"]


def test_incident_missing_node_gives_incomplete_data(client):
    body = ask(client, "Sự cố INC-10 ảnh hưởng đến đâu?")
    assert body["tool_calls"][3]["result"]["status"] == "incomplete_data" and "incomplete_data" in body["answer"]


def test_incident_stale_graph_and_unknown_incident(client):
    with client.app.state.session_factory() as db:
        db.get(ServiceGraph, "SHOP").updated_at = db.get(Incident, "INC-9").occurred_at - timedelta(days=30)
        db.commit()
    assert ask(client, "Sự cố INC-9")["tool_calls"][3]["result"]["status"] == "incomplete_data"
    assert ask(client, "Sự cố INC-404")["tool_calls"][0]["error"]["code"] == "incident_not_found"


# ---------- An toàn của vòng lặp ----------
def scripted(*calls):
    """Model giả: lần lượt gọi các tool_calls cho sẵn rồi trả câu cuối."""
    def factory(settings, tools):
        class Fake:
            n = 0

            def invoke(self, messages):
                if Fake.n < len(calls):
                    name, args = calls[Fake.n]
                    Fake.n += 1
                    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{Fake.n}", "type": "tool_call"}])
                return AIMessage(content="xong")
        return Fake()
    return factory


def test_unknown_tool_and_extra_args_are_rejected(client_factory):
    c = client_factory(scripted(("run_sql", {"query": "DROP TABLE invoices"}),
                                ("get_open_invoice", {"invoice_id": "I-77", "url": "http://x"}),
                                ("get_open_invoice", {"invoice_id": ["bad"]})))
    body = ask(c, "bất kỳ")
    assert [t["error"]["code"] for t in body["tool_calls"]] == ["unknown_tool", "bad_arguments", "tool_failed"]
    assert body["answer"] == "xong"


def test_model_cannot_supply_amounts_to_algorithm(client_factory):
    c = client_factory(scripted(("find_two_transfer_match", {"invoice_id": "I-77", "amounts": [1, 2]})))
    assert ask(c, "x")["tool_calls"][0]["error"]["code"] == "bad_arguments"


def test_step_limit_stops_endless_tool_calls(client_factory):
    c = client_factory(scripted(*[("get_open_invoice", {"invoice_id": "I-77"})] * 50))
    body = ask(c, "x")
    assert len(body["tool_calls"]) == 8 and body["status"] == "failed" and "giới hạn" in body["answer"]


def test_model_exception_is_recorded(client_factory):
    def boom(settings, tools):
        raise RuntimeError("secret internal detail")
    body = ask(client_factory(boom), "x")
    assert body["status"] == "failed" and "secret" not in body["error"]


def test_openai_mode_without_key_fails_cleanly(client_factory):
    body = ask(client_factory(ai_mode="openai"), "Kiểm tra hóa đơn I-77")
    assert body["status"] == "failed" and "OPENAI_API_KEY" in body["error"]


# ---------- Duyệt đề xuất ----------
def test_review_proposal(client):
    pid = ask(client, "Kiểm tra hóa đơn I-77")["proposals"][0]["id"]
    assert client.post(f"/api/proposals/{pid}/review", json={"decision": "approved"}).json()["status"] == "approved"
    assert client.post(f"/api/proposals/{pid}/review", json={"decision": "rejected"}).status_code == 409
    assert client.post("/api/proposals/9999/review", json={"decision": "approved"}).status_code == 404
    with client.app.state.session_factory() as db:
        assert db.get(Invoice, "I-77").status == "open"  # duyệt đề xuất cũng không đổi sổ sách trong bài này


def test_chat_validation(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.get("/api/chats/9999").status_code == 404

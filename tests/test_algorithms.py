import pytest

from app.algorithms.bfs import trace_impact
from app.algorithms.binary_search import hours_needed, min_required_rate
from app.algorithms.scheduler import build_schedule
from app.algorithms.two_sum import find_two_transfer_match


# ---------- Bài 01: two sum ----------
def T(i, time, cust="C-12", cur="VND", amt=600_000, status="unmatched"):
    return {"id": i, "received_at": f"2026-10-21T{time}:00+07:00", "customer_id": cust, "currency": cur,
            "amount_minor": amt, "status": status}


SAMPLE_TRANSFERS = [T("P1", "09:00", amt=900_000), T("P4", "09:02", cust="C-99"), T("P5", "09:03", cur="USD"),
                    T("P2", "09:05"), T("P3", "09:10")]


def test_two_sum_sample_picks_p1_p2():
    r = find_two_transfer_match(SAMPLE_TRANSFERS, "C-12", "VND", 1_500_000)
    assert r["status"] == "matched" and r["pair"] == ["P1", "P2"]


def test_two_sum_order_independent_of_input_order():
    r = find_two_transfer_match(list(reversed(SAMPLE_TRANSFERS)), "C-12", "VND", 1_500_000)
    assert r["pair"] == ["P1", "P2"]


def test_two_sum_no_pair_does_not_pick_approximate():
    r = find_two_transfer_match(SAMPLE_TRANSFERS, "C-12", "VND", 1_400_000)
    assert r["status"] == "no_match" and "pair" not in r


def test_two_sum_equal_amounts_and_no_self_match():
    # 750k + 750k = 1.5M cần hai giao dịch khác nhau; một giao dịch không ghép với chính nó
    assert find_two_transfer_match([T("A", "09:00", amt=750_000)], "C-12", "VND", 1_500_000)["status"] == "no_match"
    r = find_two_transfer_match([T("A", "09:00", amt=750_000), T("B", "09:01", amt=750_000)], "C-12", "VND", 1_500_000)
    assert r["pair"] == ["A", "B"]


def test_two_sum_ignores_matched_and_non_positive():
    rows = [T("A", "09:00", amt=900_000, status="matched"), T("B", "09:01", amt=600_000), T("C", "09:02", amt=-100),
            T("D", "09:03", amt=0)]
    assert find_two_transfer_match(rows, "C-12", "VND", 1_500_000)["status"] == "no_match"


def test_two_sum_empty_and_bad_target():
    assert find_two_transfer_match([], "C-12", "VND", 100)["status"] == "no_match"
    assert find_two_transfer_match(SAMPLE_TRANSFERS, "C-12", "VND", 0)["status"] == "no_match"


# ---------- Bài 02: binary search ----------
def test_rate_sample_is_11():
    r = min_required_rate([30, 11, 23, 4], 8)
    assert r["status"] == "ok" and r["min_rate"] == 11 and r["hours_needed"] == 8
    assert hours_needed([30, 11, 23, 4], 10) == 9  # ở tốc độ 10 cần 9 giờ


def test_rate_exact_deadline_and_single_batch():
    assert min_required_rate([10], 1)["min_rate"] == 10
    assert min_required_rate([10], 10)["min_rate"] == 1


def test_rate_no_batches_and_zero_quantity_batches():
    assert min_required_rate([], 8)["status"] == "no_batches"
    assert min_required_rate([0, 0], 8)["status"] == "no_batches"
    assert min_required_rate([0, 10], 1)["min_rate"] == 10  # lô 0 sản phẩm không chiếm giờ


def test_rate_zero_hours_and_too_few_hours():
    assert min_required_rate([5], 0)["status"] == "impossible_under_rules"
    assert min_required_rate([5, 5, 5], 2)["status"] == "impossible_under_rules"
    assert min_required_rate([], 0)["status"] == "no_batches"


def test_rate_negative_input_rejected():
    with pytest.raises(ValueError):
        min_required_rate([-1], 5)
    with pytest.raises(ValueError):
        min_required_rate([5], -1)


def test_rate_matches_brute_force():
    import random
    rng = random.Random(1)
    for _ in range(200):
        qs = [rng.randint(1, 60) for _ in range(rng.randint(1, 5))]
        hours = rng.randint(len(qs), 30)
        expected = next(r for r in range(1, 200) if hours_needed(qs, r) <= hours)
        assert min_required_rate(qs, hours)["min_rate"] == expected


# ---------- Bài 03: scheduler ----------
SLOTS = [f"{h:02d}:00" for h in range(9, 17)]


def grid(result):
    return [x["sent"][0]["message_id"] if x["sent"] else "idle" for x in result["schedule"]]


def test_schedule_sample():
    r = build_schedule({"A": ["A1", "A2", "A3"], "B": ["B1", "B2", "B3"]}, SLOTS, gap=2)
    assert grid(r) == ["A1", "B1", "idle", "A2", "B2", "idle", "A3", "B3"]
    assert r["status"] == "complete" and r["unscheduled"] == []


def test_schedule_single_customer_leaves_idle_and_reports_unscheduled():
    r = build_schedule({"A": ["A1", "A2", "A3"]}, SLOTS[:5], gap=2)
    assert grid(r) == ["A1", "idle", "idle", "A2", "idle"]
    assert r["status"] == "partial" and r["unscheduled"] == [{"customer_id": "A", "message_id": "A3"}]


def test_schedule_gap_zero_sends_every_slot():
    r = build_schedule({"A": ["A1", "A2", "A3"]}, SLOTS, gap=0)
    assert grid(r)[:3] == ["A1", "A2", "A3"]


def test_schedule_tie_breaks_alphabetically_and_input_order_ignored():
    r = build_schedule({"B": ["B2", "B1"], "A": ["A1"]}, SLOTS, gap=0)
    assert grid(r)[:3] == ["B1", "A1", "B2"]  # B còn nhiều tin hơn nên ra trước; B1 trước B2


def test_schedule_empty_and_invalid_gap():
    assert build_schedule({}, SLOTS, 2)["status"] == "complete"
    with pytest.raises(ValueError):
        build_schedule({"A": ["A1"]}, SLOTS, -1)


def test_schedule_respects_gap_for_many_customers():
    msgs = {c: [f"{c}{i}" for i in range(1, 4)] for c in "ABCD"}
    r = build_schedule(msgs, [str(i) for i in range(20)], gap=2)
    last = {}
    for x in r["schedule"]:
        for m in x["sent"]:
            c = m["customer_id"]
            assert c not in last or x["slot"] - last[c] >= 3
            last[c] = x["slot"]
    assert r["unscheduled"] == []


# ---------- Bài 04: BFS ----------
SHOP = [("DB", "Auth"), ("DB", "Reports"), ("Auth", "Checkout"), ("Auth", "MobileApp"), ("Checkout", "WebStore")]


def test_bfs_sample():
    r = trace_impact(SHOP, "DB", ["Reports", "MobileApp", "WebStore"])
    assert [(i["service"], i["edges"]) for i in r] == [("Reports", 1), ("MobileApp", 2), ("WebStore", 3)]
    assert r[2]["path"] == ["DB", "Auth", "Checkout", "WebStore"]


def test_bfs_duplicate_edges_and_cycle_terminate():
    r = trace_impact(SHOP + SHOP + [("WebStore", "DB"), ("Checkout", "Auth")], "DB", ["WebStore"])
    assert r[0]["edges"] == 3


def test_bfs_unreachable_service_excluded():
    r = trace_impact(SHOP + [("Other", "Isolated")], "DB", ["Reports", "Isolated"])
    assert [i["service"] for i in r] == ["Reports"]


def test_bfs_shortest_path_and_alphabetical_tie():
    edges = [("S", "A"), ("A", "T"), ("S", "B"), ("B", "C"), ("C", "T"), ("S", "Z"), ("S", "Y")]
    r = trace_impact(edges, "S", ["T", "Z", "Y"])
    assert [(i["service"], i["edges"]) for i in r] == [("Y", 1), ("Z", 1), ("T", 2)]


def test_bfs_failed_service_not_in_graph():
    assert trace_impact(SHOP, "Ghost", ["WebStore"]) == []

import heapq
from collections import deque


def build_schedule(messages_by_customer: dict[str, list[str]], slots: list[str], gap: int,
                   max_per_slot: int = 1) -> dict:
    if gap < 0 or max_per_slot < 1:
        raise ValueError("gap phải >= 0 và max_per_slot phải >= 1")
    remaining = {c: deque(sorted(ids)) for c, ids in messages_by_customer.items() if ids}
    heap = [(-len(q), c) for c, q in remaining.items()]  # khách còn nhiều tin nhất ra trước, hòa thì mã khách
    heapq.heapify(heap)
    waiting: deque[tuple[int, str]] = deque()  # (ô sớm nhất được gửi tiếp, khách); thứ tự ô tăng dần

    schedule = []
    for i, label in enumerate(slots):
        while waiting and waiting[0][0] <= i:
            _, c = waiting.popleft()
            heapq.heappush(heap, (-len(remaining[c]), c))
        sent = []
        for _ in range(max_per_slot):
            if not heap:
                break
            _, c = heapq.heappop(heap)
            sent.append({"customer_id": c, "message_id": remaining[c].popleft()})
            if remaining[c]:
                waiting.append((i + gap + 1, c))
        schedule.append({"slot": i, "time": label, "idle": not sent, "sent": sent})

    unscheduled = [{"customer_id": c, "message_id": m} for c, q in sorted(remaining.items()) for m in q]
    return {"status": "partial" if unscheduled else "complete", "gap": gap, "schedule": schedule,
            "unscheduled": unscheduled}

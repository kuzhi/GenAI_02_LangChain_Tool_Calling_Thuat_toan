

def hours_needed(quantities: list[int], rate: int) -> int:
    return sum(-(-q // rate) for q in quantities)


def min_required_rate(quantities: list[int], hours_left: int) -> dict:
    if any(q < 0 for q in quantities):
        raise ValueError("Số lượng của lô không được âm")
    if hours_left < 0:
        raise ValueError("Số giờ còn lại không được âm")
    quantities = [q for q in quantities if q > 0]  # lô 0 sản phẩm không chiếm giờ
    if not quantities:
        return {"status": "no_batches", "min_rate": 0, "reason": "Không có lô nào còn sản phẩm cần xử lý"}
    if hours_left < len(quantities):
        return {"status": "impossible_under_rules", "min_rate": None,
                "reason": f"Còn {hours_left} giờ nhưng có {len(quantities)} lô, mỗi lô cần ít nhất 1 giờ"}

    lo, hi = 1, max(quantities)  # ở tốc độ max(q) mỗi lô đúng 1 giờ nên luôn kịp
    while lo < hi:
        mid = (lo + hi) // 2
        if hours_needed(quantities, mid) <= hours_left:
            hi = mid
        else:
            lo = mid + 1
    return {"status": "ok", "min_rate": lo, "hours_needed": hours_needed(quantities, lo),
            "hours_left": hours_left,
            "per_batch_hours": [{"quantity": q, "hours": -(-q // lo)} for q in quantities]}

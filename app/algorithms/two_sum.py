from datetime import datetime


def find_two_transfer_match(transfers: list[dict], customer_id: str, currency: str, amount_due_minor: int) -> dict:
 
    if amount_due_minor <= 0:
        return {"status": "no_match", "reason": "Số tiền còn thiếu không dương nên không có gì để đối soát"}

    # Chỉ xét giao dịch chưa ghép, đúng khách, đúng loại tiền, số tiền dương; sắp ổn định
    eligible = [t for t in transfers
                if t["status"] == "unmatched" and t["customer_id"] == customer_id
                and t["currency"] == currency and t["amount_minor"] > 0]
    # parse để đúng thứ tự cả khi các giao dịch khác múi giờ
    eligible.sort(key=lambda t: (datetime.fromisoformat(t["received_at"]), t["id"]))

    seen: dict[int, dict] = {}  # số tiền -> giao dịch đầu tiên có số tiền đó
    for t in eligible:
        partner = seen.get(amount_due_minor - t["amount_minor"])  # kiểm tra trước khi thêm => không ghép với chính nó
        if partner is not None:
            return {"status": "matched", "pair": [partner["id"], t["id"]],
                    "amounts_minor": [partner["amount_minor"], t["amount_minor"]],
                    "total_minor": partner["amount_minor"] + t["amount_minor"],
                    "currency": currency, "eligible_count": len(eligible),
                    "reason": f"{partner['id']} + {t['id']} = {amount_due_minor} {currency}; "
                              "cặp xuất hiện sớm nhất theo thứ tự quét (giờ nhận, rồi mã giao dịch)"}
        seen.setdefault(t["amount_minor"], t)
    return {"status": "no_match", "eligible_count": len(eligible),
            "reason": f"Không có hai giao dịch hợp lệ nào cộng lại đúng {amount_due_minor} {currency}"}

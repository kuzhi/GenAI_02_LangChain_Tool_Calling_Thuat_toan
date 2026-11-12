Học viên: Trần Anh Khoa, Nguyễn Anh Thi, Phạm Đức Cường, Nguyễn Thành Được, Nguyễn Phúc Thanh

Những bài tập được thực hiện bởi:
bài tập 1 -Nguyễn Anh Thi, Nguyễn Phúc Thanh
bài tập 2 -Phạm Đức Cường
bài tập 3 -Trần Anh Khoa
bài tập 4 -Nguyễn Thành Được

# LangChain Tool Calling × Thuật toán — Backend

Một app FastAPI chứa cả 4 bài. Người dùng hỏi bằng tiếng Việt qua `POST /api/chat`; AI chọn công cụ, backend kiểm tra rồi chạy công cụ, thuật toán nằm trong Python và test được mà không cần model. Giao diện là Swagger.

## Chạy

```bash
python -m venv myenv
myenv\Scripts\activate            # Windows
pip install -r requirements.txt
# tạo .env (xem .env.example): DATABASE_URL là chuỗi Supabase, AI_MODE=mock hoặc openai
uvicorn app.main:app --reload --port 8000
```

Swagger: http://localhost:8000/docs. Bảng và dữ liệu mẫu được tạo tự động khi app khởi động (chỉ khi bảng còn trống).

| Biến `.env` | Ý nghĩa |
|---|---|
| `AI_MODE` | `mock` (mặc định): model giả bằng luật cục bộ, không cần API key nhưng vẫn đi qua đúng vòng lặp tool calling. `openai`: `ChatOpenAI.bind_tools` thật. |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Chỉ cần khi `AI_MODE=openai`; key chỉ nằm ở backend. |
| `AI_MAX_REQUESTS_PER_HOUR` | Giới hạn số câu hỏi gọi model trả phí mỗi giờ (vượt thì HTTP 429). |
| `DATABASE_URL` | Chuỗi kết nối Supabase/PostgreSQL (`postgresql+psycopg://...`). |

## API

| API | Việc |
|---|---|
| `POST /api/chat` `{"message": "..."}` | Hỏi; trả `answer`, `data_used` (dữ liệu công cụ trả về), `tool_calls` (tên, tham số, kết quả hoặc lỗi), `proposals` |
| `GET /api/chats`, `GET /api/chats/{id}` | Xem lại lịch sử câu hỏi, các lần gọi công cụ và câu trả lời |
| `GET /api/proposals`, `POST /api/proposals/{id}/review` | Xem / duyệt đề xuất (chỉ đổi trạng thái đề xuất, không đụng hóa đơn, máy, lịch) |
| `GET /api/samples` | Danh sách câu hỏi mẫu để dán vào Swagger |

## Câu hỏi mẫu và kết quả đúng

| Câu hỏi | Công cụ AI gọi | Kết quả |
|---|---|---|
| `Kiểm tra hóa đơn I-77` | get_open_invoice → list_unmatched_transfers → find_two_transfer_match → propose_invoice_match | P1 + P2 = 1.500.000 VND (đề xuất chờ duyệt) |
| `Với dây chuyền L1, ca S1, máy nào xử lý xong trước khi hết ca?` | get_open_batches → get_shift_hours → get_available_machines → calculate_min_required_rate | tốc độ tối thiểu 11, máy M2 |
| `Dây chuyền L1 ca S1, hãy đặt máy M2` | như trên + propose_machine_assignment | đề xuất chờ trưởng ca, không khóa máy |
| `Hôm nay nên xếp các tin của chiến dịch CMP-1 vào khung giờ nào?` | get_pending_messages → get_contact_policy → get_opt_in_status → build_send_schedule | A1 B1 idle A2 B2 idle A3 B3 |
| `Sự cố INC-9 ảnh hưởng đến đâu?` | get_incident → get_service_graph → get_customer_facing_services → trace_impact | Reports (1), MobileApp (2), WebStore (3) |

Ca lỗi/biên có sẵn trong dữ liệu mẫu: `I-78` (đã thanh toán), `I-79` (không có cặp), `I-999` (không tồn tại), `L2/S2` (thiếu công suất), `L3/S3` (không có lô), `CMP-2` (khách từ chối nhận + hết ô, và "gửi ngay"), `INC-10` (sơ đồ thiếu node → `incomplete_data`). Thiếu mã (ví dụ "Kiểm tra hóa đơn") thì AI hỏi lại. Chế độ `mock` nhận mã theo dạng `I-77`, `L1` + `S1`, `CMP-1`, `INC-9`.

## Thiết kế an toàn

- Công cụ đọc dữ liệu từ database; công cụ thuật toán (`find_two_transfer_match`, `calculate_min_required_rate`, `build_send_schedule`, `trace_impact`) chỉ nhận ID và **tự đọc lại dữ liệu** ở backend, không nhận số liệu do model truyền vào (tham số lạ bị từ chối).
- Chỉ chạy công cụ có trong danh sách; tên lạ (`run_sql`...) hoặc tham số sai bị từ chối và trả lại model bằng `ToolMessage` có đúng `tool_call_id`. Vòng lặp tối đa 8 bước.
- Không có công cụ ghi nhận thanh toán, khóa máy hay gửi tin: chỉ có `propose_*` tạo bản nháp `pending`. Mỗi lần chat lưu câu hỏi, từng lần gọi công cụ, kết quả/lỗi và câu trả lời vào bảng `chat_records`.

## Vì sao GenAI cần gọi công cụ

Số liệu (hóa đơn, giao dịch, lô, máy, tin, sơ đồ dịch vụ) nằm trong hệ thống, không có sẵn trong model. Model chỉ biết mã người dùng hỏi nên phải gọi công cụ để đọc dữ liệu thật, rồi gọi công cụ thuật toán để tính chính xác (model tính nhẩm dễ sai và không kiểm chứng được). Sau đó nó chỉ giải thích kết quả công cụ trả về.

## Chạy test

```bash
pytest                            # toàn bộ (46 test; phần API chạy trên Supabase ở schema riêng pytest_tool_calling, mất vài phút, không gọi OpenAI)
pytest tests/test_algorithms.py   # chỉ thuật toán, không cần database hay model
```

Cấu trúc: `app/algorithms/` (two_sum, binary_search, scheduler, bfs) · `app/tools.py` (công cụ + `@tool`) · `app/agent.py` (vòng lặp tool calling, model mock/openai) · `app/routers/chat.py` · `app/seed.py` (dữ liệu mẫu).

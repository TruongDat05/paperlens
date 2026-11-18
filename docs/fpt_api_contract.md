# Hợp đồng API FPT cho retrieval

Trạng thái **chờ kiểm chứng**. File triển khai tương ứng là `backend/app/providers/fpt.py`. Điểm kiểm chứng là `scripts/smoke_test_fpt.py`.

| Vai trò | Model dự kiến | Bằng chứng cần ghi |
| --- | --- | --- |
| Embedding | `intfloat/multilingual-e5-large` | Model ID theo catalog, endpoint, schema, số chiều, số vector mỗi batch và cách báo usage |
| Reranking | `BAAI/bge-reranker-v2-m3` | Model ID theo catalog, endpoint, schema cặp query–passage, thứ tự/score, batch và usage |

Ghi cách xác thực, giới hạn kích thước, truncation, timeout, retry và lỗi theo từng endpoint. Ghi ngày kiểm chứng và mẫu request/response đã bỏ thông tin xác thực. Embedding smoke test đối chiếu prefix `query: ` và `passage: `. Reranking smoke test kiểm tra mapping scores về đúng passage từ một query và hai đoạn. [Kế hoạch v4.1, mục 6](../PaperLens_Research_Project_Plan.md#62-kiểm-chứng-fpt-retrieval-và-gateway-llm)

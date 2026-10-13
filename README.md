# MedGraph

> Hệ thống hỗ trợ phân tích triệu chứng hô hấp bằng GraphRAG (Knowledge Graph + RAG + LLM), ưu tiên tiếng Việt.

## Disclaimer y khoa

**MedGraph là công cụ tham khảo và giáo dục, không phải công cụ chẩn đoán và không thay thế bác sĩ.** 
Khi có dấu hiệu nguy hiểm hoặc cấp cứu, hãy đến ngay cơ sở y tế gần nhất hoặc gọi cấp cứu (115 tại Việt Nam).

---

## Cài đặt và khởi chạy

Dự án sử dụng script chuẩn hóa `init.sh` để kiểm tra môi trường, cài đặt dependencies và chạy kiểm thử tự động.

### Trên Linux / macOS / WSL / Git Bash (Windows)

```bash
# Khởi tạo môi trường, kiểm tra công cụ và chạy test (bỏ qua Docker/Neo4j nếu chưa chạy)
./init.sh --no-docker

# Khởi tạo đầy đủ bao gồm Docker Neo4j
./init.sh
```

### Chạy kiểm thử thủ công

```bash
# Unit test (nhanh, không cần mạng hay Neo4j)
pytest -m unit -q

# Integration test (yêu cầu Neo4j đang chạy)
pytest -m integration -q

# Kiểm tra định dạng và quy chuẩn code
ruff check .
ruff format --check .
```

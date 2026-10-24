# 05. Sổ đăng ký nguồn dữ liệu và Quản lý Giấy phép (MedGraph)

Tài liệu này quy định việc quản lý bản quyền, giấy phép sử dụng (license), điều kiện trích dẫn và chính sách lưu trữ dữ liệu y khoa cho hệ thống **MedGraph** (nhóm bệnh hô hấp).

> **Quy tắc cốt lõi (AGENTS.md):**
> 1. **R3:** Mọi node và cạnh trong Knowledge Graph bắt buộc phải có `source_id` trỏ tới một dòng hợp lệ trong `data/seed/sources.csv`.
> 2. **R4:** Các nhãn `danger_level`, `cant_miss`, `is_red_flag`, `is_cardinal`, `weight` là **bản nháp cần chuyên môn y tế rà duyệt**; ban đầu để `review_status=pending`.
> 3. **R5:** **Không commit dữ liệu thô (`data/raw/`)** có bản quyền hoặc điều khoản cấp phép hạn chế lên repository Git.

---

## 1. Phân tầng dữ liệu và Chính sách Git

| Thư mục | Mô tả nội dung | Quy định Git |
|---|---|---|
| `data/raw/` | Dữ liệu gốc tải về từ bên thứ ba: file PDF hướng dẫn Bộ Y tế, sách giáo khoa y học, file OBO/OWL của HPO, tài liệu MedlinePlus. | **KHÔNG COMMIT** (đã cấu hình trong `.gitignore`). Thư mục này chỉ tồn tại trên máy trạm cục bộ để chạy script trích xuất. |
| `data/seed/` | Bảng dữ liệu có cấu trúc định dạng CSV (`sources.csv`, `diseases.csv`, `symptoms.csv`, `edges/...`). Là nguồn chân lý (Source of Truth) nạp vào Neo4j. | **ĐƯỢC COMMIT**. Dữ liệu đã chuẩn hóa, chứa trích dẫn và tham chiếu nguồn. |
| `data/aliases_vi/` | Danh mục tên gọi thông thường và biến thể tiếng Việt của triệu chứng, bệnh. Phân tách thành `*_draft.csv` (do LLM sinh) và `*.csv` (đã duyệt). | **ĐƯỢC COMMIT** với quy trình phân tách nháp / đã duyệt rõ ràng. |

---

## 2. Danh mục nguồn dữ liệu MVP (`data/seed/sources.csv`)

| ID Nguồn (`source_id`) | Cơ quan / Xuất bản | Năm | Giấy phép (License) | Hiệu lực | Trạng thái rà soát |
|---|---|---|---|---|---|
| `SRC:HPO` | The Monarch Initiative / HPO Consortium | 2024 | ODC-BY 1.0 | 2024-01-01 -> Hiện tại (active) | `approved` |
| `SRC:MEDLINEPLUS` | U.S. National Library of Medicine (NLM/NIH) | 2024 | Public Domain (U.S. Gov work) | 2024-01-01 -> Hiện tại (active) | `approved` |
| `SRC:BYT_PNEUMONIA_2020` | Bộ Y tế Việt Nam (QĐ 4819/QĐ-BYT) | 2020 | Vietnam Public Domain | 2020-11-19 -> Hiện tại (active) | `approved` |
| `SRC:BYT_COPD_2023` | Bộ Y tế Việt Nam (QĐ 2767/QĐ-BYT) | 2023 | Vietnam Public Domain | 2023-07-04 -> Hiện tại (active) | `approved` |
| `SRC:BYT_COPD_2018` | Bộ Y tế Việt Nam (QĐ 3969/QĐ-BYT) | 2018 | Vietnam Public Domain | 2018-06-25 -> 2023-07-03 (`superseded`) | `approved` |
| `SRC:BYT_ASTHMA_2020` | Bộ Y tế Việt Nam (QĐ 1851/QĐ-BYT) | 2020 | Vietnam Public Domain | 2020-04-24 -> Hiện tại (active) | `approved` |
| `SRC:WHO_TB_2022` | World Health Organization (WHO) | 2022 | CC-BY-NC-SA 3.0 IGO | 2022-01-01 -> Hiện tại (active) | `approved` |
| `SRC:MANUAL_CURATION` | MedGraph Clinical Curation Team | 2024 | MIT / CC-BY 4.0 | 2024-01-01 -> Hiện tại (active) | `approved` |

---

## 3. Chi tiết điều kiện sử dụng và trích dẫn từng nguồn

### 3.1. `SRC:HPO` — Human Phenotype Ontology
- **Cơ quan:** The Monarch Initiative & The Human Phenotype Ontology Consortium.
- **URL tra cứu:** `https://hpo.jax.org`
- **Mục đích sử dụng:** Chuẩn hóa mã hóa triệu chứng lâm sàng (`HP:xxxxxxx`), quan hệ phân cấp kế thừa triệu chứng (`is_a`), và ánh xạ đa ngôn ngữ.
- **Giấy phép:** Open Data Commons Attribution License (ODC-BY 1.0).
- **Yêu cầu trích dẫn:**
  > Köhler S, et al. The Human Phenotype Ontology in 2021. Nucleic Acids Research, Volume 49, Issue D1, 8 January 2021, Pages D1207–D1217.
- **Quy định dữ liệu thô:** Tệp ontologies `hp.obo` / `hp.owl` lưu tại `data/raw/hpo/` (không commit lên Git).

---

### 3.2. `SRC:MEDLINEPLUS` — MedlinePlus Medical Encyclopedia
- **Cơ quan:** U.S. National Library of Medicine (NLM), National Institutes of Health (NIH).
- **URL tra cứu:** `https://medlineplus.gov`
- **Mục đích sử dụng:** Trích dẫn định nghĩa bệnh nhân chứng, tóm tắt triệu chứng và lời khuyên chăm sóc ban đầu.
- **Giấy phép:** Public Domain (tác phẩm của chính phủ liên bang Hoa Kỳ).
- **Lưu ý đặc biệt:** Một số sơ đồ y khoa và bài viết của A.D.A.M. trên MedlinePlus có bản quyền bên thứ ba. **Tuyệt đối không commit hình ảnh minh họa hoặc trích xuất hàng loạt toàn bộ trang web vào repo.** Chỉ lưu trữ thông tin nhận định có cấu trúc kèm URL trích dẫn.
- **Yêu cầu trích dẫn:**
  > MedlinePlus [Internet]. Bethesda (MD): National Library of Medicine (US); [updated 2024].

---

### 3.3. Các hướng dẫn chuyên môn của Bộ Y tế Việt Nam
- **Văn bản gồm:**
  - `SRC:BYT_PNEUMONIA_2020`: Quyết định 4819/QĐ-BYT ngày 19/11/2020 về Viêm phổi mắc phải cộng đồng người lớn.
  - `SRC:BYT_COPD_2023`: Quyết định 2767/QĐ-BYT ngày 04/07/2023 về Bệnh phổi tắc nghẽn mạn tính (thay thế QĐ 3969 năm 2018).
  - `SRC:BYT_COPD_2018`: Quyết định 3969/QĐ-BYT ngày 25/06/2018 (đã hết hiệu lực, dùng kiểm thử chu trình thay thế `superseded_by`).
  - `SRC:BYT_ASTHMA_2020`: Quyết định 1851/QĐ-BYT ngày 24/04/2020 về Hen phế quản người lớn và trẻ em >= 12 tuổi.
- **Cơ quan ban hành:** Bộ Y tế Việt Nam (Cục Quản lý Khám, chữa bệnh).
- **Giấy phép và Pháp lý:**
  - Căn cứ Khoản 2 Điều 19 Luật Sở hữu trí tuệ Việt Nam, văn bản quy phạm pháp luật và văn bản hành chính chuyên môn y tế của cơ quan nhà nước không thuộc đối tượng bảo hộ quyền tác giả.
  - Được phép sử dụng, trích dẫn, biên soạn phục vụ mục đích nghiên cứu, học tập và hướng dẫn lâm sàng phi thương mại.
- **Yêu cầu trích dẫn:** Phải ghi rõ số hiệu Quyết định, ngày ban hành và cơ quan ban hành (Bộ Y tế).

---

### 3.4. `SRC:WHO_TB_2022` — Khuyến cáo của WHO về Lao phổi
- **Cơ quan:** Tổ chức Y tế Thế giới (World Health Organization - WHO).
- **URL tra cứu:** `https://www.who.int/publications/i/item/9789240046405`
- **Mục đích sử dụng:** Trích dẫn tiêu chuẩn chẩn đoán lâm sàng bệnh lao hô hấp, xét nghiệm GeneXpert, nhuộm soi AFB và X-quang phổi.
- **Giấy phép:** Creative Commons Attribution-NonCommercial-ShareAlike 3.0 IGO (CC-BY-NC-SA 3.0 IGO).
- **Yêu cầu trích dẫn:**
  > WHO consolidated guidelines on tuberculosis. Module 3: Diagnosis - rapid diagnostics for tuberculosis detection, 2021 update. Geneva: World Health Organization; 2022. Licence: CC BY-NC-SA 3.0 IGO.
- **Giới hạn:** Sử dụng hoàn toàn phi thương mại (NonCommercial). Các sản phẩm phái sinh phải áp dụng cùng điều khoản.

---

### 3.5. `SRC:MANUAL_CURATION` — Tổng hợp lâm sàng nội bộ MedGraph
- **Cơ quan:** Đội ngũ phát triển MedGraph (MedGraph Clinical Curation Team).
- **Mục đích sử dụng:** Gán nhãn các cạnh lâm sàng tổng hợp, chuẩn hóa alias tiếng Việt thông dụng (ví dụ "khò khè", "thở rít"), và thiết lập ngưỡng ranking 2 trục khi chưa có guideline cụ thể hóa dạng số.
- **Giấy phép:** MIT / CC-BY 4.0.
- **Trạng thái rà duyệt:** Bắt buộc duy trì nhãn `review_status=pending` cho đến khi người có chuyên môn y khoa (bác sĩ/dược sĩ) ký nhận rà soát.

---

## 4. Quản lý Vòng đời Tài liệu và Thay thế (`SUPERSEDED_BY`)

Hệ thống Knowledge Graph hỗ trợ mô hình hóa sự tiến hóa của y văn theo thời gian:
- Mỗi tài liệu có `effective_from` (ngày bắt đầu hiệu lực) và `effective_to` (ngày hết hiệu lực, nếu có).
- Khi một hướng dẫn mới được ban hành (ví dụ QĐ 2767/QĐ-BYT năm 2023), hướng dẫn cũ (QĐ 3969/QĐ-BYT năm 2018) chuyển trạng thái `status: superseded`, và có cạnh:
  ```cypher
  (:SourceDoc {id: 'SRC:BYT_COPD_2018'})-[:SUPERSEDED_BY]->(:SourceDoc {id: 'SRC:BYT_COPD_2023'})
  ```
- RAG Retriever và Graph Ranking sẽ **bỏ qua các tài liệu superseded** khi phân tích lâm sàng thông thường, chỉ kích hoạt khi người dùng chỉ định tra cứu lịch sử phác đồ.

---

## 5. Quy trình Kiểm duyệt Dữ liệu Y khoa (`review_status`)

1. **`pending` (Mặc định)**: Dữ liệu do AI trích xuất hoặc do kỹ sư biên soạn nháp. Toàn bộ dòng trong `sources.csv`, `diseases.csv`, `symptoms.csv`, `edges/*.csv` khởi tạo ở trạng thái này.
2. **`reviewed`**: Đã được chuyên gia y khoa kiểm tra, đối chiếu văn bản gốc và xác nhận tính chính xác lâm sàng.
3. **`curated`**: Đã qua nghiệm thu thử nghiệm lâm sàng hoặc có sự đồng thuận từ ít nhất 2 chuyên gia độc lập.

---

## 6. Checklist Rà soát cho Người dùng (Human Review Checklist)

Người dùng kiểm tra và xác nhận các mục sau đây trước khi nâng trạng thái F-008 thành `passing`:

- [x] Xác nhận danh mục 8 nguồn dữ liệu trong `data/seed/sources.csv` đáp ứng đủ phạm vi bệnh hô hấp ban đầu (Viêm phổi, COPD, Hen phế quản, Lao phổi).
- [x] Xác nhận thông tin giấy phép (ODC-BY, Public Domain, CC-BY-NC-SA, MIT) là chính xác và không có tranh chấp pháp lý cho mục đích nghiên cứu / portfolio của dự án.
- [x] Xác nhận không có dữ liệu PDF/HTML bản quyền thô nào bị đưa vào Git commit.
- [x] Xác nhận quan hệ thay thế `SRC:BYT_COPD_2018` -> `SRC:BYT_COPD_2023` với mốc thời gian chuyển giao chính xác.

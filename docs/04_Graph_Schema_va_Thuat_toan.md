# MedGraph: Schema Graph và Thuật toán

> Node, quan hệ, Cypher mẫu, ranking 2 trục, abstain, câu hỏi gợi ý, validator, hợp đồng dữ liệu

## 1. Node

| Label | Thuộc tính chính |
|---|---|
| Symptom | id (HPO/UMLS), name_en, name_vi, aliases_vi[], idf, is_red_flag, parent_ids (is_a) |
| Disease | id (ICD-10/UMLS), name_en, name_vi, aliases_vi[], category, urgency_default, **danger_level (1 đến 3), cant_miss (bool)** |
| RiskFactor | id, name_vi, type (hút thuốc, tuổi, tiếp xúc...) |
| LabTest | id (LOINC), name_vi, purpose |
| SourceDoc | id, title, publisher, year, url, license, **effective_from, effective_to, superseded_by, status** |
| Drug (giai đoạn 2) | id (RxNorm), name_vi, class |

## 2. Quan hệ

| Quan hệ | Thuộc tính |
|---|---|
| (Symptom)-[:INDICATES]->(Disease) | weight (0 đến 1), is_cardinal (triệu chứng cốt lõi), **provenance, evidence_count, confidence**, source_id |
| (Disease)-[:HAS_RISK_FACTOR]->(RiskFactor) | weight, provenance, source_id |
| (Disease)-[:CONFIRMED_BY]->(LabTest) | role (sàng lọc hoặc xác định), source_id |
| (Disease)-[:DIFFERENTIAL_OF]->(Disease) | distinguishing_features |
| (Disease)-[:DOCUMENTED_IN]->(SourceDoc) | section |
| (Symptom)-[:IS_A]->(Symptom) | mở rộng ontology (ví dụ ho ra máu là một dạng ho) |
| (SourceDoc)-[:SUPERSEDED_BY]->(SourceDoc) | effective_from của bản mới; dùng để chỉ lấy hướng dẫn còn hiệu lực |

**provenance** nhận một trong ba giá trị: *curated* (nhập tay từ nguồn), *reviewed* (trích xuất rồi đã rà soát), *auto_extracted* (do LLM trích xuất, chưa rà). Ranking nhân hệ số độ tin cậy theo giá trị này.

Mọi cạnh phải có **source_id**: đây là yêu cầu bắt buộc để hệ thống trích dẫn được nguồn.

## 3. Ràng buộc và index

```cypher
CREATE CONSTRAINT symptom_id IF NOT EXISTS FOR (s:Symptom) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT disease_id IF NOT EXISTS FOR (d:Disease) REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT risk_id    IF NOT EXISTS FOR (r:RiskFactor) REQUIRE r.id IS UNIQUE;
CREATE FULLTEXT INDEX symptom_alias IF NOT EXISTS
  FOR (s:Symptom) ON EACH [s.name_vi, s.aliases_vi];
```

## 4. Truy vấn xếp hạng bệnh ứng viên

Ví dụ đầu vào "ho kéo dài + sốt nhẹ + đau ngực", các tham số được truyền từ bước Entity Linking.

```cypher
// $symptom_ids = ["HP:0012735", "HP:0001945", "HP:0100749"]
// $risk_ids    = ["RF:tb_contact"]
MATCH (s:Symptom) WHERE s.id IN $symptom_ids
MATCH (s)-[r:INDICATES]->(d:Disease)
WITH d,
     collect({id: s.id, name: s.name_vi, w: r.weight}) AS matched,
     sum(r.weight * r.confidence * s.idf) AS symptom_score
OPTIONAL MATCH (d)-[hr:HAS_RISK_FACTOR]->(rf:RiskFactor)
  WHERE rf.id IN $risk_ids
WITH d, matched, symptom_score, coalesce(sum(hr.weight), 0) AS risk_score
RETURN d.id AS id, d.name_vi AS name, matched,
       d.danger_level AS danger, d.cant_miss AS cant_miss,
       symptom_score + $alpha * risk_score AS score
ORDER BY score DESC
LIMIT $k;
```

#### Truy vấn lấy subgraph để hiển thị

```cypher
MATCH p = (s:Symptom)-[:INDICATES]->(d:Disease {id: $disease_id})
WHERE s.id IN $symptom_ids
RETURN p;
```

Lưu ý: truy vấn trên chưa tính phạt thiếu triệu chứng cốt lõi, phủ định, hệ số mở rộng is_a và quy tắc abstain. Phần đó tính trong Python (ranking.py) sau khi lấy dữ liệu từ graph.

#### Mở rộng theo ontology (is_a) trước khi truy vấn

```cypher
MATCH (s:Symptom) WHERE s.id IN $symptom_ids
MATCH path = (s)-[:IS_A*1..2]->(p:Symptom)
RETURN s.id AS child, p.id AS parent, length(path) AS hops;
// Python: trọng số cha = decay ** hops (decay lấy từ config/ranking.yaml)
```

## 5. Thuật toán xếp hạng 2 trục

Với mỗi bệnh ứng viên d, tập triệu chứng người dùng S (đã bỏ triệu chứng bị phủ định khỏi phần cộng điểm):

```
idf(s)   = log( N_disease / (1 + df(s)) )          # df = số bệnh có triệu chứng s
conf(e)  = hệ số theo provenance                   # curated, reviewed = 1.0; auto_extracted < 1 (cấu hình)
sym(d)   = Σ w(s,d) · conf(s,d) · idf(s) · decay^hops    # s thuộc S ∩ Sym(d)
risk(d)  = Σ w(r,d) · conf(r,d)                    # r thuộc R ∩ Risk(d)
miss(d)  = Σ penalty                               # thiếu triệu chứng cốt lõi
neg(d)   = Σ negation_penalty                      # người dùng phủ nhận triệu chứng cốt lõi
score(d) = sym(d) + α·risk(d) − β·miss(d) − γ·neg(d)

TRỤC 1  likelihood(d) = score(d) / max score       # 0..1
TRỤC 2  danger(d)     = d.danger_level             # 1..3, gán từ nguồn uy tín

likely    = top-k theo likelihood
cant_miss = { d : d.cant_miss = true  và  likelihood(d) >= tau_min }
```

#### Quy tắc abstain (không xếp hạng tự tin)

```
abstain  nếu   likelihood(top1) < tau_low    HOẶC    likelihood(top1) - likelihood(top2) < delta
# Khi abstain: không đưa danh sách tự tin, hỏi thêm câu phân biệt (xem bên dưới).
# Red-flag luôn hiển thị, không phụ thuộc quy tắc này.
```

#### Chọn câu hỏi tiếp theo (information gain)

```
Với D = top-k ứng viên (phân phối likelihood đã chuẩn hóa), q = triệu chứng chưa hỏi:
  p(q)    = tổng likelihood của các bệnh có triệu chứng q
  gain(q) = H(D) - [ p(q)·H(D | có q) + (1 - p(q))·H(D | không q) ]
Chọn q có gain lớn nhất; ưu tiên q có is_cardinal hoặc is_red_flag.
```

- **idf** làm sốt (gặp ở rất nhiều bệnh) có trọng số thấp, ho ra máu (đặc hiệu hơn) có trọng số cao.
- Mọi tham số (α, β, γ, decay, tau_min, tau_low, delta) nằm trong config/ranking.yaml và được **tinh chỉnh bằng gold set**, không đặt cứng khi chưa đo.
- Hướng mở rộng: chuyển sang xác suất kiểu Naive Bayes với P(triệu chứng | bệnh), có thể học từ DDXPlus.

## 6. Entity Linking nhiều tầng

| Tầng | Cách làm | Ghi chú |
|---|---|---|
| 1 | Khớp chính xác với name_vi và aliases_vi (đã chuẩn hóa dấu, chữ thường) | Nhanh, rẻ, độ chính xác cao |
| 2 | BM25 trên tên và alias để bắt biến thể từ vựng | Tương tự thành phần TF-IDF/lexical trong hybrid retrieval |
| 3 | Embedding đa ngữ (bge-m3) tìm node gần nhất, chỉ nhận nếu điểm ≥ ngưỡng | Ngưỡng cấu hình trong ranking.yaml |
| 4 | Mở rộng theo is_a (cha) với hệ số giảm dần | Ví dụ ho ra máu kéo theo ho với trọng số thấp hơn |
| 5 | Không đạt ngưỡng: đánh dấu chưa nhận diện và hỏi lại người dùng | Tránh đoán sai trong bối cảnh y khoa |

Đo **linking recall theo từng cấu hình** (chỉ alias, +BM25, +embedding, +is_a) để có bảng ablation chứng minh giá trị của hybrid.

## 7. Prompt template và Citation Validator

```
Bạn là trợ lý thông tin y khoa. Chỉ sử dụng các đoạn tài liệu trong <evidence>.
Nếu tài liệu không đủ, hãy nói rõ là không đủ thông tin.
Không chẩn đoán chắc chắn. Không kê đơn hoặc đề xuất liều thuốc.
Trả về JSON: danh sách nhận định, mỗi nhận định có "text" và "chunk_id" lấy từ <evidence>.
Trả lời tiếng Việt, dễ hiểu.

<user_symptoms>...</user_symptoms>
<candidates>... (từ graph: điểm, danger_level, triệu chứng khớp) ...</candidates>
<evidence>... (đoạn văn + chunk_id + metadata) ...</evidence>
```

| Lớp | Kiểm tra | Nếu không đạt |
|---|---|---|
| Lớp 1: tồn tại | chunk_id có thật trong vector store và nguồn còn hiệu lực | Loại nhận định |
| Lớp 2: ủng hộ | Đoạn nguồn có thực sự ủng hộ nhận định (LLM-judge hoặc NLI), chỉ kiểm cho top-3 ứng viên và có cache | Loại nhận định |
| Sau 2 lớp | Còn ít nhất một nhận định hợp lệ? | Không: trả "không đủ căn cứ"; red-flag vẫn hiển thị |
| LLM lỗi | Không gọi được LLM | Mẫu dự phòng: red-flag, bảng ứng viên, đoạn nguồn nguyên văn |

## 8. Hợp đồng dữ liệu (Pydantic, rút gọn)

```python
class Entity(BaseModel):
    text: str; id: str | None; type: Literal["symptom", "risk", "lab", "drug", "condition"]
    negated: bool = False; duration_days: int | None = None
    severity: str | None = None; value: float | None = None; unit: str | None = None

class Claim(BaseModel):
    text: str; chunk_id: str; supported: bool | None = None

class Candidate(BaseModel):
    disease_id: str; name_vi: str; likelihood: float; danger_level: int
    provenance_mix: dict[str, int] = {}; claims: list[Claim] = []

class Result(BaseModel):
    abstained: bool; urgency: Urgency; red_flags: list[str]
    likely: list[Candidate]; cant_miss: list[Candidate]
    follow_up_questions: list[str]; subgraph: dict; disclaimer: str
```

## 9. Dữ liệu mẫu: alias triệu chứng (cần rà soát)

| id | name_vi | aliases_vi (cần rà soát) |
|---|---|---|
| HP:0012735 | ho | ho khan; ho dai dẳng; ho kéo dài; ho liên tục |
| HP:0001945 | sốt | sốt nhẹ; sốt âm ỉ; sốt về chiều |
| HP:0100749 | đau ngực | tức ngực; nhói ngực; nặng ngực |
| HP:0002094 | khó thở | thở dốc; hụt hơi; thở không ra hơi |
| HP:0002105 | ho ra máu | khạc ra máu; ho có máu |
| HP:0001824 | sụt cân | gầy đi; sút cân; giảm cân không rõ lý do |

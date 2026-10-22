// =============================================================================
// MedGraph: Schema Constraints & Indexes (Cypher)
//
// Đóng băng theo quy tắc R7 (AGENTS.md).
// Mọi câu lệnh bắt buộc sử dụng IF NOT EXISTS để đảm bảo tính idempotent.
// =============================================================================

// --- 1. Unique Constraints trên thuộc tính id cho mọi NodeLabel ---

CREATE CONSTRAINT symptom_id IF NOT EXISTS
FOR (s:Symptom) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT disease_id IF NOT EXISTS
FOR (d:Disease) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT risk_factor_id IF NOT EXISTS
FOR (r:RiskFactor) REQUIRE r.id IS UNIQUE;

CREATE CONSTRAINT lab_test_id IF NOT EXISTS
FOR (l:LabTest) REQUIRE l.id IS UNIQUE;

CREATE CONSTRAINT source_doc_id IF NOT EXISTS
FOR (src:SourceDoc) REQUIRE src.id IS UNIQUE;

// --- 2. Fulltext Indexes cho tìm kiếm và entity linking tiếng Việt ---

CREATE FULLTEXT INDEX symptom_alias IF NOT EXISTS
FOR (s:Symptom) ON EACH [s.name_vi, s.aliases_vi, s.aliases_norm];

CREATE FULLTEXT INDEX disease_alias IF NOT EXISTS
FOR (d:Disease) ON EACH [d.name_vi, d.aliases_vi, d.aliases_norm];

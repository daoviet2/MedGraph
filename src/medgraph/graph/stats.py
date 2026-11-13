"""Tính IDF của triệu chứng từ số bệnh và các cạnh INDICATES đã nạp."""

import math
from typing import Any, Protocol


class SymptomIdfRepository(Protocol):
    """Các thao tác graph cần cho bước hậu xử lý IDF."""

    def get_disease_count(self, tx: Any = None) -> int: ...

    def get_symptom_disease_frequencies(self, tx: Any = None) -> dict[str, int]: ...

    def update_symptom_idf(self, idf_by_symptom: dict[str, float], tx: Any = None) -> int: ...


def compute_idf(n_diseases: int, document_frequency: int) -> float:
    """Trả log(N_disease / (1 + df)); giá trị có thể âm theo đúng công thức."""
    if n_diseases < 1:
        raise ValueError("n_diseases must be positive")
    if not 0 <= document_frequency <= n_diseases:
        raise ValueError("document_frequency must be between 0 and n_diseases")
    return math.log(n_diseases / (1 + document_frequency))


def refresh_symptom_idf(repository: SymptomIdfRepository, tx: Any = None) -> int:
    """Tính từ trạng thái graph thực tế và ghi IDF cho triệu chứng có INDICATES."""
    n_diseases = repository.get_disease_count(tx=tx)
    if n_diseases == 0:
        return 0
    frequencies = repository.get_symptom_disease_frequencies(tx=tx)
    idf_by_symptom = {
        symptom_id: compute_idf(n_diseases, frequency)
        for symptom_id, frequency in frequencies.items()
    }
    return repository.update_symptom_idf(idf_by_symptom, tx=tx)

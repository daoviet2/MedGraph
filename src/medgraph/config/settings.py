"""Cấu hình tập trung cho MedGraph.

Đọc cấu hình từ biến môi trường (.env / OS environment) và file config/settings.yaml.
Thứ tự ưu tiên: init kwargs > OS environment > .env > settings.yaml > default.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
from pydantic_settings.main import ENV_FILE_SENTINEL, DotenvType


class Settings(BaseSettings):
    """Cấu hình toàn hệ thống MedGraph."""

    # Thông tin cơ bản
    app_name: str = Field(default="MedGraph", description="Tên ứng dụng")
    schema_version: str = Field(default="1.0.0", description="Phiên bản schema")

    # Neo4j Database (bắt buộc)
    neo4j_uri: str = Field(description="URI kết nối Neo4j (ví dụ: bolt://localhost:7687)")
    neo4j_user: str = Field(description="Tên người dùng Neo4j")
    neo4j_password: str = Field(description="Mật khẩu truy cập Neo4j")
    neo4j_max_connection_lifetime: int = Field(
        default=3600,
        description="Thời gian sống tối đa của kết nối Neo4j (giây)",
    )
    neo4j_max_connection_pool_size: int = Field(
        default=50,
        description="Kích thước pool kết nối Neo4j",
    )

    # LLM Configuration
    llm_provider: Literal["anthropic", "fake"] = Field(
        default="fake",
        description="Nhà cung cấp LLM (anthropic hoặc fake)",
    )
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        description="Khóa API Anthropic (được bảo vệ dưới dạng SecretStr)",
    )
    llm_model_small: str = Field(
        default="claude-3-haiku-20240307",
        description="Mô hình LLM nhỏ cho trích xuất thực thể và tác vụ nhẹ",
    )
    llm_model_large: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Mô hình LLM lớn cho suy luận và giải thích",
    )

    # Đường dẫn thư mục dữ liệu & cache (thường nạp từ settings.yaml)
    data_dir: Path = Field(
        default=Path("data"),
        description="Đường dẫn thư mục dữ liệu chính",
    )
    seed_dir: Path = Field(
        default=Path("data/seed"),
        description="Đường dẫn thư mục chứa dữ liệu seed",
    )
    aliases_dir: Path = Field(
        default=Path("data/aliases_vi"),
        description="Đường dẫn thư mục alias tiếng Việt",
    )
    cache_dir: Path = Field(
        default=Path(".cache"),
        description="Đường dẫn thư mục cache",
    )

    # Loader & ETL
    batch_size: int = Field(
        default=500,
        description="Kích thước lô khi ghi vào Knowledge Graph",
    )

    # Biến nội bộ hỗ trợ override đường dẫn yaml khi kiểm thử
    _yaml_path: ClassVar[Path | str | None] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        yaml_file="config/settings.yaml",
        yaml_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="forbid",
        frozen=True,
    )

    def __init__(
        self,
        _yaml_file: Path | str | None = None,
        _env_file: DotenvType | None = ENV_FILE_SENTINEL,
        **values: Any,
    ) -> None:
        """Khởi tạo Settings, hỗ trợ override đường dẫn file cấu hình khi kiểm thử."""
        if _yaml_file is not None:
            prev_yaml = Settings._yaml_path
            try:
                Settings._yaml_path = _yaml_file
                super().__init__(**values, _env_file=_env_file)
            finally:
                Settings._yaml_path = prev_yaml
        else:
            super().__init__(**values, _env_file=_env_file)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Tùy chỉnh thứ tự nguồn: init kwargs > env > dotenv > yaml > file_secret > default."""
        yaml_file = (
            cls._yaml_path
            if cls._yaml_path is not None
            else settings_cls.model_config.get("yaml_file")
        )
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(
                settings_cls,
                yaml_file=yaml_file,
                yaml_file_encoding="utf-8",
            ),
            file_secret_settings,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Trả về thể hiện Settings duy nhất cho ứng dụng (singleton via cache)."""
    return Settings()

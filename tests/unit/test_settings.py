"""Unit tests cho module cấu hình (Settings)."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from medgraph.config.settings import Settings, get_settings


@pytest.mark.unit
def test_default_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Xác nhận các giá trị mặc định được thiết lập đúng khi chỉ truyền các trường bắt buộc."""
    # Xóa sạch biến môi trường có thể gây nhiễu
    for var in ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "BATCH_SIZE", "LLM_PROVIDER"]:
        monkeypatch.delenv(var, raising=False)

    # Sử dụng file yaml và env rỗng
    empty_yaml = tmp_path / "empty.yaml"
    empty_yaml.write_text("", encoding="utf-8")
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")

    settings = Settings(
        _yaml_file=empty_yaml,
        _env_file=empty_env,
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="test_password",
    )

    assert settings.app_name == "MedGraph"
    assert settings.schema_version == "1.0.0"
    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert settings.neo4j_user == "neo4j"
    assert settings.neo4j_password == "test_password"
    assert settings.batch_size == 500
    assert settings.llm_provider == "fake"
    assert settings.anthropic_api_key is None
    assert settings.data_dir == Path("data")
    assert settings.seed_dir == Path("data/seed")
    assert settings.aliases_dir == Path("data/aliases_vi")
    assert settings.cache_dir == Path(".cache")


@pytest.mark.unit
def test_yaml_overrides_default(tmp_path: Path) -> None:
    """Xác nhận cấu hình từ settings.yaml ghi đè lên giá trị mặc định."""
    custom_yaml = tmp_path / "custom.yaml"
    custom_yaml.write_text(
        "batch_size: 250\ndata_dir: custom_data\nneo4j_max_connection_pool_size: 100\n",
        encoding="utf-8",
    )
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")

    settings = Settings(
        _yaml_file=custom_yaml,
        _env_file=empty_env,
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="pwd",
    )

    assert settings.batch_size == 250
    assert settings.data_dir == Path("custom_data")
    assert settings.neo4j_max_connection_pool_size == 100
    # Các giá trị không có trong yaml vẫn giữ mặc định
    assert settings.llm_provider == "fake"


@pytest.mark.unit
def test_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Xác nhận biến môi trường có độ ưu tiên cao hơn settings.yaml (env > yaml > default)."""
    custom_yaml = tmp_path / "custom.yaml"
    custom_yaml.write_text(
        "batch_size: 250\ndata_dir: yaml_data\n",
        encoding="utf-8",
    )
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")

    # Đặt biến môi trường ghi đè giá trị trong yaml
    monkeypatch.setenv("BATCH_SIZE", "1000")
    monkeypatch.setenv("DATA_DIR", "env_data")

    settings = Settings(
        _yaml_file=custom_yaml,
        _env_file=empty_env,
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="pwd",
    )

    assert settings.batch_size == 1000
    assert settings.data_dir == Path("env_data")


@pytest.mark.unit
def test_missing_required_fields_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Xác nhận thiếu biến bắt buộc sẽ ném ValidationError có thông báo rõ tên biến."""
    for var in ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"]:
        monkeypatch.delenv(var, raising=False)

    empty_yaml = tmp_path / "empty.yaml"
    empty_yaml.write_text("", encoding="utf-8")
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_yaml_file=empty_yaml, _env_file=empty_env)

    errors = exc_info.value.errors()
    missing_fields = {err["loc"][0] for err in errors}
    assert "neo4j_uri" in missing_fields
    assert "neo4j_user" in missing_fields
    assert "neo4j_password" in missing_fields


@pytest.mark.unit
def test_anthropic_api_key_is_secret_str(tmp_path: Path) -> None:
    """Xác nhận ANTHROPIC_API_KEY là SecretStr và không bị lộ giá trị trong repr/log."""
    raw_secret = "sk-ant-secret-key-123456789"
    empty_yaml = tmp_path / "empty.yaml"
    empty_yaml.write_text("", encoding="utf-8")
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")

    settings = Settings(
        _yaml_file=empty_yaml,
        _env_file=empty_env,
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="pwd",
        anthropic_api_key=raw_secret,
    )

    assert isinstance(settings.anthropic_api_key, SecretStr)
    # Không xuất hiện trong str và repr
    assert raw_secret not in str(settings.anthropic_api_key)
    assert raw_secret not in repr(settings.anthropic_api_key)
    assert raw_secret not in repr(settings)
    assert "**********" in str(settings.anthropic_api_key)
    # Lấy giá trị thật qua get_secret_value()
    assert settings.anthropic_api_key.get_secret_value() == raw_secret


@pytest.mark.unit
def test_get_settings_cached() -> None:
    """Xác nhận hàm get_settings() được cache và trả về cùng một instance."""
    # Xóa cache trước khi test
    get_settings.cache_clear()

    s1 = get_settings()
    s2 = get_settings()

    assert s1 is s2
    assert get_settings.cache_info().hits >= 1


@pytest.mark.unit
def test_settings_is_immutable(tmp_path: Path) -> None:
    """Xác nhận Settings là bất biến (frozen=True)."""
    empty_yaml = tmp_path / "empty.yaml"
    empty_yaml.write_text("", encoding="utf-8")
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")

    settings = Settings(
        _yaml_file=empty_yaml,
        _env_file=empty_env,
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="pwd",
    )

    with pytest.raises(ValidationError):
        settings.batch_size = 999  # type: ignore[misc]


@pytest.mark.unit
def test_extra_fields_forbidden(tmp_path: Path) -> None:
    """Xác nhận trường lạ sẽ bị từ chối (extra='forbid')."""
    empty_yaml = tmp_path / "empty.yaml"
    empty_yaml.write_text("", encoding="utf-8")
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _yaml_file=empty_yaml,
            _env_file=empty_env,
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="pwd",
            unknown_parameter="unexpected",
        )

    errors = exc_info.value.errors()
    assert any(err["loc"][0] == "unknown_parameter" for err in errors)


@pytest.mark.unit
def test_no_global_settings_instance_on_import() -> None:
    """Xác nhận việc import module không tạo sẵn instance Settings toàn cục."""
    import medgraph.config.settings as settings_mod

    # Không có biến `settings` ở cấp độ module (tránh đọc file khi import)
    assert not hasattr(settings_mod, "settings")
    assert callable(settings_mod.get_settings)

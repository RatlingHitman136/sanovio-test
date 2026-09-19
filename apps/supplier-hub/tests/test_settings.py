import pytest
from pydantic import SecretStr, ValidationError

from supplier_hub.core.settings import HubSettings


def test_fake_llm_mode_needs_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert HubSettings(llm_mode="fake").anthropic_api_key is None


def test_real_llm_mode_requires_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY is required"):
        HubSettings(llm_mode="anthropic")


def test_key_is_never_shown_in_repr() -> None:
    settings = HubSettings(llm_mode="anthropic", anthropic_api_key=SecretStr("sk-secret"))

    assert "sk-secret" not in repr(settings)


def test_cors_is_off_unless_origins_are_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    assert HubSettings().cors_origins == ()
    named = HubSettings(cors_origins="http://localhost:5173, https://app.example")  # type: ignore[arg-type]
    assert named.cors_origins == ("http://localhost:5173", "https://app.example")
    with pytest.raises(ValidationError, match="'\\*' is not allowed"):
        HubSettings(cors_origins="*")  # type: ignore[arg-type]


def test_an_empty_ui_dir_means_no_app() -> None:
    assert HubSettings(supplier_ui_dir="").supplier_ui_dir is None  # type: ignore[arg-type]

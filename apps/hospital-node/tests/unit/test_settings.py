from pathlib import Path

import pytest

from hospital_node.core.settings import NodeSettings


def test_deny_list_is_read_from_a_comma_separated_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EGRESS_DENY_ATTRIBUTES", "stopper_material, special_scale,")
    monkeypatch.setenv("NODE_SIGNING_KEY_FILE", str(tmp_path / "k.pem"))
    monkeypatch.setenv("NODE_SIGNING_KID", "k")

    settings = NodeSettings(_env_file=None)  # type: ignore[call-arg]

    assert settings.egress_deny_attributes == {"stopper_material", "special_scale"}


def test_secrets_never_show_in_repr(tmp_path: Path) -> None:
    configured = NodeSettings(
        _env_file=None,  # type: ignore[call-arg]
        node_signing_key_file=tmp_path / "k.pem",
        node_signing_kid="k",
        anthropic_api_key="sk-ant-secret",
        node_seed_password="hunter2",
    )

    assert "sk-ant-secret" not in repr(configured)
    assert "hunter2" not in repr(configured)


def test_defaults_follow_the_architecture(settings: NodeSettings) -> None:
    assert settings.requirement_rate_limit_per_hour == 120
    assert settings.assertion_rate_limit_per_hour == 30
    assert settings.share_product_hints is False
    assert settings.normalize_batch_size == 25


def test_an_empty_ui_dir_means_no_app(settings: NodeSettings) -> None:
    configured = NodeSettings.model_validate(
        settings.model_dump() | {"purchaser_ui_dir": "", "_env_file": None}
    )
    assert configured.purchaser_ui_dir is None
    assert configured.hub_url == "http://127.0.0.1:8000"

import sys
from pathlib import Path

import jinja2
import pytest

from llm_client import render

# The fixture package lives next to this file; tests run with --import-mode=importlib.
sys.path.insert(0, str(Path(__file__).parent))


def test_render_reads_the_package_prompt() -> None:
    text = render("prompts_pkg", "greeting_v1.j2", name="Anna", items=["a", "b"])

    assert text == "Hello Anna!\n- a\n- b\n"


def test_a_missing_variable_is_an_error() -> None:
    with pytest.raises(jinja2.UndefinedError):
        render("prompts_pkg", "greeting_v1.j2", name="Anna")

"""Scaffold smoke test: the app factory imports and builds."""

import pytest

from skillcoach_api.main import create_app

pytestmark = [pytest.mark.foundations, pytest.mark.smoke]


def test_app_boots() -> None:
    app = create_app()
    assert app.title == "Skill Coach API"

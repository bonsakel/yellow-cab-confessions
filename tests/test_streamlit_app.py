"""Headless smoke tests for every Streamlit entry point."""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_ROOT))
APP_SCRIPTS = [
    APP_ROOT / "Home.py",
    *sorted((APP_ROOT / "pages").glob("*.py")),
]


@pytest.mark.parametrize("script", APP_SCRIPTS, ids=lambda path: path.stem)
def test_streamlit_page_renders_without_exceptions(script: Path) -> None:
    """Run each page once without a browser and assert it has no runtime errors."""
    app = AppTest.from_file(str(script), default_timeout=30).run()
    assert not app.exception, "\n".join(str(error.message) for error in app.exception)


def test_night_playback_button_starts_autoplay() -> None:
    """Verify that the Night City play control switches to its pause state."""
    app = AppTest.from_file(
        str(APP_ROOT / "pages" / "5_A_Night_in_the_City.py"),
        default_timeout=30,
    ).run()
    app.button[0].click().run()
    assert any("Pause playback" in button.label for button in app.button)
    assert not app.exception, "\n".join(str(error.message) for error in app.exception)

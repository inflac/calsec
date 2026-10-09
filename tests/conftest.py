"""Shared fixtures for GUI tests.

GUI modules import each other as top-level modules (``import theme``,
``from ui.month_view import ...``), so GUI tests import them the same way to
work on the same module objects the app uses.
"""
import tkinter as tk

import pytest


def new_tk(**kwargs) -> tk.Tk:
    """Create a Tk interpreter, skipping the test if there is no display.

    On Windows, creating many Tk interpreters in one process occasionally fails
    to find init.tcl, so tests share one interpreter and retry here.
    """
    last = None
    for _ in range(3):
        try:
            return tk.Tk(**kwargs)
        except tk.TclError as exc:
            last = exc
    pytest.skip(f"no display available: {last}")


@pytest.fixture(scope="session")
def _tk_interpreter():
    root = new_tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture()
def tk_root(_tk_interpreter):
    """A fresh, visible, themed top-level window for one test, UI in English."""
    import i18n
    import theme

    i18n.load("en")
    win = tk.Toplevel(_tk_interpreter)
    win.geometry("+0+0")
    theme.apply(win, "dark")
    win.update()
    yield win
    try:
        win.destroy()
    except tk.TclError:
        pass


@pytest.fixture()
def no_settings_file(monkeypatch):
    """Keep settings in memory only, so tests never write the real settings file."""
    import settings

    monkeypatch.setattr(settings, "save", lambda: None)
    monkeypatch.setattr(settings, "_current", dict(settings._DEFAULTS))
    return settings


class FakeEvent:
    """Minimal stand-in for a Tk event passed to handlers directly."""

    def __init__(self, x=0, y=0, x_root=0, y_root=0):
        self.x, self.y, self.x_root, self.y_root = x, y, x_root, y_root

import pytest
from unittest import mock

import gui.main as main_module


# ---------- Global GUI kill ----------

@pytest.fixture(autouse=True)
def no_gui(monkeypatch):
    import tkinter

    monkeypatch.setattr(tkinter, "Tk", lambda *_, **__: mock.Mock())
    monkeypatch.setattr(main_module.messagebox, "showerror", lambda *_, **__: None)
    monkeypatch.setattr(main_module.messagebox, "showinfo",  lambda *_, **__: None)
    monkeypatch.setattr(main_module, "settings", mock.Mock())
    monkeypatch.setattr(main_module, "theme",    mock.Mock())


@pytest.fixture
def app_class(monkeypatch):
    monkeypatch.setattr(main_module.Application, "_start", lambda self: None)
    return main_module.Application


# ---------- Application ----------

def test_application_init(app_class):
    app = app_class()
    assert app is not None


def test_toggle_theme(monkeypatch, app_class):
    monkeypatch.setattr(main_module.settings, "get", lambda key: "dark")
    monkeypatch.setattr(main_module.settings, "set", lambda k, v: None)
    monkeypatch.setattr(main_module.theme,    "apply", lambda *a: None)

    # Patch MainWindow so _toggle_theme doesn't need a real CalendarApp
    monkeypatch.setattr(main_module, "MainWindow", lambda *a, **k: mock.Mock())

    app = app_class()
    app._logged_in_app = mock.Mock()  # CalendarApp mock
    app._switch_to = mock.Mock()

    app._toggle_theme()

    app._switch_to.assert_called()


# ---------- LoginFrame helpers ----------

def _make_login_frame(on_login=None):
    """
    Bypass LoginFrame.__init__ (requires a real tkinter parent).
    Only the _submit() logic is under test here.
    """
    frame = object.__new__(main_module.LoginFrame)
    frame._on_login = on_login or (lambda _: None)
    frame._pw_entry = mock.Mock()
    frame._error_var = mock.Mock()
    return frame


# ---------- LoginFrame ----------

def test_login_wrong_password(monkeypatch):
    monkeypatch.setattr(main_module, "load_private_key",
                        mock.Mock(side_effect=ValueError("bad pw")))

    frame = _make_login_frame()
    frame._pw_entry.get.return_value = "wrong"

    frame._submit()

    frame._error_var.set.assert_called_with("Wrong password.")
    frame._pw_entry.delete.assert_called_with(0, "end")


def test_login_file_not_found(monkeypatch):
    monkeypatch.setattr(main_module, "load_private_key",
                        mock.Mock(side_effect=FileNotFoundError("missing")))

    frame = _make_login_frame()
    frame._pw_entry.get.return_value = "pw"

    frame._submit()

    frame._error_var.set.assert_called_with("missing")


def test_login_success(monkeypatch):
    fake_key = object()
    monkeypatch.setattr(main_module, "load_private_key",
                        mock.Mock(return_value=fake_key))
    monkeypatch.setattr(main_module, "CalendarApp",
                        mock.Mock(return_value="APP"))

    called = {}

    frame = _make_login_frame(on_login=lambda app: called.__setitem__("app", app))
    frame._pw_entry.get.return_value = "correct"

    frame._submit()

    assert called["app"] == "APP"

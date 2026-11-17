from pathlib import Path

from streamlit.testing.v1 import AppTest

from splitsmart.store import Ledger


def widget(items, label):
    return next(item for item in items if item.label == label)


def test_create_group_add_and_record(tmp_path, monkeypatch):
    path = tmp_path / "ui.sqlite"
    monkeypatch.setenv("SPLITSMART_DB", str(path))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    assert not app.exception
    widget(app.button, "New group").click().run()
    widget(app.text_input, "Group name").set_value("House")
    widget(app.text_area, "Members").set_value("Alice\nBob")
    widget(app.button, "Create group").click().run()
    assert not app.exception
    db = Ledger(path)
    gid = next(k for k, v in db.groups().items() if v == "House")
    widget(app.button, "Add expense").click().run()
    widget(app.text_input, "Description").set_value("Dinner")
    widget(app.text_input, "Amount ($)").set_value("20")
    widget(app.button, "Save expense").click().run()
    assert not app.exception
    assert db.snapshot(gid)[1][0]["shares"] == {"Alice": 1000, "Bob": 1000}
    widget(app.button, "Record payment").click().run()
    widget(app.button, "Save payment").click().run()
    assert not app.exception
    assert db.snapshot(gid)[2][0]["amount"] == 1000


def test_invalid_custom_split_then_edit_and_delete(tmp_path, monkeypatch):
    path = tmp_path / "edit.sqlite"
    monkeypatch.setenv("SPLITSMART_DB", str(path))
    db = Ledger(path)
    gid = db.create_group("Roommates", ["Alice", "Bob", "Charlie"])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    widget(app.selectbox, "Current group").set_value(gid).run()
    widget(app.button, "Add expense").click().run()
    widget(app.radio, "Split method").set_value("Custom").run()
    widget(app.text_input, "Description").set_value("Groceries")
    widget(app.text_input, "Amount ($)").set_value("15")
    for member, value in [("Alice", "5"), ("Bob", "4"), ("Charlie", "5")]:
        widget(app.text_input, f"{member}’s share ($)").set_value(value)
    widget(app.button, "Save expense").click().run()
    assert "Shares total $14.00" in app.error[0].value
    assert db.snapshot(gid)[1] == []
    widget(app.text_input, "Bob’s share ($)").set_value("5")
    widget(app.button, "Save expense").click().run()
    widget(app.button, "Edit expense").click().run()
    widget(app.text_input, "Description").set_value("Groceries and snacks")
    widget(app.button, "Save changes").click().run()
    assert db.snapshot(gid)[1][0]["title"] == "Groceries and snacks"
    widget(app.button, "Edit expense").click().run()
    widget(app.button, "Confirm deletion").click().run()
    assert not app.exception
    assert db.snapshot(gid)[1] == []
    assert len(db.snapshot(gid)[3]) == 3

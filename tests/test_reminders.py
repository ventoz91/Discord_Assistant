import time

import pytest

import chatbotfunc.reminders as rem


@pytest.fixture(autouse=True)
def temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(rem, "_REMINDERS_PATH", str(tmp_path / "reminders.json"))


class TestParseDuration:
    def test_simple_units(self):
        assert rem.parse_duration("30m") == 1800
        assert rem.parse_duration("2h") == 7200
        assert rem.parse_duration("1d") == 86400
        assert rem.parse_duration("1w") == 604800
        assert rem.parse_duration("45s") == 45

    def test_compound(self):
        assert rem.parse_duration("1h30m") == 5400
        assert rem.parse_duration("1d2h") == 93600

    def test_case_and_whitespace(self):
        assert rem.parse_duration("2H") == 7200
        assert rem.parse_duration(" 30m ") == 1800

    def test_invalid(self):
        assert rem.parse_duration("soon") is None
        assert rem.parse_duration("") is None
        assert rem.parse_duration(None) is None
        assert rem.parse_duration("10") is None
        assert rem.parse_duration("h") is None
        assert rem.parse_duration("2x") is None
        assert rem.parse_duration("2h later") is None

    def test_zero_rejected(self):
        assert rem.parse_duration("0m") is None


class TestFormatDuration:
    def test_two_largest_units(self):
        assert rem.format_duration(5400) == "1h30m"
        assert rem.format_duration(90061) == "1d1h"
        assert rem.format_duration(45) == "45s"


class TestStore:
    def test_add_and_list(self):
        rem.add_reminder(1, 100, "Knova", 3600, "check oven")
        rem.add_reminder(1, 200, "Ventoz", 60, "stretch")
        assert len(rem.list_reminders()) == 2
        mine = rem.list_reminders(user_id=100)
        assert len(mine) == 1 and mine[0]["text"] == "check oven"

    def test_list_sorted_soonest_first(self):
        rem.add_reminder(1, 100, "K", 7200, "later")
        rem.add_reminder(1, 100, "K", 60, "sooner")
        assert [r["text"] for r in rem.list_reminders()] == ["sooner", "later"]

    def test_cancel_own_only(self):
        r = rem.add_reminder(1, 100, "K", 3600, "mine")
        assert rem.cancel_reminder(r["id"], 999) is None
        assert rem.cancel_reminder(r["id"], 100)["text"] == "mine"
        assert rem.list_reminders() == []

    def test_pop_due_removes_and_returns(self):
        rem.add_reminder(1, 100, "K", 10, "future")
        overdue = rem.add_reminder(1, 100, "K", 10, "past")
        # Force one into the past
        data = rem._load()
        for r in data["reminders"]:
            if r["id"] == overdue["id"]:
                r["due_ts"] = int(time.time()) - 5
        rem._save(data)

        due = rem.pop_due()
        assert [r["text"] for r in due] == ["past"]
        assert [r["text"] for r in rem.list_reminders()] == ["future"]

    def test_ids_monotonic_across_operations(self):
        a = rem.add_reminder(1, 100, "K", 60, "a")
        rem.cancel_reminder(a["id"], 100)
        b = rem.add_reminder(1, 100, "K", 60, "b")
        assert b["id"] == a["id"] + 1

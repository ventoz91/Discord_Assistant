import json

import pytest

import chatbotfunc.profiles as profiles


@pytest.fixture(autouse=True)
def temp_profile_store(tmp_path, monkeypatch):
    store = tmp_path / "user_profiles.json"
    monkeypatch.setattr(profiles, "_PROFILE_PATH", str(store))
    store.write_text(json.dumps({
        "111": {"display_name": "Knova", "facts": ["likes mushrooms", "plays modded minecraft"], "last_updated": 0},
    }))
    yield store


class TestGetFacts:
    def test_returns_facts(self):
        assert profiles.get_facts(111) == ["likes mushrooms", "plays modded minecraft"]

    def test_unknown_user_empty(self):
        assert profiles.get_facts(999) == []


class TestDeleteFact:
    def test_deletes_by_one_based_index(self, temp_profile_store):
        removed = profiles.delete_fact(111, 1)
        assert removed == "likes mushrooms"
        assert profiles.get_facts(111) == ["plays modded minecraft"]

    def test_out_of_range_returns_none(self):
        assert profiles.delete_fact(111, 5) is None
        assert profiles.delete_fact(111, 0) is None
        assert len(profiles.get_facts(111)) == 2


class TestClearFacts:
    def test_clears_and_reports_count(self):
        assert profiles.clear_facts(111) == 2
        assert profiles.get_facts(111) == []

    def test_unknown_user_zero(self):
        assert profiles.clear_facts(999) == 0

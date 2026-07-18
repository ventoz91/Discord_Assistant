import datetime

from chatbotfunc.morning_paper import should_post, _channel_ids


def _at(hour):
    return datetime.datetime(2026, 7, 18, hour, 30)


class TestShouldPost:
    def test_before_hour_no(self):
        assert not should_post(_at(8), 9, None)

    def test_at_hour_never_posted_yes(self):
        assert should_post(_at(9), 9, None)

    def test_after_hour_yes(self):
        assert should_post(_at(15), 9, None)

    def test_already_posted_today_no(self):
        assert not should_post(_at(10), 9, "2026-07-18")

    def test_posted_yesterday_yes(self):
        assert should_post(_at(10), 9, "2026-07-17")


class TestChannelIds:
    def test_unset_means_disabled(self, monkeypatch):
        monkeypatch.delenv("MORNING_PAPER_CHANNEL_IDS", raising=False)
        assert _channel_ids() == []

    def test_comma_list(self, monkeypatch):
        monkeypatch.setenv("MORNING_PAPER_CHANNEL_IDS", "123, 456,789")
        assert _channel_ids() == [123, 456, 789]

from chatbotfunc.safearr_report import format_report

URL = "http://10.13.37.100:8383"


def test_empty_queue_posts_nothing():
    assert format_report({"reviewing": 0, "intaking": 2}, URL) is None
    assert format_report({}, URL) is None


def test_counts_titles_flags_and_age():
    text = format_report({
        "reviewing": 5, "flagged": 1, "oldest_quarantined_at": 1000.0,
        "by_title": {"Pokémon": 4, "Bluey (2018)": 1},
    }, URL, now=1000.0 + 3 * 86400)
    assert text == (
        "🛡️ **SafeArr:** 5 downloads waiting for review\n"
        "Pokémon (4), Bluey (2018) (1)\n"
        "⚠️ 1 flagged as likely wrong file · oldest waiting 3 days\n"
        "<http://10.13.37.100:8383/>"
    )


def test_single_item_and_recent():
    text = format_report({"reviewing": 1, "oldest_quarantined_at": 1000.0, "by_title": {"Up (2009)": 1}},
                         URL + "/", now=1000.0 + 600)
    assert text.splitlines()[0] == "🛡️ **SafeArr:** 1 download waiting for review"
    assert "oldest waiting under an hour" in text
    assert text.endswith("<http://10.13.37.100:8383/>")


def test_long_title_list_is_capped():
    titles = {f"Show {i}": 1 for i in range(10)}
    text = format_report({"reviewing": 10, "by_title": titles}, URL)
    assert "+2 more" in text


def test_posts_when_only_other_things_need_a_human():
    text = format_report({"reviewing": 0, "stuck": [{"path": "/q/a.avi"}], "broken_hardlinks": 2,
                          "adopt_candidates": 1}, URL)
    assert text.splitlines() == [
        "🛡️ **SafeArr:** nothing waiting for review",
        "🧱 1 file is stuck before review (see the dashboard)",
        "🔗 2 approved files are no longer hardlinked: run `safearr relink`",
        "📥 1 title matches a rule but isn't protected yet: <http://10.13.37.100:8383/adopt>",
        "<http://10.13.37.100:8383/>",
    ]


def test_all_clear_posts_nothing():
    assert format_report({"reviewing": 0, "stuck": [], "broken_hardlinks": 0, "adopt_candidates": 0}, URL) is None


def test_stuck_alerts_fire_once_per_file():
    from chatbotfunc.safearr_report import new_stuck_alerts

    summary = {"stuck": [
        {"path": "/q/a.avi", "file": "a.avi", "kind": "decode", "error": "Can't decode the video (rawvideo)"},
        {"path": "/q/b.mkv", "file": "b.mkv", "kind": "other", "error": "ffmpeg timed out after 300s"},
    ]}
    messages, alerted = new_stuck_alerts(summary, {"/q/b.mkv"}, URL)
    assert len(messages) == 1 and "`a.avi` can't be decoded" in messages[0] and "rawvideo" in messages[0]
    assert alerted == {"/q/a.avi", "/q/b.mkv"}

    messages, alerted = new_stuck_alerts({"stuck": []}, alerted, URL)
    assert messages == [] and alerted == set(), "fixed files are forgotten, so a relapse alerts again"

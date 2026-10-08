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

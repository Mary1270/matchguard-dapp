from _bootstrap import make_contract


def test_extract_domain_basic_and_www():
    c = make_contract()
    assert c._extract_domain("https://www.espn.com/soccer/match") == "espn.com"
    assert c._extract_domain("https://espn.com") == "espn.com"


def test_extract_domain_multi_part_suffix():
    c = make_contract()
    assert c._extract_domain("https://www.sportsmole.co.uk/football/x") == "sportsmole.co.uk"


def test_extract_domain_invalid_scheme_returns_empty():
    c = make_contract()
    assert c._extract_domain("ftp://espn.com") == ""
    assert c._extract_domain("espn.com") == ""  # missing scheme


def test_extract_path():
    c = make_contract()
    assert c._extract_path("https://bbc.com/sport/football/12345") == "/sport/football/12345"
    assert c._extract_path("https://bbc.com/sport/") == "/sport"
    assert c._extract_path("https://bbc.com") == ""


def test_parse_endpoint_requirement_forms():
    c = make_contract()
    assert c._parse_endpoint_requirement("bbc.com") == ("bbc.com", "")
    assert c._parse_endpoint_requirement("bbc.com/sport") == ("bbc.com", "/sport")
    assert c._parse_endpoint_requirement("https://bbc.com/sport/football") == ("bbc.com", "/sport/football")


def test_check_required_domains_covered():
    c = make_contract()
    annotated = c._annotate_sources(
        ["https://www.espn.com/match/1", "https://bbc.com/sport/football/9"]
    )
    missing = c._check_required_domains_covered(["espn.com", "bbc.com/sport"], annotated)
    assert missing == []

    missing = c._check_required_domains_covered(["espn.com", "bbc.com/cricket"], annotated)
    assert missing == ["bbc.com/cricket"]


def test_annotate_sources_flags_duplicates_and_reputability():
    c = make_contract()
    annotated = c._annotate_sources(
        [
            "https://espn.com/a",
            "https://www.espn.com/b",   # same registrable domain -> duplicate
            "https://randomblog.com/c",  # not reputable
            "not-a-url",                 # invalid scheme
        ]
    )
    assert annotated[0]["is_duplicate_domain"] is False
    assert annotated[0]["is_reputable"] is True
    assert annotated[1]["is_duplicate_domain"] is True
    assert annotated[2]["is_reputable"] is False
    assert annotated[3]["valid_scheme"] is False


def test_classify_content_thresholds():
    c = make_contract()
    assert c._classify_content(None) == ("empty", False)
    assert c._classify_content("   ") == ("empty", False)
    assert c._classify_content("too short") == ("malformed", False)
    long_text = "word " * 20
    assert c._classify_content(long_text) == ("ok", True)


def test_parse_word_with_label():
    c = make_contract()
    raw = "EVENT_MATCH: Match\nSTATUS: Final\nRESULT: HomeWin"
    assert c._parse_word(raw, c.EVENT_MATCH_WORDS, "Unclear", label="EVENT_MATCH") == "Match"
    assert c._parse_word(raw, c.STATUS_WORDS, "Unknown", label="STATUS") == "Final"
    assert c._parse_word(raw, c.RESULT_WORDS, "Unclear", label="RESULT") == "HomeWin"


def test_parse_word_defaults_on_garbage():
    c = make_contract()
    assert c._parse_word("nonsense response", c.STATUS_WORDS, "Unknown", label="STATUS") == "Unknown"
    assert c._parse_word("", c.STATUS_WORDS, "Unknown", label="STATUS") == "Unknown"

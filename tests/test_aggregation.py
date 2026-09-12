from _bootstrap import make_contract


def rec(domain, status, result="Unclear", quality_flag="ok", is_duplicate=False, is_reputable=True):
    return {
        "domain": domain,
        "status": status,
        "result": result,
        "quality_flag": quality_flag,
        "is_duplicate_domain": is_duplicate,
        "is_reputable": is_reputable,
    }


def test_two_agreeing_sources_final_home_win():
    c = make_contract()
    records = [
        rec("espn.com", "Final", "HomeWin"),
        rec("bbc.com", "Final", "HomeWin"),
    ]
    assert c._aggregate_verdict(records) == "HomeWin"


def test_single_eligible_source_is_indeterminate():
    c = make_contract()
    records = [rec("espn.com", "Final", "HomeWin")]
    assert c._aggregate_verdict(records) == "Indeterminate"


def test_three_way_status_tie_is_disputed():
    c = make_contract()
    records = [
        rec("espn.com", "Final", "HomeWin"),
        rec("bbc.com", "Postponed"),
        rec("reuters.com", "Cancelled"),
    ]
    # No status category has a strict pairwise majority (1-1-1).
    assert c._aggregate_verdict(records) == "Disputed"


def test_final_status_majority_but_result_split_is_disputed():
    c = make_contract()
    records = [
        rec("espn.com", "Final", "HomeWin"),
        rec("bbc.com", "Final", "AwayWin"),
        rec("reuters.com", "Final", "Draw"),
    ]
    # All three sources agree the match is Final (3-0-0-0 on status),
    # but the RESULT itself is a genuine 3-way split - Disputed, not
    # a coin-flip guess.
    assert c._aggregate_verdict(records) == "Disputed"


def test_result_majority_wins_over_lone_dissenter():
    c = make_contract()
    records = [
        rec("espn.com", "Final", "AwayWin"),
        rec("bbc.com", "Final", "AwayWin"),
        rec("reuters.com", "Final", "HomeWin"),
    ]
    assert c._aggregate_verdict(records) == "AwayWin"


def test_postponed_majority():
    c = make_contract()
    records = [
        rec("espn.com", "Postponed"),
        rec("bbc.com", "Postponed"),
        rec("reuters.com", "Final", "HomeWin"),
    ]
    assert c._aggregate_verdict(records) == "Postponed"


def test_duplicate_domain_excluded_from_eligibility():
    c = make_contract()
    records = [
        rec("espn.com", "Final", "HomeWin"),
        rec("espn.com", "Final", "HomeWin", is_duplicate=True),
    ]
    # Only ONE distinct domain actually counts - below MIN_INDEPENDENT_SOURCES.
    eligible = [r for r in records if r["quality_flag"] == "ok"]
    # The aggregate function itself only looks at quality_flag=="ok"
    # entries' domains; is_duplicate_domain must already have been
    # reflected upstream as quality_flag != "ok" by the pipeline, but
    # exercise the domain-counting behavior directly here too:
    assert len({r["domain"] for r in eligible}) == 1
    assert c._aggregate_verdict(records) == "Indeterminate"


def test_non_ok_quality_flag_excluded():
    c = make_contract()
    records = [
        rec("espn.com", "Final", "HomeWin"),
        rec("bbc.com", "Final", "HomeWin", quality_flag="event_mismatch"),
        rec("reuters.com", "Final", "HomeWin"),
    ]
    assert c._aggregate_verdict(records) == "HomeWin"


def test_settlement_from_verdict_home_and_away():
    c = make_contract()
    assert c._settlement_from_verdict("HomeWin", "home") == "party_a_wins"
    assert c._settlement_from_verdict("HomeWin", "away") == "party_b_wins"
    assert c._settlement_from_verdict("AwayWin", "away") == "party_a_wins"
    assert c._settlement_from_verdict("AwayWin", "home") == "party_b_wins"


def test_settlement_from_verdict_always_refunds_non_decisive_states():
    c = make_contract()
    for verdict in ("Draw", "Postponed", "Cancelled", "Abandoned", "Disputed", "Indeterminate"):
        assert c._settlement_from_verdict(verdict, "home") == "refund"
        assert c._settlement_from_verdict(verdict, "away") == "refund"

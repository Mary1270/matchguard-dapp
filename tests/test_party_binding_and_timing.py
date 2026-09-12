import datetime
import json

import pytest

from _bootstrap import (
    make_contract, set_caller, iso, now_utc, default_timing,
    create_default_match, DEFAULT_REQUIRED_DOMAINS,
    PARTY_A_ADDRESS, PARTY_B_ADDRESS, STRANGER_ADDRESS,
)
from genlayer import gl


def test_create_match_binds_caller_as_party_a():
    c = make_contract()
    match_id = create_default_match(c)
    match = json.loads(c.get_match(match_id))
    assert match["party_a"].lower() == PARTY_A_ADDRESS.lower()
    assert match["party_b"].lower() == PARTY_B_ADDRESS.lower()
    assert match["status"] == "pending_acceptance"


def test_party_b_cannot_equal_party_a():
    c = make_contract()
    with pytest.raises(gl.vm.UserError):
        create_default_match(c, party_b_address=PARTY_A_ADDRESS)


def test_side_a_must_be_home_or_away():
    c = make_contract()
    with pytest.raises(gl.vm.UserError):
        create_default_match(c, side_a="draw")


def test_teams_must_be_distinct():
    c = make_contract()
    with pytest.raises(gl.vm.UserError):
        create_default_match(c, away_team="Alpha FC")


def test_scheduled_start_must_have_minimum_lead_time():
    c = make_contract()
    too_soon = iso(now_utc() + datetime.timedelta(minutes=5))
    deadline = iso(now_utc() + datetime.timedelta(hours=3))
    with pytest.raises(gl.vm.UserError):
        create_default_match(c, scheduled_start=too_soon, resolution_deadline=deadline)


def test_scheduled_start_must_not_be_too_far_out():
    c = make_contract()
    too_far = iso(now_utc() + datetime.timedelta(days=30))
    deadline = iso(now_utc() + datetime.timedelta(days=30, hours=2))
    with pytest.raises(gl.vm.UserError):
        create_default_match(c, scheduled_start=too_far, resolution_deadline=deadline)


def test_resolution_deadline_must_be_pinned_to_scheduled_start():
    c = make_contract()
    start = now_utc() + datetime.timedelta(hours=3)
    # deadline only 5 minutes after kickoff - below MIN_MATCH_DURATION_SECONDS
    too_tight = iso(start + datetime.timedelta(minutes=5))
    with pytest.raises(gl.vm.UserError):
        create_default_match(c, scheduled_start=iso(start), resolution_deadline=too_tight)

    # deadline 2 days after kickoff - above MAX_MATCH_DURATION_BUFFER_SECONDS
    too_late = iso(start + datetime.timedelta(days=2))
    with pytest.raises(gl.vm.UserError):
        create_default_match(c, scheduled_start=iso(start), resolution_deadline=too_late)


def test_required_source_domains_validation():
    c = make_contract()
    # too few
    with pytest.raises(gl.vm.UserError):
        create_default_match(c, required_source_domains=["espn.com"])
    # unreputable domain
    with pytest.raises(gl.vm.UserError):
        create_default_match(c, required_source_domains=["espn.com", "randomblog.com"])
    # duplicate domain
    with pytest.raises(gl.vm.UserError):
        create_default_match(c, required_source_domains=["espn.com", "espn.com"])


def test_accept_match_requires_exact_party_b():
    c = make_contract()
    match_id = create_default_match(c)
    set_caller(STRANGER_ADDRESS)
    with pytest.raises(gl.vm.UserError):
        c.accept_match(match_id)

    set_caller(PARTY_B_ADDRESS)
    match = json.loads(c.accept_match(match_id))
    assert match["status"] == "open"
    assert match["accepted_at"] is not None


def test_accept_match_fails_after_scheduled_start():
    c = make_contract()
    start = now_utc() + datetime.timedelta(hours=2)
    deadline = start + datetime.timedelta(hours=2)
    match_id = create_default_match(c, scheduled_start=iso(start), resolution_deadline=iso(deadline))

    # Simulate time passing by rewriting scheduled_start into the past
    # directly in storage (the stub's clock is real wall-clock time,
    # so we can't sleep hours in a unit test).
    match = json.loads(c.get_match(match_id))
    match["scheduled_start"] = iso(now_utc() - datetime.timedelta(minutes=1))
    c.matches[match_id] = json.dumps(match, sort_keys=True)

    set_caller(PARTY_B_ADDRESS)
    with pytest.raises(gl.vm.UserError):
        c.accept_match(match_id)


def test_cancel_match_only_by_party_a_while_pending():
    c = make_contract()
    match_id = create_default_match(c)

    set_caller(PARTY_B_ADDRESS)
    with pytest.raises(gl.vm.UserError):
        c.cancel_match(match_id)

    set_caller(PARTY_A_ADDRESS)
    match = json.loads(c.cancel_match(match_id))
    assert match["status"] == "cancelled"

    with pytest.raises(gl.vm.UserError):
        c.cancel_match(match_id)  # already cancelled


def test_expire_match_pending_acceptance_requires_scheduled_start_passed():
    c = make_contract()
    match_id = create_default_match(c)
    with pytest.raises(gl.vm.UserError):
        c.expire_match(match_id)  # scheduled_start hasn't passed

    match = json.loads(c.get_match(match_id))
    match["scheduled_start"] = iso(now_utc() - datetime.timedelta(minutes=1))
    c.matches[match_id] = json.dumps(match, sort_keys=True)

    updated = json.loads(c.expire_match(match_id))
    assert updated["status"] == "expired"


def test_get_role():
    c = make_contract()
    match_id = create_default_match(c)
    assert c.get_role(match_id, PARTY_A_ADDRESS) == "party_a"
    assert c.get_role(match_id, PARTY_B_ADDRESS) == "party_b"
    assert c.get_role(match_id, STRANGER_ADDRESS) == "none"


def test_total_matches_increments():
    c = make_contract()
    assert c.total_matches() == 0
    create_default_match(c)
    assert c.total_matches() == 1
    create_default_match(c)
    assert c.total_matches() == 2

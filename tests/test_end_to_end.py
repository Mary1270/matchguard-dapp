"""
End-to-end tests of the propose_resolution / challenge_resolution /
finalize_match / expire_match lifecycle. gl.nondet.web.render and
gl.nondet.exec_prompt are mocked to simulate specific per-domain
source content and LLM extraction responses; every other step
(fetching, prompt construction, deterministic aggregation, locking,
versioning, settlement mapping) runs for real through contract.py.
"""
import datetime
import json
import unittest
from unittest.mock import patch

from _bootstrap import (
    PARTY_A_ADDRESS,
    PARTY_B_ADDRESS,
    STRANGER_ADDRESS,
    gl,
    make_contract,
    set_caller,
)


def iso_in(seconds_from_now: float) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds_from_now)
    return dt.isoformat()


def create_and_accept(c, side_a="home", required_source_domains=None):
    required_source_domains = required_source_domains or ["espn.com", "bbc.com"]
    set_caller(PARTY_A_ADDRESS)
    start_offset = c.MIN_DEADLINE_LEAD_SECONDS + 5
    mid = c.MIN_MATCH_DURATION_SECONDS + 60
    match_id = c.create_match(
        party_b_address=PARTY_B_ADDRESS,
        sport="Football",
        competition="Premier League",
        home_team="Alpha FC",
        away_team="Beta United",
        scheduled_start=iso_in(start_offset),
        side_a=side_a,
        resolution_deadline=iso_in(start_offset + mid),
        description="End-to-end test match",
        required_source_domains=required_source_domains,
    )
    set_caller(PARTY_B_ADDRESS)
    c.accept_match(match_id)

    # Fast-forward past resolution_deadline without waiting in real
    # time, by rewriting stored timestamps directly - the same
    # technique used by the sibling project's test suite.
    record = json.loads(c.matches[match_id])
    record["scheduled_start"] = iso_in(-start_offset)
    record["resolution_deadline"] = iso_in(-5)
    record["resolution_window_closes_at"] = iso_in(c.RESOLUTION_WINDOW_SECONDS)
    c.matches[match_id] = json.dumps(record, sort_keys=True)
    return match_id


# ---------------------------------------------------------------------
# Per-domain fixture content, and the LLM response the mock derives
# from it (mirroring what a real model would extract).
# ---------------------------------------------------------------------
CONTENT = {
    "home_win_final": "Alpha FC beat Beta United 2-1 in the full-time final result of this Premier League match.",
    "away_win_final": "Beta United beat Alpha FC 3-0 in the full-time final result of this Premier League match.",
    "draw_final": "Alpha FC and Beta United played out a 1-1 draw, the full-time final result of this Premier League match.",
    "postponed": "This Premier League match between Alpha FC and Beta United has been postponed due to a waterlogged pitch.",
    "live": "LIVE 55': Alpha FC lead Beta United 1-0 as the match continues in this Premier League fixture.",
    "wrong_fixture": "Chelsea beat Arsenal 4-2 in the full-time final result of today's Premier League match.",
    "garbage": "asdkj q3lkj asd q3lkj",
}


def llm_response_for(content: str) -> str:
    if content == CONTENT["home_win_final"]:
        return "EVENT_MATCH: Match\nSTATUS: Final\nRESULT: HomeWin"
    if content == CONTENT["away_win_final"]:
        return "EVENT_MATCH: Match\nSTATUS: Final\nRESULT: AwayWin"
    if content == CONTENT["draw_final"]:
        return "EVENT_MATCH: Match\nSTATUS: Final\nRESULT: Draw"
    if content == CONTENT["postponed"]:
        return "EVENT_MATCH: Match\nSTATUS: Postponed\nRESULT: Unclear"
    if content == CONTENT["live"]:
        return "EVENT_MATCH: Match\nSTATUS: Live\nRESULT: Unclear"
    if content == CONTENT["wrong_fixture"]:
        return "EVENT_MATCH: Mismatch\nSTATUS: Final\nRESULT: AwayWin"
    return "EVENT_MATCH: Unclear\nSTATUS: Unknown\nRESULT: Unclear"


def mock_sources(url_to_content_key: dict):
    """Return (render_patch_kwargs, exec_prompt_patch_kwargs) that make
    gl.nondet.web.render return the configured content per-URL, and
    gl.nondet.exec_prompt derive its response from that same content -
    exactly like a real fetch+LLM pipeline would, but offline."""

    def render(url, mode="text"):
        return CONTENT[url_to_content_key[url]]

    def exec_prompt(prompt, response_format="text"):
        # The prompt embeds the (truncated) source content; recover
        # which fixture content this call is about by checking
        # membership, since the mock has no other way to know which
        # URL is currently being processed.
        for key, content in CONTENT.items():
            if content[:50] in prompt:
                return llm_response_for(content)
        return "EVENT_MATCH: Unclear\nSTATUS: Unknown\nRESULT: Unclear"

    return render, exec_prompt


class ProposeResolutionTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_two_agreeing_sources_home_win_party_a_wins(self):
        match_id = create_and_accept(self.c, side_a="home")
        urls = {"https://espn.com/x": "home_win_final", "https://bbc.com/sport/x": "home_win_final"}
        render, exec_prompt = mock_sources(urls)
        with patch.object(gl.nondet.web, "render", side_effect=render), \
             patch.object(gl.nondet, "exec_prompt", side_effect=exec_prompt):
            result = json.loads(self.c.propose_resolution(match_id, list(urls.keys())))

        self.assertEqual(result["status"], "proposed")
        self.assertEqual(result["proposed_verdict"], "HomeWin")
        self.assertEqual(result["proposed_settlement"], "party_a_wins")
        self.assertEqual(result["version"], 1)
        self.assertIsNotNone(result["locked_source_urls"])
        self.assertEqual(len(result["resolution_history"]), 1)
        self.assertEqual(result["resolution_history"][0]["trigger"], "proposed")

    def test_away_win_when_side_a_is_home_means_party_b_wins(self):
        match_id = create_and_accept(self.c, side_a="home")
        urls = {"https://espn.com/x": "away_win_final", "https://bbc.com/sport/x": "away_win_final"}
        render, exec_prompt = mock_sources(urls)
        with patch.object(gl.nondet.web, "render", side_effect=render), \
             patch.object(gl.nondet, "exec_prompt", side_effect=exec_prompt):
            result = json.loads(self.c.propose_resolution(match_id, list(urls.keys())))
        self.assertEqual(result["proposed_verdict"], "AwayWin")
        self.assertEqual(result["proposed_settlement"], "party_b_wins")

    def test_draw_stays_open_for_challenge_but_provisionally_refunds(self):
        match_id = create_and_accept(self.c, side_a="home")
        urls = {"https://espn.com/x": "draw_final", "https://bbc.com/sport/x": "draw_final"}
        render, exec_prompt = mock_sources(urls)
        with patch.object(gl.nondet.web, "render", side_effect=render), \
             patch.object(gl.nondet, "exec_prompt", side_effect=exec_prompt):
            result = json.loads(self.c.propose_resolution(match_id, list(urls.keys())))
        self.assertEqual(result["proposed_verdict"], "Draw")
        self.assertEqual(result["proposed_settlement"], "refund")

    def test_missing_required_domain_rejected_before_any_fetch(self):
        match_id = create_and_accept(self.c, required_source_domains=["espn.com", "bbc.com"])
        with self.assertRaises(gl.vm.UserError):
            # Only espn.com submitted - bbc.com (committed at creation) is missing.
            self.c.propose_resolution(match_id, ["https://espn.com/x", "https://nba.com/x"])

    def test_insufficient_evidence_leaves_match_open_and_retryable(self):
        match_id = create_and_accept(self.c)
        # One source mismatched, one live - neither clears the bar.
        urls = {"https://espn.com/x": "wrong_fixture", "https://bbc.com/sport/x": "live"}
        render, exec_prompt = mock_sources(urls)
        with patch.object(gl.nondet.web, "render", side_effect=render), \
             patch.object(gl.nondet, "exec_prompt", side_effect=exec_prompt):
            result = json.loads(self.c.propose_resolution(match_id, list(urls.keys())))

        self.assertEqual(result["status"], "open")
        self.assertIsNone(result["locked_source_urls"])
        self.assertEqual(result["resolution_history"], [])

        # Retry with better URLs - still permitted, no poisoning occurred.
        urls2 = {"https://espn.com/x": "home_win_final", "https://bbc.com/sport/x": "home_win_final"}
        render2, exec_prompt2 = mock_sources(urls2)
        with patch.object(gl.nondet.web, "render", side_effect=render2), \
             patch.object(gl.nondet, "exec_prompt", side_effect=exec_prompt2):
            result2 = json.loads(self.c.propose_resolution(match_id, list(urls2.keys())))
        self.assertEqual(result2["status"], "proposed")
        self.assertEqual(result2["proposed_verdict"], "HomeWin")

    def test_lone_dissenting_source_does_not_block_majority(self):
        match_id = create_and_accept(self.c, required_source_domains=["espn.com", "bbc.com", "reuters.com"])
        urls = {
            "https://espn.com/x": "home_win_final",
            "https://bbc.com/sport/x": "home_win_final",
            "https://reuters.com/x": "away_win_final",
        }
        render, exec_prompt = mock_sources(urls)
        with patch.object(gl.nondet.web, "render", side_effect=render), \
             patch.object(gl.nondet, "exec_prompt", side_effect=exec_prompt):
            result = json.loads(self.c.propose_resolution(match_id, list(urls.keys())))
        self.assertEqual(result["proposed_verdict"], "HomeWin")
        self.assertEqual(result["last_attempt_independent_source_count"], 3)


class ChallengeAndFinalizeTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def _propose_home_win(self, match_id):
        urls = {"https://espn.com/x": "home_win_final", "https://bbc.com/sport/x": "home_win_final"}
        render, exec_prompt = mock_sources(urls)
        with patch.object(gl.nondet.web, "render", side_effect=render), \
             patch.object(gl.nondet, "exec_prompt", side_effect=exec_prompt):
            return json.loads(self.c.propose_resolution(match_id, list(urls.keys())))

    def test_only_parties_may_challenge(self):
        match_id = create_and_accept(self.c)
        self._propose_home_win(match_id)
        set_caller(STRANGER_ADDRESS)
        with self.assertRaises(gl.vm.UserError):
            self.c.challenge_resolution(match_id, "https://reuters.com/x", "not a party")

    def test_successful_challenge_flips_verdict_and_versions_up(self):
        # required_source_domains only constrains propose_resolution's
        # coverage requirement; challenge_resolution may add further
        # reputable sources beyond that committed set.
        match_id = create_and_accept(self.c)

        # The initial proposal itself is a genuine 1-1 split, so it
        # posts provisionally as "Disputed" (refund) - Two-Phase
        # Resolution (pillar 4) means even a non-decisive first
        # proposal still opens a real challenge window rather than
        # refunding immediately.
        initial_urls = {"https://espn.com/x": "home_win_final", "https://bbc.com/sport/x": "away_win_final"}
        render0, exec_prompt0 = mock_sources(initial_urls)
        with patch.object(gl.nondet.web, "render", side_effect=render0), \
             patch.object(gl.nondet, "exec_prompt", side_effect=exec_prompt0):
            proposed = json.loads(self.c.propose_resolution(match_id, list(initial_urls.keys())))
        self.assertEqual(proposed["proposed_verdict"], "Disputed")
        self.assertEqual(proposed["proposed_settlement"], "refund")

        # party_a challenges with a third, corroborating HomeWin
        # source. Each round re-fetches the WHOLE evidence set (the
        # two already-locked sources plus the new one), so the mock
        # must keep the locked sources' content stable while only the
        # new URL differs.
        set_caller(PARTY_A_ADDRESS)
        round1_urls = {
            "https://espn.com/x": "home_win_final",
            "https://bbc.com/sport/x": "away_win_final",
            "https://reuters.com/x": "home_win_final",
        }
        render1, exec_prompt1 = mock_sources(round1_urls)
        with patch.object(gl.nondet.web, "render", side_effect=render1), \
             patch.object(gl.nondet, "exec_prompt", side_effect=exec_prompt1):
            after_first = json.loads(
                self.c.challenge_resolution(match_id, "https://reuters.com/x", "reuters corroborates HomeWin")
            )
        # 2 HomeWin vs 1 AwayWin now has a strict majority - the
        # verdict CHANGES from Disputed to HomeWin, so this challenge
        # is accepted and the locked evidence set grows to 3.
        self.assertEqual(after_first["proposed_verdict"], "HomeWin")
        self.assertEqual(after_first["proposed_settlement"], "party_a_wins")
        self.assertEqual(after_first["resolution_history"][-1]["trigger"], "challenge_accepted")
        self.assertEqual(after_first["version"], 2)
        self.assertEqual(after_first["challenge_rounds_used"], 1)
        self.assertEqual(len(after_first["locked_source_urls"]), 3)

        # party_b's counter-challenge with one more AwayWin source
        # (2 HomeWin vs 2 AwayWin) is a tie - no strict majority - so
        # the verdict changes again, from HomeWin to Disputed, and
        # this second challenge is ALSO accepted.
        set_caller(PARTY_B_ADDRESS)
        round2_urls = dict(round1_urls)
        round2_urls["https://nba.com/x"] = "away_win_final"
        render2, exec_prompt2 = mock_sources(round2_urls)
        with patch.object(gl.nondet.web, "render", side_effect=render2), \
             patch.object(gl.nondet, "exec_prompt", side_effect=exec_prompt2):
            after_second = json.loads(
                self.c.challenge_resolution(match_id, "https://nba.com/x", "nba says AwayWin too")
            )
        self.assertEqual(after_second["proposed_verdict"], "Disputed")
        self.assertEqual(after_second["proposed_settlement"], "refund")
        self.assertEqual(after_second["resolution_history"][-1]["trigger"], "challenge_accepted")
        self.assertEqual(after_second["version"], 3)
        self.assertEqual(after_second["challenge_rounds_used"], 2)

        # Rounds exhausted (MAX_CHALLENGE_ROUNDS == 2) - a third
        # challenge must be rejected outright, guaranteeing this
        # cannot be dragged out indefinitely.
        with self.assertRaises(gl.vm.UserError):
            self.c.challenge_resolution(match_id, "https://skysports.com/x", "one more try")

    def test_finalize_before_challenge_window_closes_is_rejected(self):
        match_id = create_and_accept(self.c)
        self._propose_home_win(match_id)
        with self.assertRaises(gl.vm.UserError):
            self.c.finalize_match(match_id)

    def test_finalize_after_challenge_window_locks_in_settlement(self):
        match_id = create_and_accept(self.c)
        self._propose_home_win(match_id)

        record = json.loads(self.c.matches[match_id])
        record["challenge_deadline"] = iso_in(-1)
        self.c.matches[match_id] = json.dumps(record, sort_keys=True)

        finalized = json.loads(self.c.finalize_match(match_id))
        self.assertEqual(finalized["status"], "finalized")
        self.assertEqual(finalized["final_verdict"], "HomeWin")
        self.assertEqual(finalized["settlement_outcome"], "party_a_wins")
        self.assertIsNotNone(finalized["resolved_at"])
        self.assertEqual(finalized["resolution_history"][-1]["trigger"], "finalized")

        # Terminal - cannot finalize twice.
        with self.assertRaises(gl.vm.UserError):
            self.c.finalize_match(match_id)


class TimeoutRecoveryTests(unittest.TestCase):
    """Pillar 8: no path through the state machine can permanently
    strand a match without an eventual, permissionless, terminal
    settlement."""

    def setUp(self):
        self.c = make_contract()

    def test_never_proposed_match_expires_after_resolution_window(self):
        match_id = create_and_accept(self.c)
        record = json.loads(self.c.matches[match_id])
        record["resolution_window_closes_at"] = iso_in(-1)
        self.c.matches[match_id] = json.dumps(record, sort_keys=True)

        expired = json.loads(self.c.expire_match(match_id))
        self.assertEqual(expired["status"], "expired")

    def test_indeterminate_proposal_still_finalizes_to_refund(self):
        match_id = create_and_accept(self.c)
        urls = {"https://espn.com/x": "garbage", "https://bbc.com/sport/x": "garbage"}

        def render_fn(url, mode="text"):
            return CONTENT["garbage"]

        def exec_prompt_fn(prompt, response_format="text"):
            return "EVENT_MATCH: Unclear\nSTATUS: Unknown\nRESULT: Unclear"

        with patch.object(gl.nondet.web, "render", side_effect=render_fn), \
             patch.object(gl.nondet, "exec_prompt", side_effect=exec_prompt_fn):
            result = json.loads(self.c.propose_resolution(match_id, list(urls.keys())))

        # Garbage content never clears the evidence bar - stays open,
        # never gets artificially stuck in "proposed" with no exit.
        self.assertEqual(result["status"], "open")

        # Eventually the window closes with no quality-clearing
        # proposal ever landing - permissionless refund path.
        record = json.loads(self.c.matches[match_id])
        record["resolution_window_closes_at"] = iso_in(-1)
        self.c.matches[match_id] = json.dumps(record, sort_keys=True)
        expired = json.loads(self.c.expire_match(match_id))
        self.assertEqual(expired["status"], "expired")


if __name__ == "__main__":
    unittest.main()

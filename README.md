# MatchGuard — Adversarial Sports Event Settlement Intelligent Contract

## Why this project, and why it's a step up from ScoreSettle

ScoreSettle answered one narrow question: "what was the final score?". MatchGuard operates one architectural level higher: it settles the full **state** of a sports event in a disputable, tamper-resistant way — not just the final score, but whether the match was even played, whether it was postponed/cancelled/abandoned, whether sources disagree with each other, and what happens to the stake if no consensus ever forms.

More importantly, MatchGuard directly addresses the one concrete finding Steward raised on ScoreSettle — **premature/first-resolver source locking** — and applies that same lesson a second time, independently, to the challenge mechanism as well.

## Architecture — the eight pillars

1. **Canonical Event Identity** — the fixture is pinned by `sport` + `competition` + `home_team` + `away_team` + `scheduled_start`. Every piece of evidence must clear an `EVENT_MATCH` check confirming it actually covers this exact fixture, not just matching team names.
2. **Locked Source Set, locked only after real evidence** — the direct fix for ScoreSettle's finding: the voting source set is only locked once a resolution attempt actually clears the evidence-quality bar. A failed attempt locks nothing and leaves the match open and retryable.
3. **Two-stage Multi-Source Semantic Consensus** — first a strict-majority vote on STATUS (Final/Postponed/Cancelled/Abandoned), and only if STATUS resolves to Final does a second strict-majority vote run on RESULT. Disagreement at either stage → Disputed; insufficient evidence → Indeterminate.
4. **Two-Phase Optimistic Resolution** — the initial proposal (`propose_resolution`) is always provisional and opens a challenge window, even when the verdict looks decisive.
5. **Evidence-Based Challenge** — a challenge must supply a concrete URL, is restricted to party_a/party_b, is time-bounded, and is capped at a fixed number of rounds.
6. **Result Versioning / Immutable History** — every proposal and every challenge (accepted or rejected) is appended as its own versioned, timestamped entry. Nothing is ever silently rewritten.
7. **Always-Terminal Three-Way Settlement** — only three possible final outcomes: `party_a_wins` / `party_b_wins` / `refund`. Draw, Postponed, Cancelled, Abandoned, Disputed, and Indeterminate all resolve to `refund` — there is never a stuck "pending" state.
8. **Timeout Recovery — no permanent fund lock** — every path through the state machine has a permissionless, time-bounded exit: `expire_match` for a match that was never accepted or never got a quality-clearing proposal, and `finalize_match` for any match that reached "proposed" (even if stuck on Disputed/Indeterminate).

## Comparison with ScoreSettle

| | ScoreSettle | MatchGuard |
|---|---|---|
| Settles | Final score | Full event state (Final/Postponed/Cancelled/Abandoned/Disputed/Indeterminate) |
| Party binding | Address-bound | Address-bound + canonical event binding |
| Timing | One deadline | Independent propose window + challenge window |
| Consensus | Single-pass | Two-stage (status, then result) |
| Result record | Final value | Versioned, immutable history |
| Settlement | Win/Lose | Win/Lose/Refund — always terminal |
| Dispute handling | — | Evidence-based challenge mechanism |
| Fund-lock protection | Expiry window only | Expiry window **and** permissionless finalize on every proposed match |

## Proof of live on-chain behavior (not just offline tests)

The contract was deployed and exercised end-to-end on a real fixture (Mainz 05 vs Eintracht Frankfurt, Bundesliga, September 12, 2026, final score 1–3):

- **Contract:** `0xA98b5BdD53a91533214103aAfbC6687Da8239Bc4`
- **Deploy tx:** `0x188af5ff831b5a0b948fccc53b7284c3f2220e955f5c6812140b5622fd9ed2dc`
- **create_match tx:** `0xe733047fc3885c8497b9b468d4d9ed6e404dcb01fdb82683859755e7dda3825c` → `match_id: "0"`
- **accept_match tx:** `0xc3ea5c534e9a762cc07779fb3849e2383c3fbbc622609f20c7aabb929be496aa` → status → `open`
- **propose_resolution (first attempt, failed) tx:** `0x7ab76f896712e67e839552f8ab8f730429f85796eb3cf22aabcc0183ab00bc64` — submitted with 2 sources (ESPN + BBC). ESPN was rejected with `quality_flag: "event_mismatch"` (the LLM could not confidently confirm the fixture), leaving only 1 eligible source — below the required minimum. **Result: nothing was locked, status remained `"open"`.** This is live, on-chain proof of pillar #2: without sufficient evidence, not even the first source gets locked.
- **propose_resolution (second attempt, succeeded) tx:** `0x9f06dc0ee5f96f599df256dc8a6cb78f01e31485e2094120282e8be0b7cd29b5` — submitted with 3 sources (ESPN + BBC + Sofascore), all three `quality_flag: "ok"` and agreeing on `AwayWin`. Result: `status → "proposed"`, `proposed_verdict: "AwayWin"`, `proposed_settlement: "party_b_wins"`, `challenge_deadline` set, first `resolution_history` entry logged (version 1, trigger: "proposed").
- **finalize_match tx:** `0xa384ea236972232dc9740dc76cd85fe4ef5d4196f0b27008031fe463ee280c37` — after the challenge window closed: `status → "finalized"`, `final_verdict: "AwayWin"`, `settlement_outcome: "party_b_wins"`, second `resolution_history` entry logged (trigger: "finalized").
- **get_match / get_role / total_matches:** all returned correctly (`party_a`, `none`, `1`).

Evidence sources used:
- ESPN: `https://www.espn.com/soccer/match/_/gameId/401884794/eintracht-frankfurt-mainz`
- BBC: `https://www.bbc.com/sport/football/live/ckvgy147z1e5t`
- Sofascore: `https://www.sofascore.com/football/match/eintracht-frankfurt-1-fsv-mainz-05/gbbszdb`

## Offline test suite

46 pytest tests (party binding and timing, URL/domain parsing, two-stage aggregation logic, and a full end-to-end suite including a challenge scenario that flips a verdict from Disputed to a decisive result and back) — all passing.

## Repository / Frontend

- GitHub repo: **[add your repo link here]**
- GitHub Pages (live frontend): **[add your Pages link here]**
- GenLayer Explorer: `https://explorer-studio.genlayer.com/address/0xA98b5BdD53a91533214103aAfbC6687Da8239Bc4`

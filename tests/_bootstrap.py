"""
Shared test bootstrap - wires up the offline genlayer SDK stub and
loads contract.py once. Same pattern used by the sibling ScoreSettle
project.
"""
import importlib.util
import os
import sys
import datetime

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_STUB_DIR = os.path.join(_THIS_DIR, "genlayer_stub")
if _STUB_DIR not in sys.path:
    sys.path.insert(0, _STUB_DIR)

_CONTRACT_PATH = os.path.join(os.path.dirname(_THIS_DIR), "contract.py")
_spec = importlib.util.spec_from_file_location("matchguard_contract", _CONTRACT_PATH)
_contract_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_contract_module)

MatchGuard = _contract_module.MatchGuard
gl = _contract_module.gl
Address = _contract_module.Address


def make_contract() -> "MatchGuard":
    return MatchGuard()


# Two fixed, valid, distinct addresses reused across test files.
PARTY_A_ADDRESS = "0x" + "11" * 20
PARTY_B_ADDRESS = "0x" + "22" * 20
STRANGER_ADDRESS = "0x" + "33" * 20


def set_caller(address_str: str):
    """Simulate a specific wallet calling the next contract method."""
    gl.message.sender_address = Address(address_str)


def iso(dt: "datetime.datetime") -> str:
    return dt.isoformat()


def now_utc() -> "datetime.datetime":
    return datetime.datetime.now(datetime.timezone.utc)


# Convenience valid timing: a match starting comfortably within the
# allowed [MIN_DEADLINE_LEAD_SECONDS, MAX_DEADLINE_LEAD_SECONDS] window,
# with a resolution_deadline comfortably within
# [MIN_MATCH_DURATION_SECONDS, MAX_MATCH_DURATION_BUFFER_SECONDS] after it.
def default_timing():
    start = now_utc() + datetime.timedelta(hours=3)
    deadline = start + datetime.timedelta(hours=2)
    return iso(start), iso(deadline)


DEFAULT_REQUIRED_DOMAINS = ["espn.com", "bbc.com"]


def create_default_match(contract, **overrides):
    """Create a match with sane, valid defaults; any field can be
    overridden via kwargs (using create_match's parameter names)."""
    scheduled_start, resolution_deadline = default_timing()
    kwargs = dict(
        party_b_address=PARTY_B_ADDRESS,
        sport="Football",
        competition="Premier League",
        home_team="Alpha FC",
        away_team="Beta United",
        scheduled_start=scheduled_start,
        side_a="home",
        resolution_deadline=resolution_deadline,
        description="Friendly wager on the Alpha FC vs Beta United result.",
        required_source_domains=list(DEFAULT_REQUIRED_DOMAINS),
    )
    kwargs.update(overrides)
    set_caller(PARTY_A_ADDRESS)
    return contract.create_match(**kwargs)

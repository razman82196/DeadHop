import asyncio

import pytest

from app.irc.manager import IRCManager, ServerProfile


@pytest.fixture
def profile() -> ServerProfile:
    return ServerProfile(name="local", host="example.org", channels=["#test"]) 


@pytest.mark.asyncio
async def test_has_cap_and_ts_from_tags(profile):
    m = IRCManager(profile)
    # initially empty
    assert not m.has_cap("server-time")
    # simulate capability activation
    m._active_caps.update({"server-time", "echo-message"})
    assert m.has_cap("server-time")
    assert m.has_cap("echo-message")

    # valid RFC3339 time with Z
    ts = m._ts_from_tags({"time": "2023-10-11T12:34:56.789Z"})
    assert isinstance(ts, float)

    # invalid formats handled gracefully
    assert m._ts_from_tags({}) is None
    assert m._ts_from_tags({"time": "not-a-time"}) is None


@pytest.mark.asyncio
async def test_send_safe_when_writer_none(profile):
    m = IRCManager(profile)
    # no writer yet; _send should be a no-op without raising
    await m._send("PING :server")


@pytest.mark.asyncio
async def test_sasl_payload_format(profile):
    p = profile
    p.password = "pw"
    p.sasl_user = "user"
    m = IRCManager(p)
    out = m._sasl_payload()
    # Should begin with AUTHENTICATE and contain base64 payload after a space
    assert out.startswith("AUTHENTICATE ")
    assert len(out.split(" ", 1)[1]) > 0

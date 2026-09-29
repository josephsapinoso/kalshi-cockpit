"""#194: the public latency probe and its gap analysis, no network."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import probe_public_latency as p  # noqa: E402

# Section C, whole seconds; the first is h:m:s, the rest are m:s in the same hour.
C_STALLS = ("17:54 18:57 19:14 20:13 20:28 20:43 20:59 21:13 21:29 21:45 "
            "22:17 22:32 24:19 24:36 25:25 26:12 26:26 26:42 27:01 27:17").split()

RUN3 = ["11:45.695", "12:02.815", "12:33.923", "12:48.054", "13:25.190", "13:54.333",
        "14:11.435", "14:27.564", "14:44.688", "15:32.808", "15:47.948", "16:22.102"]


def _ms(mmss: str) -> float:
    m, s = mmss.split(":")
    return int(m) * 60 + float(s)


def test_section_c_gaps():
    ts = [3 * 3600 + 17 * 60 + 39] + [3 * 3600 + _ms(x) for x in C_STALLS]
    gaps = p.stall_gaps(ts)
    assert len(ts) == 21 and len(gaps) == 20
    assert sum(g < 24 for g in gaps) == 14
    assert min(gaps) == 14.0


def test_run3_gaps():
    ts = [11 * 60 + 31.576] + [_ms(x) for x in RUN3]
    assert len(ts) == 13
    gaps = p.stall_gaps(ts)
    assert len(gaps) == 12
    assert sum(g < 24 for g in gaps) == 7
    assert p.fraction_under(gaps, 24) == pytest.approx(7 / 12)


def test_stall_definition():
    assert not p.is_stall(12.0)      # fast 404 is not a stall
    assert p.is_stall(1200.0)        # a 1,200 ms 200 is
    assert not p.is_stall(None, "ConnectError")
    assert not p.is_stall(5000.0, "ReadTimeout")


def _run(tmp_path, capsys, bases, auth=False, handler=None):
    seen = []

    def default(req: httpx.Request) -> httpx.Response:
        seen.append(req.headers.get("cookie", ""))
        return httpx.Response(404 if "no-such" in req.url.path else 200)

    out = tmp_path / "probe.csv"
    argv = ["--seconds", "0.15", "--interval", "0.02", "--out", str(out)]
    for b in bases:
        argv += ["--base-url", b]
    if auth:
        argv.append("--auth")
    p.main(argv, transport=httpx.MockTransport(handler or default))
    return out, capsys.readouterr(), seen


@pytest.fixture(autouse=True)
def fake_token(monkeypatch):
    monkeypatch.setattr(p, "token", lambda: "FAKE-TOKEN-abc123")


def test_token_and_cookie_never_leak(tmp_path, capsys):
    out, cap, seen = _run(tmp_path, capsys, ["https://a.test"], auth=True)
    sent = [c for c in seen if "cockpit_session=" in c]
    assert sent, "the cookie must actually be sent"
    cookie_val = sent[0].split("cockpit_session=")[1].split(";")[0]
    blob = cap.out + cap.err + out.read_text(encoding="utf-8")
    assert "FAKE-TOKEN-abc123" not in blob
    assert cookie_val not in blob
    assert "cockpit_session" not in blob


def test_out_inside_repo_refused():
    target = p.ROOT / "probe_out_194.csv"
    with pytest.raises(SystemExit):
        p.main(["--seconds", "0.1", "--out", str(target)],
               transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    assert not target.exists()


def test_two_base_urls_two_arms(tmp_path, capsys):
    out, cap, _ = _run(tmp_path, capsys, ["https://a.test", "https://b.test"])
    assert "arm https://a.test" in cap.out and "arm https://b.test" in cap.out
    assert {r["arm"] for r in p.read_rows(out)} == {"https://a.test", "https://b.test"}


def test_errors_and_404s_are_recorded_but_never_stalls(tmp_path, capsys):
    def handler(req):
        if req.url.host == "err.test":
            raise httpx.ConnectError("boom")
        return httpx.Response(404)

    out, _, _ = _run(tmp_path, capsys, ["https://a.test", "https://err.test"], handler=handler)
    s = p.summarise(p.read_rows(out))
    assert s["https://a.test"]["stalls"] == 0 and "404" in s["https://a.test"]["statuses"]
    assert s["https://err.test"]["stalls"] == 0 and "error" in s["https://err.test"]["statuses"]
    p.main(["--analyse", str(out)])
    assert "arm https://err.test" in capsys.readouterr().out

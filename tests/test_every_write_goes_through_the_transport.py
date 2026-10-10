"""Every non-spending write in `frontend/src/lib/api.ts` goes through the transport.

ADR 0191. Before it, about twenty POST helpers each re-implemented fetch, parse,
shape-check and refusal text, and drifted into three failure styles and two
spellings of a refusal (`String(detail)` rendered a pydantic list as
`[object Object]`).

Establishes:
  * by execution (`node --experimental-strip-types`, the shipped
    `lib/transport.ts`, a stubbed `fetch`): a string, pydantic-list and object
    `detail` all come out through `refusalText`; a thrown fetch returns the
    caller's no-reply sentence verbatim; a non-JSON body returns the caller's
    unreadable sentence verbatim with the status kept; a failed success-shape
    check returns the unreadable sentence; a success returns the value; and
    `engageLockout` (a former thrower) now returns a result instead of throwing.
  * by source text: the two sentences are REQUIRED parameters with no default,
    every `postJson` call in `api.ts` supplies both, and no `method: "POST"`
    remains in `api.ts` outside the transport (#260 emptied the spend
    allowlist), and every spend write sends Joe to the Kalshi app on a lost reply.

Does not establish: what any component does with the result, or that the
route handlers behind the paths answer as the stub does.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests._node_driver import node_driver

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "frontend" / "src" / "lib"
TRANSPORT = LIB / "transport.ts"
API = LIB / "api.ts"
NODE = shutil.which("node")

#: Was the five spend writes until #260 converted them (2026-10-01). Empty
#: now: no write in `api.ts` may POST outside the transport.
SPEND_HELPERS: set[str] = set()

#: The writes that can move money at the venue (CONTEXT.md "Spend write").
#: A lost or unreadable reply on these is UNKNOWN (ADR 0191 section 2.3), so
#: their sentences must send Joe to the Kalshi app and never claim nothing
#: happened.
SPENDING = ("placeManualOrder", "acceptComboQuote", "placeComboBid")

# Node strips types but does not resolve `./transport` to `./transport.ts`;
# the bundler does. Same hook as tests/test_sweep_tone_predicate.py.
_HOOK = """
import { registerHooks } from "node:module";
registerHooks({
  resolve(specifier, context, nextResolve) {
    try {
      return nextResolve(specifier, context);
    } catch (e) {
      const relative = specifier.startsWith("./") || specifier.startsWith("../");
      const bare = !/\\.[cm]?[jt]sx?$/.test(specifier);
      if (e && e.code === "ERR_MODULE_NOT_FOUND" && relative && bare) {
        return nextResolve(specifier + ".ts", context);
      }
      throw e;
    }
  },
});
"""

_DRIVER = """
import {{ postJson }} from "{module}";
const sc = JSON.parse(process.argv[2]);
globalThis.fetch = async () => {{
  if (sc.throws) throw new Error("boom");
  return new Response(sc.raw, {{ status: sc.status }});
}};
const result = await postJson({{
  path: "/x",
  body: {{ a: 1 }},
  noReply: (e) => "NOREPLY:" + e.message,
  unreadable: (s) => "UNREADABLE:" + s,
  shape: sc.shape ? (b) => typeof b === "object" && "status" in b : undefined,
}});
console.log(JSON.stringify(result));
"""

_API_DRIVER = """
import {{ engageLockout }} from "{module}";
const sc = JSON.parse(process.argv[2]);
globalThis.fetch = async () => {{
  if (sc.throws) throw new Error("boom");
  return new Response(sc.raw, {{ status: sc.status }});
}};
console.log(JSON.stringify(await engageLockout()));
"""


def _node(driver_source: str, scenario: dict, module_dir: Path = LIB) -> dict:
    with node_driver(module_dir, driver_source) as driver, node_driver(
        module_dir, _HOOK
    ) as hook:
        out = subprocess.run(
            [
                NODE,
                "--experimental-strip-types",
                "--import",
                hook.resolve().as_uri(),
                str(driver),
                json.dumps(scenario),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(module_dir),
        )
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip().splitlines()[-1])


def post(raw=None, status=200, throws=False, shape=False, module_dir=LIB) -> dict:
    scenario = {"raw": raw, "status": status, "throws": throws, "shape": shape}
    return _node(_DRIVER.format(module="./transport.ts"), scenario, module_dir)


def _code_only(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", source)


PYDANTIC = [{"loc": ["body", "quote_id"], "msg": "field required", "type": "missing"}]


@pytest.mark.skipif(NODE is None, reason="node is not on PATH")
class TestBehaviour:
    def test_a_string_detail_passes_through(self):
        result = post(json.dumps({"detail": "That quote is gone."}), status=409)
        assert result == {
            "ok": False,
            "status": 409,
            "refusal": "That quote is gone.",
            "detail": "That quote is gone.",
        }

    def test_a_pydantic_list_reads_as_field_and_message(self):
        result = post(json.dumps({"detail": PYDANTIC}), status=422)
        assert result["refusal"] == "quote_id: field required"
        assert result["detail"] == PYDANTIC  # raw body kept for isLockedDetail

    def test_an_object_detail_reads_as_its_message(self):
        result = post(json.dumps({"detail": {"message": "Locked.", "conditions": []}}), status=423)
        assert result["refusal"] == "Locked."
        assert result["detail"]["conditions"] == []

    def test_a_thrown_fetch_is_the_callers_no_reply_sentence(self):
        result = post(throws=True)
        assert result == {
            "ok": False,
            "status": 0,
            "refusal": "NOREPLY:boom",
            "detail": None,
        }

    def test_a_non_json_body_is_the_callers_unreadable_sentence_with_status(self):
        result = post("<html>502</html>", status=502)
        assert result["ok"] is False
        assert result["status"] == 502
        assert result["refusal"] == "UNREADABLE:502"

    def test_a_200_with_a_non_json_body_is_not_a_success(self):
        # A proxy page served with a 200 must not read as a success.
        result = post("<html>login</html>", status=200)
        assert result["ok"] is False
        assert result["refusal"] == "UNREADABLE:200"

    def test_a_failed_shape_check_is_the_unreadable_sentence(self):
        result = post(json.dumps({"nope": 1}), status=200, shape=True)
        assert result["ok"] is False
        assert result["status"] == 200
        assert result["refusal"] == "UNREADABLE:200"

    def test_a_success_returns_the_value(self):
        result = post(json.dumps({"status": "ok", "n": 3}), shape=True)
        assert result == {"ok": True, "status": 200, "value": {"status": "ok", "n": 3}}

    def test_a_former_thrower_returns_instead_of_throwing(self):
        refused = _node(
            _API_DRIVER.format(module="./api.ts"),
            {"raw": json.dumps({"detail": "The log is locked."}), "status": 423},
        )
        assert refused["ok"] is False
        assert refused["refusal"] == "The log is locked."
        silent = _node(
            _API_DRIVER.format(module="./api.ts"), {"raw": "<html>", "status": 502}
        )
        assert silent["refusal"] == "lockout failed (502)"  # its own words, kept


class TestRequiredWording:
    def test_the_two_sentences_are_required_parameters(self):
        code = _code_only(TRANSPORT.read_text(encoding="utf-8"))
        options = code[code.index("export type WriteOptions") :]
        options = options[: options.index("\n};")]
        assert re.search(r"^\s*noReply:\s*\(", options, re.M)
        assert re.search(r"^\s*unreadable:\s*\(", options, re.M)
        assert "noReply?" not in options and "unreadable?" not in options

    def test_the_transport_gives_neither_a_default(self):
        code = _code_only(TRANSPORT.read_text(encoding="utf-8"))
        body = code[code.index("export async function postJson") :]
        assert not re.search(r"\b(noReply|unreadable)\s*=[^=>]", body)
        assert not re.search(r"\b(noReply|unreadable)\s*\?\?", body)

    def test_every_call_in_api_supplies_both(self):
        code = _code_only(API.read_text(encoding="utf-8"))
        calls = len(re.findall(r"\bpostJson<", code))
        assert calls >= 15
        assert len(re.findall(r"^\s*noReply:", code, re.M)) == calls
        assert len(re.findall(r"^\s*unreadable[:,]", code, re.M)) == calls

    def test_the_transport_adds_no_retry(self):
        code = _code_only(TRANSPORT.read_text(encoding="utf-8"))
        assert len(re.findall(r"\bfetch\(", code)) == 1
        assert not re.search(r"\b(retry|retries|attempt)\b", code, re.I)


class TestNoStrayPost:
    def test_no_post_remains_in_api_outside_the_spend_helpers(self):
        code = _code_only(API.read_text(encoding="utf-8"))
        stray = []
        for hit in re.finditer(r'method:\s*"POST"', code):
            owners = re.findall(r"function\s+(\w+)", code[: hit.start()])
            owner = owners[-1] if owners else "<module>"
            if owner not in SPEND_HELPERS:
                stray.append(owner)
        assert stray == []


def _function_body(code: str, name: str) -> str:
    start = code.index(f"export async function {name}(")
    return code[start : code.index("\n}\n", start)]


class TestASpendWriteNeverClaimsNothingHappened:
    """ADR 0191 section 2.3: on a spend write a lost reply is UNKNOWN."""

    @pytest.mark.parametrize("name", SPENDING)
    def test_it_goes_through_the_transport(self, name):
        body = _function_body(API.read_text(encoding="utf-8"), name)
        assert "postJson<" in body

    @pytest.mark.parametrize("name", SPENDING)
    @pytest.mark.parametrize("sentence", ["noReply", "unreadable"])
    def test_both_sentences_send_him_to_the_kalshi_app(self, name, sentence):
        body = _function_body(API.read_text(encoding="utf-8"), name)
        if sentence == "unreadable" and re.search(r"^\s*unreadable,", body, re.M):
            # Shorthand for a local `const unreadable = ...` in the same body.
            text = body[body.index("const unreadable") : body.index("return postJson")]
        else:
            text = body[body.index(f"{sentence}:") :]
            text = text[: re.search(r"\n\s*\w+[:,]\s", text[1:]).start() + 1]
        assert "Kalshi app" in text, (name, sentence, text)
        assert not re.search(
            r"\bnothing\b|\bnot (been )?sent\b|\bnot placed\b", text, re.I
        ), (name, sentence, text)

    def test_no_spend_sentence_says_nothing_was_sent(self):
        code = _code_only(API.read_text(encoding="utf-8"))
        assert "Nothing was sent to the exchange" not in code

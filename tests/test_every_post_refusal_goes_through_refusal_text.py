"""Every refusal in `frontend/src/lib/api.ts` is turned into words by `refusalText`.

**The defect.** FastAPI answers a malformed body with 422 and a *list* of
pydantic error objects as `detail`. `String(list_of_objects)` is
`[object Object],[object Object]`. `postHedge` was fixed; thirteen other
helpers, including `acceptComboQuote` (the spend path, whose refusal state
offers no retry so the words are all Joe gets), kept `String(detail)`.

Establishes: by source text, that no `String(...detail...)` formatting remains
outside comments; by execution (`node --experimental-strip-types`, the shipped
`api.ts`), that `acceptComboQuote` renders a pydantic list as `field: msg`.

Does not establish: that the other twelve helpers behave identically at run
time (they share the one function, checked by source text only), or what any
component does with the refusal string.
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
API = REPO / "frontend" / "src" / "lib" / "api.ts"
NODE = shutil.which("node")

_DRIVER = """
import {{ acceptComboQuote }} from "{module}";
const detail = JSON.parse(process.argv[2]);
globalThis.fetch = async () => new Response(JSON.stringify({{ detail }}), {{
  status: 422,
  headers: {{ "Content-Type": "application/json" }},
}});
console.log(JSON.stringify(await acceptComboQuote("rfq-1", "q-1")));
"""

# `api.ts` imports `./transport` extensionless (ADR 0191), which the bundler
# resolves and node does not; same hook as tests/test_sweep_tone_predicate.py.
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

PYDANTIC = [
    {"loc": ["body", "quote_id"], "msg": "field required", "type": "missing"}
]


def _code_only(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", source)


def _run(detail) -> dict:
    with node_driver(API.parent, _DRIVER.format(module="./api.ts")) as driver, node_driver(
        API.parent, _HOOK
    ) as hook:
        out = subprocess.run(
            [
                NODE,
                "--experimental-strip-types",
                "--import",
                hook.resolve().as_uri(),
                str(driver),
                json.dumps(detail),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(API.parent),
        )
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip().splitlines()[-1])


class TestSource:
    def test_no_string_of_a_detail_remains(self):
        code = _code_only(API.read_text(encoding="utf-8"))
        offenders = [
            line.strip()
            for line in code.splitlines()
            if re.search(r"String\([^)]*detail", line)
        ]
        assert offenders == []


@pytest.mark.skipif(NODE is None, reason="node is not on PATH")
class TestBehaviour:
    def test_a_pydantic_list_reads_as_field_and_message(self):
        result = _run(PYDANTIC)
        assert result["ok"] is False
        assert "quote_id: field required" in result["refusal"]
        assert "[object Object]" not in result["refusal"]

    def test_a_plain_string_detail_is_unchanged(self):
        result = _run("That quote is gone.")
        assert result["refusal"] == "That quote is gone."

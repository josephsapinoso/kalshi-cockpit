"""`OpenPositions` rendered, not read: does every branch show the server's reason?

**Why this renders the component instead of asserting on its source.** The
defect ADR 0107's screen lane fixes is a *branch that silently drops a field*.
`backend/bets.py` words five distinct staked refusals with care -- "no
positions poll has succeeded yet" is a different fact from "not read in the
last 30 minutes" -- and two of the component's three branches returned before
anything could render them. A substring test sees `staked_refusal` mentioned
in the file and calls that covered; it cannot see that the mention sits in a
branch the payload never reaches. Only rendering the real component with a
real payload answers "does Joe see this sentence".

**How.** Node strips types but does **not** transform JSX, so the component is
compiled with the repo's own `tsc` (`--jsx react-jsx`) into a temp directory
and rendered with `react-dom/server`. Two files are substituted and neither is
the code under test: `@/lib/api` becomes a stub carrying `DISPLAY_TIME_ZONE`
and the `OpenPositionsBlock` type copied from the real module, because
importing the real `api.ts` would drag ~2,500 lines of unrelated wire types
through the compile; `@/lib/openPositionsStamps` is the real file, copied
unmodified. `OpenPositions.tsx` itself is copied byte-for-byte except for the
two import specifiers, which the bundler alias would otherwise have to
resolve.

What this establishes: that each reachable server payload produces markup
containing the server's own words, and that the two figures on `/slate` no
longer print the same bold phrase for different numbers.

What this does **not** establish: that the server picks the right refusal for
a given database state (`tests/test_venue_positions.py` and
`tests/test_bets_sections.py` own that); that the stamps are the right clocks
(`tests/test_open_positions_stamp.py`); or anything about styling beyond the
text content.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"
COMPONENT = FRONTEND / "src" / "components" / "OpenPositions.tsx"
STAMPS = FRONTEND / "src" / "lib" / "openPositionsStamps.ts"

NODE = shutil.which("node")
NPX = shutil.which("npx") or shutil.which("npx.cmd")

pytestmark = pytest.mark.skipif(
    NODE is None or NPX is None or not (FRONTEND / "node_modules").is_dir(),
    reason=(
        "node, npx and an installed frontend are required. Skipped rather "
        "than xfailed: the guard is real where they exist (CI and both dev "
        "machines) and a missing runtime is an environment fact."
    ),
)

#: The wire type, copied from `frontend/src/lib/api.ts`. Copied rather than
#: imported so the compile stays small; `tests/test_bets_sections.py` pins the
#: real declaration, and this stub only has to be structurally faithful.
_API_STUB = """
export const DISPLAY_TIME_ZONE = "America/Los_Angeles";
export type OpenPositionsBlock = {
  count: number | null;
  count_as_of_ms: number | null;
  count_age_ms?: number | null;
  value_tenths: number | null;
  value_display: string | null;
  value_as_of_ms: number | null;
  value_age_ms?: number | null;
  value_refusal: string | null;
  staked_tenths?: number | null;
  staked_display?: string | null;
  staked_refusal?: string | null;
};
"""

#: The compiled component lives in a temp directory, and ESM resolves bare
#: specifiers by walking up from the importing FILE rather than from `cwd` --
#: so `react-dom/server` and `react/jsx-runtime` are unreachable from there
#: however the subprocess is launched. The hook resolves exactly those two
#: against the repo's own `frontend/` install, at the versions that ship, and
#: touches nothing else: a bare specifier it was not given is left to fail
#: exactly as node would fail it.
_HOOK = """
import {{ registerHooks }} from "node:module";
const MAP = {map};
registerHooks({{
  resolve(specifier, context, nextResolve) {{
    if (Object.hasOwn(MAP, specifier)) {{
      return {{ url: MAP[specifier], shortCircuit: true }};
    }}
    try {{
      return nextResolve(specifier, context);
    }} catch (e) {{
      // `tsc --moduleResolution bundler` emits `./lib/api` with no
      // extension, which the bundler resolves and node does not. Retry with
      // `.js` for a relative, extensionless specifier and nothing else.
      const relative = specifier.startsWith("./") || specifier.startsWith("../");
      const bare = !/\\.[cm]?jsx?$/.test(specifier);
      if (e && e.code === "ERR_MODULE_NOT_FOUND" && relative && bare) {{
        return nextResolve(specifier + ".js", context);
      }}
      throw e;
    }}
  }},
}});
"""

_DRIVER = """
import { renderToStaticMarkup } from "react-dom/server";
import OpenPositions from "./OpenPositions.js";
const block = JSON.parse(process.argv[2]);
const html = renderToStaticMarkup(OpenPositions({ block }));
console.log(JSON.stringify({ html }));
"""


def _module_map() -> dict[str, str]:
    """`react-dom/server` and `react/jsx-runtime` as file URLs, resolved by
    node itself from the frontend package rather than guessed from a path."""
    script = (
        "const {createRequire}=require('module');"
        f"const r=createRequire({json.dumps(str(FRONTEND / 'package.json'))});"
        "const {pathToFileURL}=require('url');"
        "console.log(JSON.stringify({"
        "'react-dom/server': pathToFileURL(r.resolve('react-dom/server')).href,"
        "'react/jsx-runtime': pathToFileURL(r.resolve('react/jsx-runtime')).href"
        "}));"
    )
    out = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, timeout=60
    )
    assert out.returncode == 0, f"could not resolve react: {out.stderr}"
    return json.loads(out.stdout.strip())

POLLED_MS = 1_788_600_000_000
NOW_MS = POLLED_MS + 60_000


def _base(**over) -> dict:
    block = {
        "count": None,
        "count_as_of_ms": None,
        "count_age_ms": None,
        "value_tenths": None,
        "value_display": None,
        "value_as_of_ms": None,
        "value_age_ms": None,
        "value_refusal": None,
    }
    block.update(over)
    return block


@pytest.fixture(scope="module")
def pristine(tmp_path_factory) -> Path:
    """The unmodified component, compiled ONCE for the whole module.

    `tsc` costs ~2.5s a call and eleven of the thirteen tests here render the
    same source, so compiling per test spent ~30s to produce the same bytes
    eleven times -- an eighth of CI's whole `Tests + warehouse` budget, for
    nothing. The two mutation tests pass `source` and get their own build.
    """
    return _build(tmp_path_factory.mktemp("pristine"), None)


def _build(tmp_path: Path, source: str | None) -> Path:
    """Compile the component (real or mutated) and return its `out` dir."""
    work = tmp_path / "rt"
    (work / "lib").mkdir(parents=True, exist_ok=True)
    tsx = COMPONENT.read_text(encoding="utf-8") if source is None else source
    tsx = tsx.replace('"@/lib/api"', '"./lib/api"').replace(
        '"@/lib/openPositionsStamps"', '"./lib/openPositionsStamps"'
    )
    (work / "OpenPositions.tsx").write_text(tsx, encoding="utf-8")
    (work / "lib" / "api.ts").write_text(_API_STUB, encoding="utf-8")
    (work / "lib" / "openPositionsStamps.ts").write_text(
        STAMPS.read_text(encoding="utf-8").replace('"@/lib/api"', '"./api"'),
        encoding="utf-8",
    )

    out = work / "out"
    compile_result = subprocess.run(
        [
            NPX, "tsc",
            str(work / "OpenPositions.tsx"),
            str(work / "lib" / "openPositionsStamps.ts"),
            str(work / "lib" / "api.ts"),
            "--jsx", "react-jsx",
            "--module", "esnext",
            "--target", "es2022",
            "--moduleResolution", "bundler",
            "--skipLibCheck",
            "--outDir", str(out),
        ],
        capture_output=True, text=True, timeout=300, cwd=str(FRONTEND),
    )
    assert (out / "OpenPositions.js").is_file(), (
        "tsc emitted no component:\n"
        f"{compile_result.stdout}\n{compile_result.stderr}"
    )
    # Written once beside the build rather than per render: both are pure
    # functions of the install, and `_module_map` shells out to node.
    (out / "_render.mjs").write_text(_DRIVER, encoding="utf-8")
    (out / "_hook.mjs").write_text(
        _HOOK.format(map=json.dumps(_module_map())), encoding="utf-8"
    )
    return out


def render(block: dict | None, out: Path) -> str:
    """Render the compiled component with `block`; return its text content."""
    driver = out / "_render.mjs"
    hook = out / "_hook.mjs"
    result = subprocess.run(
        [
            NODE,
            "--import", hook.resolve().as_uri(),
            str(driver),
            json.dumps(block),
        ],
        capture_output=True, text=True, timeout=120, cwd=str(FRONTEND),
    )
    assert result.returncode == 0, (
        f"node failed rendering:\n{result.stdout}\n{result.stderr}"
    )
    html = json.loads(result.stdout.strip())["html"]
    return re.sub(r"<[^>]+>", "", html)


# ---------------------------------------------------------------------------
# The four states that reach the `count === null` branch
# ---------------------------------------------------------------------------
# Each is a real `backend/bets.py` payload: the server omits `count` and sends
# a differently-worded `staked_refusal`. Before 2026-09-05 all four rendered
# the same sentence, which named a cause that is wrong for two of them.

NEVER_POLLED = _base(staked_refusal="no positions poll has succeeded yet")
NOT_MIRRORED = _base(staked_refusal="no positions poll has kept its rows yet")
NOT_READ = _base(
    staked_refusal="not read in the last 30 minutes",
    count_as_of_ms=POLLED_MS,
    count_age_ms=NOW_MS - POLLED_MS,
)
RECORD_UNREADABLE = _base(
    staked_refusal="the open-positions record could not be read"
)


class TestEveryRefusalReachesTheScreen:
    """The defect, stated four times. The server distinguishes these; the
    screen must not flatten them back together."""

    @pytest.mark.parametrize(
        "block",
        [NEVER_POLLED, NOT_MIRRORED, NOT_READ, RECORD_UNREADABLE],
        ids=["never_polled", "not_mirrored", "not_read", "record_unreadable"],
    )
    def test_the_servers_own_words_are_rendered(self, block, pristine):
        text = render(block, pristine)
        assert block["staked_refusal"] in text, (
            "the screen replaced the server's reason with its own sentence"
        )

    def test_it_no_longer_claims_the_mirror_is_behind_when_nothing_was_polled(self, pristine):
        """The half that was actively false. "The positions mirror is behind"
        asserts a previous read that, in this state, never happened."""
        text = render(NEVER_POLLED, pristine)
        assert "mirror is behind" not in text

    def test_it_still_says_an_absence_of_reading_is_not_an_absence_of_risk(self, pristine):
        """The sentence that must survive the rewrite. Losing it would turn a
        refusal into something a reader could mistake for "you hold
        nothing"."""
        text = render(NOT_READ, pristine)
        assert "not the same as nothing at risk" in text


class TestTheZeroCountBranch:
    """`count === 0` returned before `StakedNow` could speak."""

    def test_an_empty_but_fresh_snapshot_reads_as_no_positions(self, pristine):
        """ADR 0107 §5: count 0 and $0.00 from one read is an honest state,
        and the live account has been in it since v33. "No open positions"
        already says $0.00, so the figure is deliberately not printed twice."""
        block = _base(
            count=0,
            count_as_of_ms=POLLED_MS,
            count_age_ms=NOW_MS - POLLED_MS,
            staked_tenths=0,
            staked_display="$0.00",
        )
        text = render(block, pristine)
        assert "No open positions at the venue" in text
        assert "$0.00" not in text, (
            "the zero is printed twice -- 'No open positions' already says it"
        )

    def test_an_integrity_refusal_at_zero_is_not_swallowed(self, pristine):
        """The reachable one that matters: the mirror holds rows under a poll
        that counted none, so the table disagrees with the read that wrote it.
        Reporting "nothing open" off that record without saying so is the
        defect."""
        words = "the mirror holds 2 rows for a poll that counted 0"
        block = _base(
            count=0,
            count_as_of_ms=POLLED_MS,
            count_age_ms=NOW_MS - POLLED_MS,
            staked_refusal=words,
        )
        text = render(block, pristine)
        assert words in text, "an integrity refusal at a zero count is hidden"


class TestTheOpenCase:
    def test_the_figure_and_its_words_render(self, pristine):
        block = _base(
            count=2,
            count_as_of_ms=POLLED_MS,
            count_age_ms=NOW_MS - POLLED_MS,
            value_display=None,
            value_refusal="the venue reported a value whose unit has never been pinned",
            staked_tenths=41_000,
            staked_display="$41.00",
        )
        text = render(block, pristine)
        assert "Open now: 2 positions" in text
        assert "$41.00 staked" in text
        assert "your own money in, not a value" in text

    def test_the_staked_phrase_distinguishes_itself_from_tonights(self, pristine):
        """`/slate` mounts this and `TonightStrip` seven lines apart and both
        printed a bold "$X staked" for different numbers -- this one the money
        on positions open now, that one the money committed since the day
        roll. The qualifier is inside the bold span because the bold text is
        what the eye takes."""
        block = _base(
            count=1,
            count_as_of_ms=POLLED_MS,
            count_age_ms=NOW_MS - POLLED_MS,
            value_refusal="not read",
            staked_tenths=41_000,
            staked_display="$41.00",
        )
        text = render(block, pristine)
        assert "staked on what is still open" in text, (
            "the open-positions figure no longer distinguishes itself from "
            "TonightStrip's 'staked tonight' on the same screen"
        )

    def test_a_backend_without_the_field_renders_no_staked_line(self, pristine):
        """The old state, not a refusal: omitted entirely."""
        block = _base(
            count=1,
            count_as_of_ms=POLLED_MS,
            count_age_ms=NOW_MS - POLLED_MS,
            value_refusal="not read",
        )
        text = render(block, pristine)
        assert "staked" not in text.lower()


class TestTheBranchesAreLoadBearing:
    """Each mutation removes one render and asserts the words vanish. Every
    one asserts `mutated != source` first: a mutation that no longer applies
    is a test that passes for free."""

    def test_dropping_the_refusal_from_the_null_branch_hides_four_states(
        self, tmp_path
    ):
        source = COMPONENT.read_text(encoding="utf-8")
        mutated = source.replace(
            "        {typeof block.staked_refusal === \"string\"\n"
            "          ? ` — ${block.staked_refusal}`\n"
            "          : \"\"}\n",
            "",
        )
        assert mutated != source, "the null-branch mutation no longer applies"
        text = render(NEVER_POLLED, _build(tmp_path, mutated))
        assert NEVER_POLLED["staked_refusal"] not in text

    def test_dropping_the_refusal_from_the_zero_branch_hides_the_integrity_case(
        self, tmp_path
    ):
        source = COMPONENT.read_text(encoding="utf-8")
        opener = '        {typeof block.staked_display !== "string" &&'
        # `.index` would raise ValueError and report a stack trace instead of
        # the one fact that matters -- the mutation no longer applies, so this
        # test is passing for free. Same reason the sibling asserts
        # `mutated != source` before trusting a `.replace`.
        assert opener in source, (
            "the zero-branch mutation no longer applies: its anchor is gone "
            "from OpenPositions.tsx, so this test proves nothing"
        )
        start = source.index(opener)
        closer = ") : null}"
        assert closer in source[start:], "the zero-branch mutation lost its end"
        end = source.index(closer, start) + len(closer) + 1
        mutated = source[:start] + source[end:]
        assert mutated != source, "the zero-branch mutation no longer applies"
        words = "the mirror holds 2 rows for a poll that counted 0"
        block = _base(
            count=0,
            count_as_of_ms=POLLED_MS,
            count_age_ms=NOW_MS - POLLED_MS,
            staked_refusal=words,
        )
        text = render(block, _build(tmp_path, mutated))
        assert words not in text

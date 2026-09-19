"""Backlog board: two GitHub trees (map #3, backlog root #80), one frontier. Read-only.

    .venv\\Scripts\\python.exe scripts/board.py
    .venv\\Scripts\\python.exe scripts/board.py --json
    .venv\\Scripts\\python.exe scripts/board.py --fixture tests/fixtures/board_issues.json

Why this exists
----------------
`tasks/NEXT.md` names two queues besides its own Open list: map issue #3
("Cockpit for the pilot", Joe's UI decisions) and, since #80, the engineering
backlog root. Both are walked today with hand-typed `gh api` one-liners in
NEXT.md's own SESSION START box, and a hand-typed query answers exactly the
question it was typed for and nothing else -- it cannot say whether a leaf
an agent could pick up right now is missing an `owner:` label, or whether the
`### Still open` list a session is about to copy forward hands Joe a decision
with no ticket number attached (the decay `tests/test_a_question_for_joe_has_a_ticket.py`
exists for). This is one instrument that answers both: what is ready to work
on, and what is wrong with the tree before anyone starts.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- **It is a snapshot, not a lock.** Two sessions reading it a second apart can
  both see the same node "ready" and both start it. Nothing here reserves
  anything -- the same limitation `scripts/lane_board.py` states for lanes.
- **`ready` is a necessary condition, not sufficient.** A leaf with no
  assignee, no blocker and an open state might still be blocked in a way
  GitHub's dependency graph does not model (a `Blocked by: #N` line in prose
  instead of a native edge, per `docs/agents/issue-tracker.md`). This script
  reads only the native edge (`issue_dependencies_summary.blocked_by`).
- **A closed node is not re-verified.** `state == "closed"` is trusted as
  GitHub reports it; this script does not check whether the work claimed done
  actually landed.
- **The Still-open ticket check is textual, not semantic.** It confirms a
  `#NN` other than `#3` appears on the item; it does not confirm that number
  is open, is a sub-issue of the map, or names the question the item raises.
  `tests/test_a_question_for_joe_has_a_ticket.py`'s own docstring states the
  same limit for its stricter, `ASKS_JOE`-scoped version of this check --
  this script's version is deliberately broader (every Still-open item, not
  only ones matching a decayed wording) and is not a replacement for that
  test.
- **It cannot see a `Blocked by:` prose line**, a task-list child (the
  fallback `docs/agents/issue-tracker.md` names for when sub-issues are
  disabled), or anything on a fork.
- **`gh`'s pagination and rate limits are not this script's problem to solve**
  beyond `--paginate`; a very large tree could hit a secondary rate limit and
  this script reports that as UNREADABLE like any other `gh` failure, never
  as an empty tree.

Unreadable resolves to None, never to zero
-------------------------------------------
Per CLAUDE.md: a `gh` call that fails, JSON that does not decode, or a missing
`tasks/NEXT.md` is reported UNREADABLE with its reason and exits 3. It is
never folded into a clean or a merely-warned result -- mistaking "could not
look" for "found nothing wrong" is the one way an instrument like this lies,
and it lies in the flattering direction.

No application code is imported
--------------------------------
This is stdlib-only. It never imports `backend`, so a broken backend import
does not take down the one instrument that reports on the backlog around it.
It also never imports a `tests/*` module (including
`test_a_question_for_joe_has_a_ticket.py`, whose three small parsers this file
re-implements rather than reaching into) -- a script importing a test file
would make `pytest` a runtime dependency of `scripts/`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

OWNER = "josephsapinoso"
REPO = "kalshi-cockpit"
ROOTS: tuple[int, ...] = (3, 80)
MAP_ISSUE = 3

_TIMEOUT = 45.0

# --------------------------------------------------------------------------
# NEXT.md parsing -- byte-identical in spirit to
# tests/test_a_question_for_joe_has_a_ticket.py's latest_entry / still_open_items /
# names_a_ticket, re-implemented here (not imported: scripts must not depend on
# tests, per this file's own docstring). If the two drift, that is a real
# finding and either file's test suite should catch it independently.
# --------------------------------------------------------------------------

_ENTRY_HEADING = re.compile(r"^## \d{4}-\d{2}-\d{2}")
_STILL_OPEN_HEADING = re.compile(r"^### Still open", re.IGNORECASE)
_ITEM_START = re.compile(r"^\d+\.\s")
_TICKET = re.compile(r"#(\d+)\b")

#: A line starting `Done when`, optionally wrapped in markdown bold
#: (`**Done when**`), case-insensitive, anchored to the start of the line.
_DONE_WHEN = re.compile(r"(?m)^\s*\*{0,2}\s*done when\b", re.IGNORECASE)


def names_a_ticket(text: str) -> bool:
    """True when `text` cites an issue number that is not the map itself."""
    return any(int(n) != MAP_ISSUE for n in _TICKET.findall(text))


def latest_entry(text: str) -> str:
    """The first dated `## YYYY-MM-DD` section of NEXT.md, up to the next `---` rule."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if _ENTRY_HEADING.match(ln)), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == "---"), len(lines))
    return "\n".join(lines[start:end])


def still_open_items(entry: str) -> list[str]:
    """The numbered items under `### Still open`, each with its continuation lines."""
    lines = entry.splitlines()
    start = next((i for i, ln in enumerate(lines) if _STILL_OPEN_HEADING.match(ln)), None)
    if start is None:
        return []
    items: list[list[str]] = []
    for ln in lines[start + 1 :]:
        if ln.startswith("#"):
            break
        if _ITEM_START.match(ln):
            items.append([ln])
        elif items and ln.strip():
            items[-1].append(ln)
    return ["\n".join(item) for item in items]


def still_open_items_without_a_ticket(next_text: str) -> list[str]:
    """Every Still-open item in the latest NEXT.md entry naming no #NN besides #3.

    Broader than the test file's `open_items_asking_joe_without_a_ticket`: this
    checks every item, not only ones matching a decayed "for Joe" wording --
    the board's job is to flag a missing ticket number on sight, not to judge
    whether the item's prose reads as a question.
    """
    entry = latest_entry(next_text)
    return [item for item in still_open_items(entry) if not names_a_ticket(item)]


# --------------------------------------------------------------------------
# gh reads -- the only place a subprocess is invoked. --fixture bypasses this
# whole section entirely.
# --------------------------------------------------------------------------


def _run_gh(args: list[str]) -> tuple[str | None, str | None]:
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"gh invocation failed: {exc}"
    if result.returncode != 0:
        return None, (result.stderr.strip() or f"gh exited {result.returncode}")
    return result.stdout, None


def _gh_json(args: list[str]):
    out, err = _run_gh(args)
    if out is None:
        return None, err
    try:
        return json.loads(out), None
    except json.JSONDecodeError as exc:
        return None, f"gh returned undecodable JSON for {args}: {exc}"


def _fetch_node(number: int) -> tuple[dict | None, str | None]:
    return _gh_json(["api", f"repos/{OWNER}/{REPO}/issues/{number}"])


def _fetch_children(number: int) -> tuple[list | None, str | None]:
    data, err = _gh_json(
        ["api", f"repos/{OWNER}/{REPO}/issues/{number}/sub_issues", "--paginate"]
    )
    if data is None:
        return None, err
    if not isinstance(data, list):
        return None, f"#{number}/sub_issues did not return a list"
    return data, None


def _ensure_full_fields(node: dict) -> tuple[dict | None, str | None]:
    """Per-node fallback fetch when the sub_issues payload omits a field this
    script reads. Measured live 2026-09-19: it does not (see the fixture's own
    `real_capture_shape_note`), so this fires on nothing today and exists for
    the day the endpoint's shape changes.
    """
    if "body" in node and "issue_dependencies_summary" in node:
        return node, None
    return _fetch_node(node["number"])


def _attach_children(node: dict) -> tuple[dict | None, str | None]:
    node, err = _ensure_full_fields(node)
    if node is None:
        return None, err
    children_raw, err = _fetch_children(node["number"])
    if children_raw is None:
        return None, err
    children: list[dict] = []
    for child in children_raw:
        child, err = _ensure_full_fields(child)
        if child is None:
            return None, err
        sub_total = (child.get("sub_issues_summary") or {}).get("total", 0)
        if sub_total:
            subtree, err = _attach_children(child)
            if subtree is None:
                return None, err
            children.append(subtree)
        else:
            children.append({**child, "children": []})
    return {**node, "children": children}, None


def fetch_tree(root_number: int) -> tuple[dict | None, str | None]:
    """The one function that talks to `gh`. Everything else takes its output."""
    root_raw, err = _fetch_node(root_number)
    if root_raw is None:
        return None, err
    return _attach_children(root_raw)


# --------------------------------------------------------------------------
# fixture loading -- the shape `fetch_tree` produces, captured once from the
# real repo. See tests/fixtures/board_issues.json's own "trimming_note" and
# "real_capture_shape_note".
# --------------------------------------------------------------------------


def load_fixture(path: Path) -> tuple[dict | None, str | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"fixture unreadable: {exc}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"fixture is not valid JSON: {exc}"
    roots = data.get("roots")
    if not isinstance(roots, dict):
        return None, "fixture has no `roots` object"
    return data, None


# --------------------------------------------------------------------------
# classification -- pure functions over one node at a time.
# --------------------------------------------------------------------------


def _label_names(node: dict) -> set[str]:
    return {lab["name"] for lab in node.get("labels", []) if lab.get("name")}


def classify_type(labels: set[str]) -> str:
    for name in sorted(labels):
        if name.startswith("type:"):
            return name.split(":", 1)[1]
    for name in sorted(labels):
        if name.startswith("wayfinder:"):
            return name.split(":", 1)[1]
    return "untyped"


#: The three wayfinder labels that, absent an explicit `owner:` label, infer
#: `owner = joe` -- a decision Joe makes in conversation (grilling), a fact
#: that must be surfaced first (research), or something he needs to react to
#: (prototype). `wayfinder:task` is deliberately excluded: it names a type,
#: not an owner.
_WAYFINDER_INFERS_JOE = {"wayfinder:grilling", "wayfinder:research", "wayfinder:prototype"}


def classify_owner(labels: set[str]) -> str | None:
    for name in sorted(labels):
        if name.startswith("owner:"):
            return name.split(":", 1)[1]
    if labels & _WAYFINDER_INFERS_JOE:
        return "joe"
    return None


def classify_model(labels: set[str]) -> str | None:
    for name in sorted(labels):
        if name.startswith("model:"):
            return name.split(":", 1)[1]
    return None


def has_done_when(body: str) -> bool:
    return bool(_DONE_WHEN.search(body or ""))


def classify(node: dict) -> dict:
    """Classify one node. Does not recurse: `children` on the result is the
    node's own raw children, untouched -- `classify_tree` below classifies
    them and replaces this field. Kept separate so `classify` stays a pure,
    single-node function callable directly in tests without building a tree.
    """
    labels = _label_names(node)
    raw_children = node.get("children", [])
    leaf = not any(child.get("state") == "open" for child in raw_children)
    blocked_by = (node.get("issue_dependencies_summary") or {}).get("blocked_by", 0) or 0
    assignee = node.get("assignee")
    assignee_login = assignee.get("login") if assignee else None
    state = node.get("state", "open")
    ready = state == "open" and leaf and assignee_login is None and blocked_by == 0
    return {
        "number": node["number"],
        "title": node.get("title", ""),
        "state": state,
        "body": node.get("body") or "",
        "type": classify_type(labels),
        "owner": classify_owner(labels),
        "model": classify_model(labels),
        "assignee": assignee_login,
        "blocked_by": blocked_by,
        "leaf": leaf,
        "ready": ready,
        "children": raw_children,
    }


def classify_tree(node: dict) -> dict:
    """`classify`, applied recursively; `children` holds classified subtrees."""
    result = classify(node)
    result["children"] = [classify_tree(child) for child in node.get("children", [])]
    return result


def flatten(node: dict) -> list[dict]:
    """Pre-order walk of an already-classified tree: the node, then each child."""
    out = [node]
    for child in node.get("children", []):
        out.extend(flatten(child))
    return out


# --------------------------------------------------------------------------
# frontier and warnings -- pure functions over a flat list of classified nodes.
# --------------------------------------------------------------------------


def frontier(nodes: list[dict]) -> list[tuple[str | None, str | None, list[dict]]]:
    """Ready leaves grouped by (owner, model), in tree order.

    Group order is first-appearance order in `nodes` (which callers pass in
    tree order), and nodes within a group keep that same tree order -- no
    alphabetic re-sort, so the list reads the way the tree does.
    """
    groups: dict[tuple[str | None, str | None], list[dict]] = {}
    order: list[tuple[str | None, str | None]] = []
    for node in nodes:
        if not node["ready"]:
            continue
        key = (node["owner"], node["model"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(node)
    return [(owner, model, groups[(owner, model)]) for owner, model in order]


def warnings(nodes: list[dict], next_text: str | None) -> list[str]:
    """One line per problem. `next_text` is `None` when NEXT.md could not be
    read -- that is reported as UNREADABLE by the caller, not folded in here,
    so this function never needs to distinguish "no NEXT.md" from "no items".
    """
    out: list[str] = []
    for node in nodes:
        if node["state"] != "open" or not node["leaf"]:
            continue
        if node["owner"] is None:
            out.append(f"#{node['number']} is an open leaf with no owner -- {node['title']}")
        if node["owner"] == "agent":
            if node["model"] is None:
                out.append(
                    f"#{node['number']} is owner:agent with no model: label -- {node['title']}"
                )
            if not has_done_when(node["body"]):
                out.append(
                    f"#{node['number']} is owner:agent with no 'Done when' line in its body "
                    f"-- {node['title']}"
                )
    if next_text is not None:
        for item in still_open_items_without_a_ticket(next_text):
            first_line = item.splitlines()[0].strip()
            out.append(f"Still-open item names no ticket besides #3: {first_line}")
    return out


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def _tree_lines(node: dict, depth: int = 0) -> list[str]:
    indent = "  " * depth
    owner = node["owner"] or "-"
    model = node["model"] or "-"
    assignee = node["assignee"] or "-"
    state_suffix = f"  [{node['state']}]" if node["state"] == "closed" else ""
    lines = [
        f"{indent}#{node['number']}  {node['type']}  {owner}  {model}  {assignee}  "
        f"blocked:{node['blocked_by']}  {node['title']}{state_suffix}"
    ]
    for child in node["children"]:
        lines.extend(_tree_lines(child, depth + 1))
    return lines


def _frontier_header(owner: str | None, model: str | None) -> str:
    if owner == "joe":
        return "waiting on Joe"
    owner_label = owner or "- (no owner)"
    model_label = model or "-"
    return f"owner:{owner_label}  model:{model_label}"


def render(
    trees: list[dict],
    all_nodes: list[dict],
    warning_lines: list[str],
    unreadable_reasons: list[str],
) -> str:
    out: list[str] = []
    add = out.append

    add("TREE")
    add("----")
    for tree in trees:
        add(f"root #{tree['number']}  {tree['title']}")
        for child in tree["children"]:
            add("\n".join(_tree_lines(child, depth=1)))
        add("")

    add("FRONTIER")
    add("--------")
    groups = frontier(all_nodes)
    if not groups:
        add("none ready")
    for owner, model, group_nodes in groups:
        add(_frontier_header(owner, model))
        for node in group_nodes:
            add(f"  #{node['number']}  {node['title']}")
    add("")

    add("WARNINGS")
    add("--------")
    if not warning_lines:
        add("none")
    for line in warning_lines:
        add(line)
    add("")

    for reason in unreadable_reasons:
        add(f"UNREADABLE  {reason}")
    if unreadable_reasons:
        add("")

    ready_count = sum(1 for n in all_nodes if n["ready"])
    warn_count = len(warning_lines)
    unreadable_count = len(unreadable_reasons)
    code = verdict_code(ready_count, warn_count, unreadable_count)
    add(
        f"VERDICT  READY {ready_count}  WARNINGS {warn_count}  "
        f"UNREADABLE {unreadable_count}  -> exit {code}"
    )
    return "\n".join(out) + "\n"


def verdict_code(ready_count: int, warn_count: int, unreadable_count: int) -> int:
    if unreadable_count:
        return 3
    if warn_count:
        return 1
    return 0


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def _default_next_path() -> Path:
    return Path(__file__).resolve().parent.parent / "tasks" / "NEXT.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backlog board over map #3 and backlog root #80 (read-only).",
        epilog="exit 0 clean; 1 one or more warnings; 3 a tree or NEXT.md could not be read.",
    )
    parser.add_argument("--json", action="store_true", help="dump the classified tree as JSON")
    parser.add_argument(
        "--fixture", default=None, help="read issues from a JSON file instead of calling gh"
    )
    parser.add_argument(
        "--next", default=None, help="path to NEXT.md (default: tasks/NEXT.md next to this repo)"
    )
    args = parser.parse_args(argv)

    # Issue bodies (never titles, checked against the committed fixture) carry
    # arbitrary unicode -- an arrow, an em dash -- and Windows' default
    # console codepage (cp1252) cannot encode all of it. Reconfigure rather
    # than strip: stripping would silently change what `--json` reports.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    unreadable_reasons: list[str] = []
    trees: list[dict] = []

    if args.fixture is not None:
        fixture_data, err = load_fixture(Path(args.fixture))
        if fixture_data is None:
            unreadable_reasons.append(err or "fixture unreadable")
        else:
            for root in ROOTS:
                raw = fixture_data["roots"].get(str(root))
                if raw is None:
                    unreadable_reasons.append(f"fixture has no root #{root}")
                    continue
                trees.append(classify_tree(raw))
    else:
        for root in ROOTS:
            raw, err = fetch_tree(root)
            if raw is None:
                unreadable_reasons.append(f"#{root}: {err}")
                continue
            trees.append(classify_tree(raw))

    next_path = Path(args.next) if args.next else _default_next_path()
    next_text: str | None
    try:
        next_text = next_path.read_text(encoding="utf-8")
    except OSError as exc:
        next_text = None
        unreadable_reasons.append(f"{next_path}: {exc}")

    all_nodes: list[dict] = []
    for tree in trees:
        all_nodes.extend(flatten(tree))

    warning_lines = warnings(all_nodes, next_text)

    if args.json:
        print(json.dumps(trees, indent=2, ensure_ascii=False))
        ready_count = sum(1 for n in all_nodes if n["ready"])
        return verdict_code(ready_count, len(warning_lines), len(unreadable_reasons))

    print(render(trees, all_nodes, warning_lines, unreadable_reasons), end="")
    ready_count = sum(1 for n in all_nodes if n["ready"])
    return verdict_code(ready_count, len(warning_lines), len(unreadable_reasons))


if __name__ == "__main__":
    sys.exit(main())

import {
  DISPLAY_TIME_ZONE,
  displayZoneLabel,
  fetchPlaybook,
  type ConfigVersion,
  type Lesson,
} from "@/lib/api";

import FiveStepTest from "@/components/FiveStepTest";

export const dynamic = "force-dynamic";

/**
 * What rules were in force, and how much evidence exists under each.
 *
 * Every recommendation carries the strategy version it was made under, and
 * nothing read that column back until this page. It matters because a config
 * edit splits the record into halves that cannot be compared, and the halves
 * look exactly like one continuous record when totalled.
 *
 * The load-bearing rendering decision: **an empty lessons list is not
 * "nothing to report".** `lessons` has one writer -- the Historian -- and
 * nothing that runs calls it. So the empty state says the agent has never run,
 * for the same reason the Dashboards screen distinguishes an unbuilt warehouse
 * from an empty one.
 */
export default async function PlaybookPage() {
  let playbook;
  try {
    playbook = await fetchPlaybook();
  } catch {
    return (
      <Shell>
        <p className="text-muted">Backend unreachable.</p>
      </Shell>
    );
  }

  const { config_versions: versions, lessons, proposals_awaiting_approval } =
    playbook;

  return (
    <Shell>
      <header className="mb-10">
        <h1 className="display text-4xl sm:text-5xl">Playbook</h1>
        <p className="mt-3 max-w-xl text-lg text-muted">
          The rules that were in force when each observation was recorded. A
          threshold change splits the evidence into halves that cannot be
          pooled, so the split is shown rather than summed away.
        </p>
      </header>

      {proposals_awaiting_approval.length > 0 && (
        <section className="mb-10 rounded-2xl border border-accent/50 bg-card p-6">
          <div className="text-xs font-semibold uppercase tracking-widest text-accent">
            Awaiting your decision
          </div>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            {proposals_awaiting_approval.length} proposed config change
            {proposals_awaiting_approval.length === 1 ? "" : "s"}. Proposals are
            inert &mdash; nothing here has been applied, and nothing applies one
            without you.
          </p>
        </section>
      )}

      {/* Above the version cards, deliberately: they answer an archivist's
          question, the five steps answer "what do I do in the next twenty
          seconds", and on a phone the thing you act on goes where the thumb
          lands first. */}
      <FiveStepTest />

      <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
        Strategy versions
      </h2>
      <p className="mt-2 text-sm text-muted">{playbook.note}</p>

      {versions.length === 0 ? (
        <p className="mt-6 text-sm text-muted">
          No strategy version recorded yet. One is written the first time a pass
          prices anything.
        </p>
      ) : (
        <ul className="mt-6 space-y-4">
          {versions.map((version) => (
            <VersionCard
              key={version.version}
              version={version}
              floor={playbook.min_rows_to_mean_anything}
            />
          ))}
        </ul>
      )}

      <h2 className="mt-12 text-sm font-semibold uppercase tracking-widest text-muted">
        Lessons
      </h2>

      {!playbook.historian_has_run ? (
        <div className="mt-6 rounded-2xl border bg-card p-6">
          <div className="font-mono text-sm font-semibold">
            The Historian has never run
          </div>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            This is <em>not</em>{" "}
            &ldquo;no lessons found&rdquo;. The agent that
            writes them is built and tested and is called by nothing that runs,
            so this list would be empty however much the record contained.
            Saying so is the point: an empty list rendered as a healthy silence
            over a disconnected wire is worse than no list at all.
          </p>
        </div>
      ) : (
        <ul className="mt-6 space-y-4">
          {lessons.map((lesson) => (
            <LessonCard key={lesson.id} lesson={lesson} />
          ))}
        </ul>
      )}
    </Shell>
  );
}

function VersionCard({
  version,
  floor,
}: {
  version: ConfigVersion;
  floor: number;
}) {
  const changes = Object.entries(version.changed_from_previous);

  return (
    <li className="rounded-2xl border bg-card p-6">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="display text-2xl">v{version.version}</span>
        {version.is_current && (
          <span className="rounded-full bg-positive/15 px-2 py-0.5 text-xs font-semibold text-positive">
            current
          </span>
        )}
        <span className="text-xs text-muted">
          from {stamp(version.effective_from_ms)}
          {version.effective_to_ms ? ` to ${stamp(version.effective_to_ms)}` : ""}
        </span>
      </div>

      {version.rationale && (
        <p className="mt-3 text-sm leading-relaxed text-muted">
          {version.rationale}
        </p>
      )}

      {/*
        One column at 320px, and that is measured rather than chosen.
        `grid-cols-2` there gives each column 103px against a 137px label, and
        the text paints over its neighbour *without overflowing anything* --
        `minmax(0, 1fr)` lets a column shrink below its own content, so
        scrollWidth stays exactly equal to the viewport and the page reads as
        clean. This is the "CONSENSUSKALSHI" defect the Board had, and only the
        per-element check in `scripts/check_mobile.py` sees it.
      */}
      <dl className="mt-4 grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label="Recommendations" value={version.recommendations} />
        <Stat label="Markets" value={version.markets} />
        <Stat label="Unsuppressed" value={version.unsuppressed} />
        <Stat label="Actionable" value={version.actionable} />
        <Stat label="CLV scored" value={version.clv_scored} />
      </dl>

      {!version.has_enough_to_say_anything && (
        <p className="mt-4 text-sm text-muted">
          {/*
            `{floor} observations` on two source lines renders as
            "100observations" -- JSX drops the whitespace around a newline that
            follows an expression. Only looking at the page finds this; the
            overflow check cannot, and neither can a test on the payload.
          */}
          Fewer than {floor}{" "}
          observations under this version, so nothing measured here supports a
          conclusion on its own. Reported rather than hidden: a starved version
          shortened its neighbours&rsquo; samples too.
        </p>
      )}

      {changes.length > 0 && (
        <div className="mt-4 border-t pt-4">
          <div className="text-xs font-semibold uppercase tracking-widest text-muted">
            Changed from v{version.version - 1}
          </div>
          {/*
            A table is the wrong shape on a phone and a scrolling one is worse,
            so this is a list of rows that wrap. `break-words` because a config
            key is a long unbroken token and one of those widens the document,
            which costs every page its right edge rather than just this one.
          */}
          <ul className="mt-2 space-y-1 font-mono text-xs">
            {changes.map(([key, change]) => (
              <li key={key} className="break-words">
                <span className="text-muted">{key}</span>{" "}
                <span className="text-negative">{render(change.from)}</span>
                {" → "}
                <span className="text-positive">{render(change.to)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}

function LessonCard({ lesson }: { lesson: Lesson }) {
  return (
    <li className="rounded-2xl border bg-card p-6">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h3 className="text-lg font-bold tracking-tight">{lesson.title}</h3>
        {lesson.accepted_by_user === null && lesson.proposed_config_diff && (
          <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent">
            awaiting decision
          </span>
        )}
        {lesson.accepted_by_user === false && (
          <span className="rounded-full bg-negative/15 px-2 py-0.5 text-xs font-semibold text-negative">
            rejected
          </span>
        )}
      </div>
      <p className="mt-2 text-sm leading-relaxed text-muted">{lesson.body}</p>
      <p className="mt-3 text-xs text-muted">
        {/*
          `n` before the effect size, per the measurement rules. A lesson
          without a sample size is an anecdote, and it is the number
          `validate_proposals` refuses on.
        */}
        {lesson.sample_size === null
          ? "No sample size recorded — treat as an anecdote."
          : `n = ${lesson.sample_size}`}
      </p>
    </li>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs uppercase tracking-widest text-muted">{label}</dt>
      <dd className="mt-0.5 font-mono text-lg">{value.toLocaleString()}</dd>
    </div>
  );
}

/**
 * `2026-08-08 23:24 PDT`. Pacific, with the zone named.
 *
 * This printed UTC on the argument that "the record is stamped in it", which is
 * true and is not a reason: the record is *stored* in UTC and stays that way,
 * and this is a label a human reads. Naming the zone is what makes the change
 * safe -- a bare `2026-08-08 23:24` that used to mean UTC and now means Pacific
 * would silently re-date every version boundary on this page by seven hours.
 * With `PDT` on the end, an old screenshot and a new one cannot be confused.
 */
function stamp(ms: number): string {
  const d = new Date(ms).toLocaleString("sv-SE", {
    timeZone: DISPLAY_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${d} ${displayZoneLabel(ms)}`;
}

function render(value: unknown): string {
  if (value === null || value === undefined) return "unset";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-3xl px-6 py-12 sm:py-16">{children}</div>;
}

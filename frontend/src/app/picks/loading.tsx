import { SHELL_WIDTH } from "@/lib/shell";

/**
 * What the Picks tab shows while `/api/slate` is still answering.
 *
 * The first `loading.tsx` under `app/`, and it exists because this route is
 * the first to sit in a nav slot behind a ~6-second cold fetch (#8 amendment
 * 4). Without it the tap renders nothing until the payload lands, and on this
 * desk nothing has two readings — "no favourites tonight" and "not here yet"
 * — that mean opposite things. This says which one it is, in words, and draws
 * no list shape: a skeleton of rows is a promise about what is coming.
 */
export default function PicksLoading() {
  return (
    <div className={`${SHELL_WIDTH} px-6 py-12 sm:py-16 xl:px-8`}>
      <h1 className="text-2xl font-extrabold tracking-tight">Picks</h1>
      <p className="mt-4 max-w-prose text-sm text-muted" aria-live="polite">
        Reading tonight&rsquo;s prices &mdash; not empty, not yet answered.
      </p>
    </div>
  );
}

/**
 * The landing screen is the Slate — every game, priced, with the edge as a
 * column rather than a gate.
 *
 * It was the Board until 2026-08-20, and the change is the first item of the
 * fleet convening's diagnosis (docs/reviews/2026-08-20-fleet-convening.md):
 * the Board is the filter whose output had been `surfaced: 0` for 1,005
 * consecutive passes, so the screen a phone opens on was the one screen
 * guaranteed to be empty — while the screen Joe asked for on 2026-08-09
 * (`/slate`, its own docstring records the request) sat behind a nav word a
 * beginner cannot tell from three others. The Board still exists, one tap
 * away at `/board`, exactly as `/builder`, `/rejections` and `/dashboards`
 * are still served from their old paths.
 *
 * A re-export rather than a copy: two routes rendering one component cannot
 * drift apart, which is this repo's two-implementations rule applied to a
 * page.
 */
export { default } from "./slate/page";
export const dynamic = "force-dynamic";

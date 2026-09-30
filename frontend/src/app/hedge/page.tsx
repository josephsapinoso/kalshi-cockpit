import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

/**
 * `/hedge` moved onto `/bets#open` (#240, Joe's 234 A, 2026-09-30): what he
 * holds is the top section of Your bets, rendered by the same
 * `HedgePositions` off the same `/api/hedge` read. This route stays served
 * because the Discord alerts and old bookmarks link here; it answers with a
 * redirect and renders nothing of its own.
 */
export default function HedgePage(): never {
  redirect("/bets#open");
}

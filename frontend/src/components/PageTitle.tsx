/**
 * The one heading style for every page (#394). Two variants only: `page`
 * for a tab page's own name, `detail` for a matchup heading (`/market`,
 * `/game`). `page` is sized at `2xl/3xl`, not the `4xl/5xl` three tabs used
 * to carry, because `/bets` (#248) puts the net figure (`3xl/4xl`) above the
 * page's own name on purpose -- the money is the largest type on that
 * screen, and a shared style has to fit under it everywhere, not just there.
 */
const VARIANTS = {
  page: "display text-2xl sm:text-3xl",
  detail: "display text-3xl sm:text-4xl xl:text-5xl",
} as const;

export default function PageTitle({
  children,
  variant = "page",
}: {
  children: React.ReactNode;
  variant?: keyof typeof VARIANTS;
}) {
  return <h1 className={VARIANTS[variant]}>{children}</h1>;
}

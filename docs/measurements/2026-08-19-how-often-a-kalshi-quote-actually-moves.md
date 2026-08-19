# 84.5% of quote rows are byte-identical to the row before them, and the share is not a constant

Taken 2026-08-19 19:05-19:25Z on live (`a482fea`). The input to the decision in
`2026-08-19-the-prune-loses-to-the-writer.md`: the prune cannot win at any
schedule, so the writer has to write less, and this is how much less there is to
have.

## What this establishes

That across the live slate, **84.5%** of consecutive quote observations for the
same ticker are identical in every stored field; that the figure is stable
across two independent methods; and -- the part that matters more than the
headline -- that it is **not one number but two**, split by whether anyone is
trading the market yet.

## What it does not

It does not establish that 84.5% will hold. It is a property of *what is on the
slate*, not of Kalshi, and the slate is seasonal. See the per-series table: the
saving is carried by markets for games that are days away.

It does not measure in-play behaviour. Every reading here is pre-game.

It reads through a `mode=ro` connection, so it sees the last checkpoint and not
the last ~12 minutes. That is harmless *here* and worth stating anyway: the
comparison is between rows inside one snapshot, so staleness shifts the window
without biasing the ratio. It is not harmless for counts -- see the correction
in the prune file.

## Two methods, and the first one was wrong

```
census   all 5,963 markets across one real 47.2s pass gap    85.1% unchanged
sample   700 tickers, 2,075 consecutive pairs, per-series    84.5% unchanged
```

These agree. **An earlier sample said 97.8% and was biased**, and the way it was
biased is worth keeping: it drew tickers from

```sql
SELECT ticker FROM kalshi_markets ORDER BY last_seen_ms DESC LIMIT 4000
```

and then took every eighth. `last_seen_ms` is written by the same upsert loop
for every market in a pass, so it ties across thousands of rows and the order
within a tie is insertion order -- which is series order. Taking every eighth of
that samples a *few series densely*, not the slate evenly, and the series it
happened to land on are the ones that never move.

**It agreed with nothing and was believed for four minutes because it pointed
the same way as the real answer.** A sample drawn on a column with massive ties
is not a random sample; it is a scan of whatever the table's physical order
happens to be.

## The split, which is the actual finding

Per series, ordered by share of the slate:

| series | share of slate | pairs | unchanged |
|---|---|---|---|
| `KXNCAAFSPREAD` | 26.7% | 561 | **99.1%** |
| `KXNCAAFTOTAL` | 19.0% | 405 | **99.0%** |
| `KXMLBTB` | 7.2% | 144 | 57.6% |
| `KXNFLSPREAD` | 6.4% | 135 | 80.0% |
| `KXMLBHIT` | 5.8% | 129 | 60.5% |
| `KXNCAAFGAME` | 5.6% | 114 | **99.1%** |
| `KXNFLTOTAL` | 4.8% | 102 | 98.0% |
| `KXMLBTEAMTOTAL` | 4.4% | 79 | 62.0% |
| `KXMLBRBI` | 4.0% | 87 | 73.6% |
| `KXMLBTOTAL` | 3.5% | 66 | 51.5% |

**Two populations.** College football and NFL markets sit at 98-99% unchanged;
today's baseball markets sit at **51-74%**. The pooled 84.5% is a weighted
average of a nearly-static majority and an active minority, and the majority is
static because nobody is trading a game that is days out -- not because Kalshi
quotes are sticky.

**So the pooled number is the wrong one to design against.** `KXNCAAFSPREAD` and
`KXNCAAFTOTAL` alone are 45.7% of the slate at ~99% unchanged. As NFL and NBA
come into season -- both within weeks, as `retention.py` already notes -- the
active share rises and the saving falls.

## What it means for the write rate

At the measured 84.5%, writing only on change takes the load from **7.77M
rows/day to ~1.20M/day**, against a prune ceiling of 3.84M/day. That is a
comfortable margin.

**At the pessimistic end it is not comfortable.** If the slate were all as
active as today's baseball -- call it 55% unchanged -- the write rate lands at
**~3.5M/day against a 3.84M/day ceiling**. That is a 9% margin on a prune that
must never be skipped, and the prune is skipped whenever a window is open.

So: writing only on change is necessary and, on this evidence, **not obviously
sufficient on its own**. The honest framing for the ADR is that it buys back
the margin that was never there, and that the prune's ceiling is still worth
raising rather than treated as solved.

## Why this is the right cut and not an arbitrary one

Rows are compared on `(yes_bid_tenths, yes_bid_qty, no_bid_tenths, no_bid_qty)`
-- every field `store_quotes_from_discovery` writes apart from `ticker`,
`observed_ms`, `seq` and `source`. So "unchanged" here means *the row would have
carried no information the previous row did not*, which is exactly the condition
under which not writing it loses nothing.

It does **not** mean the observation was worthless. Knowing a quote is *still*
the same at a later time is information, and it is the information the 30s
Kalshi staleness rule runs on. Any implementation must keep that, and it cannot
keep it in a row it did not write.

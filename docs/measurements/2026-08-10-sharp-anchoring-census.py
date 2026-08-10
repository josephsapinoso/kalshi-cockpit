"""Sharp anchoring, measured on the record's own rows -- the harness.

Run read-only against the LIVE database on 2026-08-10:

    flyctl ssh console -a kalshi-cockpit \
      -C "python -c exec(__import__(\'base64\').b64decode(\'<this file, b64>\'))"

The container has no `sqlite3` binary, only Python, and the connection is
opened as `file:/data/cockpit.db?mode=ro`. Nothing is written and no Odds API
credit is spent: `odds_snapshots` is append-only and stores every book, while
sharp anchoring is a READ-time filter (`runner.py:658` -> `devig.py:290-291`),
so the whole question is answerable from rows already on disk.

`SHARP_BOOKS` is pinned here from `runner.py:103`. If that constant changes,
this file is wrong and must be re-derived rather than adjusted.

The recommendation population is pinned to `id <= 1564` so that it is the same
1,564 rows as `docs/measurements/2026-08-10-clean-shortfall-pull.json`. The
table had already grown to 1,676 rows by the time this ran; the extra 112 are
excluded deliberately.

WHAT THIS MEASUREMENT DOES NOT ESTABLISH
  - It does not establish that the sharp books are RIGHT. It counts how many
    books were dropped and how often the filter bound; nothing here compares a
    sharp price to an outcome.
  - It does not establish why `betfair_ex_uk` is absent. It establishes only
    that it is absent. Region gating is a hypothesis this data cannot separate
    from "the key is not returned for these sports at all".
  - It does not establish that the 423 wide-consensus rows are a fair test of
    a wide-consensus strategy. They are the instants where the sharps had NOT
    yet quoted, which is a selected subset -- thinner, earlier, MLB-heavy.
  - It carries no interval and performs no significance test. Every figure is
    a complete enumeration of a fixed population, not an estimate of one.
  - `market='h2h'` throughout. The engine has never written a fair price about
    a spread or a total, so there is nothing to measure there.
  - It says nothing about rows created after 2026-08-09 23:37, when odds
    fetching stopped and the runner began re-reading one stored instant.
"""

# Run as FOUR separate passes, in this order, each its own `python -c`. They are
# concatenated here in the order they were executed; each reopens its own
# read-only connection. Output is transcribed verbatim in
# `2026-08-10-sharp-anchoring-on-the-record-run.txt`.
#
# Pass 1 reproduces the census (Q1-Q5 of scripts/sql/odds_book_census.sql) and
#        re-derives it per event.
# Pass 2 joins the census to the record: `anchored_on_sharp`, the pinned 1,564,
#        and the scope identity.
# Pass 3 reconstructs `odds_age_ms` and `books_used` from the raw snapshots.
# Pass 4 computes the per-ROW unit, which is the one the ADR's claim is about.


# ==========================================================================
# PASS 1
# ==========================================================================
import sqlite3, json, statistics as st
c = sqlite3.connect("file:/data/cockpit.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
q = lambda s, p=(): [dict(r) for r in c.execute(s, p).fetchall()]
def med(xs): return st.median(xs) if xs else None
SB = ('pinnacle','betfair_ex_eu','betfair_ex_uk','matchbook')
P = print

P("=== A. REPRODUCE Q5 scope (h2h) ===")
P(q("SELECT COUNT(*) rows,COUNT(DISTINCT odds_event_id) ev,COUNT(DISTINCT bookmaker) bk,"
    "datetime(MIN(fetched_ms)/1000,'unixepoch') t0,datetime(MAX(fetched_ms)/1000,'unixepoch') t1 "
    "FROM odds_snapshots WHERE market='h2h'"))
P("=== A2. scope ALL markets ===")
P(q("SELECT market,COUNT(*) rows,COUNT(DISTINCT odds_event_id) ev,COUNT(DISTINCT bookmaker) bk,"
    "datetime(MIN(fetched_ms)/1000,'unixepoch') t0,datetime(MAX(fetched_ms)/1000,'unixepoch') t1 "
    "FROM odds_snapshots GROUP BY market"))
P("=== A3. sport_key breakdown h2h ===")
P(q("SELECT sport_key,COUNT(*) rows,COUNT(DISTINCT odds_event_id) ev FROM odds_snapshots WHERE market='h2h' GROUP BY sport_key"))

PI = q("SELECT odds_event_id oe,fetched_ms fm,sport_key sk,COUNT(DISTINCT bookmaker) n_all,"
       "COUNT(DISTINCT CASE WHEN bookmaker IN %s THEN bookmaker END) n_sharp "
       "FROM odds_snapshots WHERE market='h2h' GROUP BY odds_event_id,fetched_ms" % (SB,))
P("=== B. Q1 per-instant, n=%d ===" % len(PI))
na=[r['n_all'] for r in PI]; ns=[r['n_sharp'] for r in PI]; nd=[a-s for a,s in zip(na,ns)]
P("available min/med/max", min(na), med(na), max(na))
P("sharp     min/med/max", min(ns), med(ns), max(ns))
P("discarded min/med/max", min(nd), med(nd), max(nd))
P("=== C. Q3 bind ===")
from collections import Counter
cs=Counter(ns)
for k in sorted(cs): P(k, cs[k], round(100*cs[k]/len(PI),1))
P("=== D. Q2 distribution FULL ===")
cd=Counter((r['n_all'],r['n_sharp']) for r in PI)
for k,v in sorted(cd.items(),key=lambda x:-x[1]): P("avail",k[0],"sharp",k[1],"disc",k[0]-k[1],"->",v)
P("=== E. Q4 sharp coverage, h2h ===")
P(q("SELECT bookmaker,COUNT(DISTINCT odds_event_id) ev,COUNT(*) quotes FROM odds_snapshots "
    "WHERE market='h2h' AND bookmaker IN %s GROUP BY bookmaker ORDER BY quotes DESC" % (SB,)))
P("=== E2. betfair_ex_uk ANY market ANY time ===")
P(q("SELECT COUNT(*) n FROM odds_snapshots WHERE bookmaker='betfair_ex_uk'"))
P("=== E3. ALL bookmakers ever seen, any market ===")
P(q("SELECT bookmaker,market,COUNT(*) n,COUNT(DISTINCT odds_event_id) ev FROM odds_snapshots GROUP BY bookmaker,market ORDER BY bookmaker,market"))
P("=== E4. betfair-like names ===")
P(q("SELECT DISTINCT bookmaker FROM odds_snapshots WHERE bookmaker LIKE '%betfair%' OR bookmaker LIKE '%match%' OR bookmaker LIKE '%pinn%'"))

P("=== F. PER-EVENT re-derivation (event-weighted) ===")
byev={}
for r in PI: byev.setdefault(r['oe'],[]).append(r)
ev_med_all=[]; ev_med_sharp=[]; ev_med_disc=[]; ev_instants=[]
for oe,rs in byev.items():
    ev_instants.append((oe,len(rs)))
    ev_med_all.append(med([x['n_all'] for x in rs]))
    ev_med_sharp.append(med([x['n_sharp'] for x in rs]))
    ev_med_disc.append(med([x['n_all']-x['n_sharp'] for x in rs]))
P("events",len(byev))
P("median across events of per-event median available:", med(ev_med_all))
P("median across events of per-event median sharp    :", med(ev_med_sharp))
P("median across events of per-event median discarded:", med(ev_med_disc))
P("per-event median-available distribution:", sorted(Counter(ev_med_all).items()))
P("per-event median-sharp distribution    :", sorted(Counter(ev_med_sharp).items()))
P("=== F2. instants per event, dominance ===")
ev_instants.sort(key=lambda x:-x[1])
P("top 10:",ev_instants[:10])
P("instants-per-event min/med/max:",min(x[1] for x in ev_instants),med([x[1] for x in ev_instants]),max(x[1] for x in ev_instants))
tot=sum(x[1] for x in ev_instants)
P("largest event share of instants: %d/%d = %.1f%%"%(ev_instants[0][1],tot,100*ev_instants[0][1]/tot))
P("top5 share: %.1f%%"%(100*sum(x[1] for x in ev_instants[:5])/tot))
P("=== F3. events with ZERO sharp at every instant vs mixed ===")
allzero=[oe for oe,rs in byev.items() if all(x['n_sharp']==0 for x in rs)]
anyzero=[oe for oe,rs in byev.items() if any(x['n_sharp']==0 for x in rs)]
P("events where sharp==0 at EVERY instant:",len(allzero))
P("events where sharp==0 at ANY instant:",len(anyzero))
P("instants with sharp==0 that belong to all-zero events:",sum(len(byev[o]) for o in allzero))
P("=== F4. sharp==0 instants: their n_all and sport ===")
z=[r for r in PI if r['n_sharp']==0]
P("n_all distribution among sharp==0:",sorted(Counter(x['n_all'] for x in z).items()))
P("sport distribution among sharp==0:",sorted(Counter(x['sk'] for x in z).items()))
P("sport distribution among ALL instants:",sorted(Counter(x['sk'] for x in PI).items()))
P("=== F5. n_all < 2 instants ===")
P("instants with n_all<2:",sum(1 for r in PI if r['n_all']<2))
P("their events:",sorted(Counter(r['oe'] for r in PI if r['n_all']<2).items())[:10])

P("=== G. THE RECORD: fair_prices ===")
P(q("SELECT COUNT(*) n,COUNT(DISTINCT link_id) links,datetime(MIN(computed_ms)/1000,'unixepoch') t0,"
    "datetime(MAX(computed_ms)/1000,'unixepoch') t1 FROM fair_prices"))
P("--- fair_prices by market ---")
P(q("SELECT market,COUNT(*) n FROM fair_prices GROUP BY market"))
P("--- anchored_on_sharp distribution ---")
P(q("SELECT anchored_on_sharp,COUNT(*) n,COUNT(DISTINCT link_id) links,COUNT(DISTINCT computed_ms) instants "
    "FROM fair_prices GROUP BY anchored_on_sharp"))
P("--- anchored x book_count ---")
P(q("SELECT anchored_on_sharp,book_count,COUNT(*) n FROM fair_prices GROUP BY 1,2 ORDER BY 1,2"))
P("--- market_width by anchored ---")
P(q("SELECT anchored_on_sharp,COUNT(*) n,SUM(market_width IS NULL) nullwidth,ROUND(MIN(market_width),4) mn,"
    "ROUND(AVG(market_width),4) avg,ROUND(MAX(market_width),4) mx FROM fair_prices GROUP BY 1"))
P("--- books_used sample for anchored=0 ---")
P(q("SELECT books_used,COUNT(*) n FROM fair_prices WHERE anchored_on_sharp=0 GROUP BY books_used ORDER BY n DESC LIMIT 8"))
P("--- books_used sample for anchored=1 ---")
P(q("SELECT books_used,COUNT(*) n FROM fair_prices WHERE anchored_on_sharp=1 GROUP BY books_used ORDER BY n DESC LIMIT 8"))

P("=== H. RECOMMENDATIONS joined to fair_prices.anchored_on_sharp ===")
P(q("SELECT COUNT(*) n,datetime(MIN(created_ms)/1000,'unixepoch') t0,datetime(MAX(created_ms)/1000,'unixepoch') t1,"
    "COUNT(DISTINCT created_ms) instants,COUNT(DISTINCT link_id) links FROM recommendations"))
P("--- recs by anchored_on_sharp ---")
P(q("SELECT f.anchored_on_sharp a,COUNT(*) n,COUNT(DISTINCT r.link_id) links,COUNT(DISTINCT r.created_ms) instants "
    "FROM recommendations r LEFT JOIN fair_prices f ON f.id=r.fair_price_id GROUP BY 1"))
P("--- recs by anchored x surfaced/suppression ---")
cols=[r['name'] for r in q("PRAGMA table_info(recommendations)")]
P("rec cols:",cols)
if 'surfaced' in cols:
    P(q("SELECT f.anchored_on_sharp a,r.surfaced s,COUNT(*) n FROM recommendations r "
        "LEFT JOIN fair_prices f ON f.id=r.fair_price_id GROUP BY 1,2 ORDER BY 1,2"))
if 'suppression_reasons' in cols:
    P(q("SELECT f.anchored_on_sharp a,r.suppression_reasons sr,COUNT(*) n FROM recommendations r "
        "LEFT JOIN fair_prices f ON f.id=r.fair_price_id GROUP BY 1,2 ORDER BY 1,3 DESC"))
P("--- recs book_count distribution by anchored ---")
P(q("SELECT f.anchored_on_sharp a,r.book_count bc,COUNT(*) n FROM recommendations r "
    "LEFT JOIN fair_prices f ON f.id=r.fair_price_id GROUP BY 1,2 ORDER BY 1,2"))

P("=== I. WHICH ODDS INSTANTS WERE ACTUALLY CONSUMED ===")
# for each fair_prices row, the odds instant it read = MAX(fetched_ms) <= computed_ms for that odds_event_id
rows=q("SELECT f.id fid,f.computed_ms cm,f.anchored_on_sharp a,f.book_count bc,e.odds_event_id oe "
       "FROM fair_prices f JOIN event_links e ON e.id=f.link_id WHERE f.market='h2h'")
inst_by_ev={}
for r in PI: inst_by_ev.setdefault(r['oe'],[]).append(r)
for v in inst_by_ev.values(): v.sort(key=lambda x:x['fm'])
consumed=set(); mism=0; matched=0; nomatch=0
agree=Counter()
for r in rows:
    cand=[x for x in inst_by_ev.get(r['oe'],[]) if x['fm']<=r['cm']]
    if not cand: nomatch+=1; continue
    inst=cand[-1]; matched+=1
    consumed.add((r['oe'],inst['fm']))
    agree[(inst['n_sharp']==0, r['a']==0)]+=1
P("fair_prices h2h rows:",len(rows),"matched to an instant:",matched,"no prior instant:",nomatch)
P("distinct instants CONSUMED by the runner:",len(consumed),"of",len(PI),"stored instants")
P("agreement (census sharp==0, stored anchored==0) -> count:",dict(agree))
cons_sharp0=sum(1 for oe,fm in consumed if any(x['fm']==fm and x['n_sharp']==0 for x in inst_by_ev[oe]))
P("consumed instants with census n_sharp==0:",cons_sharp0,"=%.1f%%"%(100*cons_sharp0/max(1,len(consumed))))
P("=== I2. instants NEVER consumed ===")
never=[r for r in PI if (r['oe'],r['fm']) not in consumed]
P("never consumed:",len(never),"of which n_sharp==0:",sum(1 for r in never if r['n_sharp']==0))
P("=== J. record odds observation window (created_ms - odds_age_ms) ===")
if 'odds_age_ms' in cols:
    P(q("SELECT COUNT(*) n,COUNT(DISTINCT created_ms-odds_age_ms) instants,"
        "datetime((MIN(created_ms-odds_age_ms))/1000,'unixepoch') t0,"
        "datetime((MAX(created_ms-odds_age_ms))/1000,'unixepoch') t1 FROM recommendations"))
P("=== K. suppression config in DB ===")
P(q("SELECT * FROM strategy_configs ORDER BY version DESC LIMIT 3"))
c.close()

# ==========================================================================
# PASS 2
# ==========================================================================
import sqlite3, statistics as st
from collections import Counter
c = sqlite3.connect("file:/data/cockpit.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
q = lambda s,p=(): [dict(r) for r in c.execute(s,p).fetchall()]
P=print; med=lambda xs: st.median(xs) if xs else None
SB=('pinnacle','betfair_ex_eu','betfair_ex_uk','matchbook')
PIN=1564

P("=== L. recs total vs PINNED population (id<=1564) ===")
P(q("SELECT COUNT(*) n,MIN(id) mn,MAX(id) mx FROM recommendations"))
P(q("SELECT COUNT(*) n,datetime(MIN(created_ms)/1000,'unixepoch') t0,datetime(MAX(created_ms)/1000,'unixepoch') t1 FROM recommendations WHERE id<=?", (PIN,)))
P("=== L2. anchored_on_sharp on the PINNED 1564 ===")
P(q("SELECT f.anchored_on_sharp a,COUNT(*) n,COUNT(DISTINCT r.link_id) links,COUNT(DISTINCT r.created_ms) cycles,"
    "COUNT(DISTINCT r.created_ms-r.odds_age_ms) obs_instants "
    "FROM recommendations r LEFT JOIN fair_prices f ON f.id=r.fair_price_id WHERE r.id<=? GROUP BY 1",(PIN,)))
P("=== L3. anchored NULL/unjoined check ===")
P(q("SELECT COUNT(*) n FROM recommendations r WHERE r.id<=? AND (r.fair_price_id IS NULL OR NOT EXISTS(SELECT 1 FROM fair_prices f WHERE f.id=r.fair_price_id))",(PIN,)))
P("=== L4. pinned: anchored x suppressed_reason ===")
P(q("SELECT f.anchored_on_sharp a,COALESCE(r.suppressed_reason,'(none)') sr,COUNT(*) n FROM recommendations r "
    "LEFT JOIN fair_prices f ON f.id=r.fair_price_id WHERE r.id<=? GROUP BY 1,2 ORDER BY 1,3 DESC",(PIN,)))
P("=== L5. pinned: anchored x fair book_count ===")
P(q("SELECT f.anchored_on_sharp a,f.book_count bc,COUNT(*) n FROM recommendations r "
    "JOIN fair_prices f ON f.id=r.fair_price_id WHERE r.id<=? GROUP BY 1,2 ORDER BY 1,2",(PIN,)))
P("=== L6. pinned: per-link contribution of anchored=0 rows ===")
r0=q("SELECT r.link_id li,COUNT(*) n FROM recommendations r JOIN fair_prices f ON f.id=r.fair_price_id "
     "WHERE r.id<=? AND f.anchored_on_sharp=0 GROUP BY 1 ORDER BY 2 DESC",(PIN,))
tot=sum(x['n'] for x in r0)
P("links contributing anchored=0:",len(r0),"total rows",tot)
P("top 8:",r0[:8])
if tot: P("largest link share: %.1f%%  top3 %.1f%%"%(100*r0[0]['n']/tot,100*sum(x['n'] for x in r0[:3])/tot))
P("=== L7. pinned: per-link contribution of ALL rows ===")
ra=q("SELECT r.link_id li,COUNT(*) n FROM recommendations r WHERE r.id<=? GROUP BY 1 ORDER BY 2 DESC",(PIN,))
P("links:",len(ra),"top 8:",ra[:8],"largest share %.1f%%"%(100*ra[0]['n']/sum(x['n'] for x in ra)))
P("=== L8. pinned: anchored=0 by league (via event_links.league) ===")
P(q("SELECT e.league lg,f.anchored_on_sharp a,COUNT(*) n FROM recommendations r "
    "JOIN fair_prices f ON f.id=r.fair_price_id JOIN event_links e ON e.id=r.link_id WHERE r.id<=? GROUP BY 1,2 ORDER BY 1,2",(PIN,)))
P("=== L9. pinned: anchored x clv scored ===")
P(q("SELECT f.anchored_on_sharp a,SUM(r.clv_tenths IS NOT NULL) scored,COUNT(*) n FROM recommendations r "
    "JOIN fair_prices f ON f.id=r.fair_price_id WHERE r.id<=? GROUP BY 1",(PIN,)))
P("=== L10. pinned: distinct odds observation instants overall ===")
P(q("SELECT COUNT(DISTINCT created_ms-odds_age_ms) obs, COUNT(DISTINCT created_ms) cycles,"
    "datetime((MIN(created_ms-odds_age_ms))/1000,'unixepoch') t0,datetime((MAX(created_ms-odds_age_ms))/1000,'unixepoch') t1 "
    "FROM recommendations WHERE id<=?",(PIN,)))

P("=== M. SCOPE: does the census cover the record's odds observations? ===")
P("census h2h fetched_ms window:")
P(q("SELECT datetime(MIN(fetched_ms)/1000,'unixepoch') f0,datetime(MAX(fetched_ms)/1000,'unixepoch') f1,"
    "datetime(MIN(book_updated_ms)/1000,'unixepoch') b0,datetime(MAX(book_updated_ms)/1000,'unixepoch') b1,"
    "SUM(book_updated_ms IS NULL) nullstamps FROM odds_snapshots WHERE market='h2h'"))
P("=== M2. exact join: rec -> the instant it read -> oldest book stamp ===")
recs=q("SELECT r.id rid,r.created_ms cm,r.odds_age_ms oa,r.link_id li,e.odds_event_id oe,f.anchored_on_sharp a,f.books_used bu "
       "FROM recommendations r JOIN event_links e ON e.id=r.link_id LEFT JOIN fair_prices f ON f.id=r.fair_price_id WHERE r.id<=?",(PIN,))
snap=q("SELECT odds_event_id oe,fetched_ms fm,bookmaker bk,book_updated_ms bu,outcome_name onm FROM odds_snapshots WHERE market='h2h'")
inst={}
for s in snap: inst.setdefault((s['oe'],s['fm']),[]).append(s)
byev={}
for (oe,fm) in inst: byev.setdefault(oe,[]).append(fm)
for v in byev.values(): v.sort()
import json as J
ok=0; bad=0; nomatch=0; consumed=Counter(); anch_check=Counter()
for r in recs:
    fms=[f for f in byev.get(r['oe'],[]) if f<=r['cm']]
    if not fms: nomatch+=1; continue
    fm=fms[-1]; consumed[(r['oe'],fm)]+=1
    rows_=inst[(r['oe'],fm)]
    used=set(J.loads(r['bu'])) if r['bu'] else set()
    ages=[(x['bu'] if x['bu'] is not None else fm) for x in rows_ if x['bk'] in used]
    recon=r['cm']-r['oa']
    if ages and min(ages)==recon: ok+=1
    else: bad+=1
    nsharp=len({x['bk'] for x in rows_ if x['bk'] in SB})
    anch_check[(nsharp==0, r['a']==0)]+=1
P("recs pinned:",len(recs),"reconstruction exact:",ok,"mismatch:",bad,"no prior instant:",nomatch)
P("(census n_sharp==0, stored anchored==0) -> count:",dict(anch_check))
P("distinct instants CONSUMED by pinned recs:",len(consumed),"of 234 stored")
cz=[k for k in consumed if len({x['bk'] for x in inst[k] if x['bk'] in SB})==0]
P("consumed instants with n_sharp==0:",len(cz),"=%.1f%% of consumed"%(100*len(cz)/max(1,len(consumed))))
P("rows attributable to those instants:",sum(consumed[k] for k in cz))
P("rows per consumed instant: min/med/max",min(consumed.values()),med(list(consumed.values())),max(consumed.values()))
P("=== M3. never-consumed instants ===")
allinst=set(inst)
never=allinst-set(consumed)
P("never consumed:",len(never),"of which n_sharp==0:",sum(1 for k in never if len({x['bk'] for x in inst[k] if x['bk'] in SB})==0))
P("=== M4. census restricted to CONSUMED instants only ===")
na=[];ns=[]
for k in consumed:
    rows_=inst[k]
    na.append(len({x['bk'] for x in rows_})); ns.append(len({x['bk'] for x in rows_ if x['bk'] in SB}))
P("consumed instants n=%d available min/med/max"%len(na),min(na),med(na),max(na))
P("sharp min/med/max",min(ns),med(ns),max(ns))
P("discarded min/med/max",min(a-s for a,s in zip(na,ns)),med([a-s for a,s in zip(na,ns)]),max(a-s for a,s in zip(na,ns)))
P("sharp==0 share of consumed instants: %.1f%%"%(100*sum(1 for x in ns if x==0)/len(ns)))
P("ROW-weighted: available med",med([len({x['bk'] for x in inst[k]}) for k in consumed.elements()]),
  "sharp med",med([len({x['bk'] for x in inst[k] if x['bk'] in SB}) for k in consumed.elements()]))
c.close()

# ==========================================================================
# PASS 3
# ==========================================================================
import sqlite3, os, json as J, statistics as st
from collections import Counter
P=print; med=lambda xs: st.median(xs) if xs else None
P("=== N. live env regions ===")
P("ODDS_REGIONS =", repr(os.environ.get("ODDS_REGIONS")))
P("ODDS_MARKETS =", repr(os.environ.get("ODDS_MARKETS")))
c=sqlite3.connect("file:/data/cockpit.db?mode=ro",uri=True); c.row_factory=sqlite3.Row
q=lambda s,p=():[dict(r) for r in c.execute(s,p).fetchall()]
P("=== N2. api_credits sample ===")
P(q("SELECT * FROM api_credits ORDER BY id DESC LIMIT 2"))
PIN=1564
SB=('pinnacle','betfair_ex_eu','betfair_ex_uk','matchbook')

P("=== O. odds_age reconstruction, CORRECT subset (all books quoting every outcome) ===")
snap=q("SELECT odds_event_id oe,fetched_ms fm,bookmaker bk,book_updated_ms bu,outcome_name onm FROM odds_snapshots WHERE market='h2h'")
inst={}
for s in snap: inst.setdefault((s['oe'],s['fm']),[]).append(s)
byev={}
for (oe,fm) in inst: byev.setdefault(oe,[]).append(fm)
for v in byev.values(): v.sort()
def full_books(rows_):
    outs=[]
    for r in rows_:
        if r['onm'] not in outs: outs.append(r['onm'])
    bb={}
    for r in rows_: bb.setdefault(r['bk'],set()).add(r['onm'])
    return {b for b,s in bb.items() if all(o in s for o in outs)}
recs=q("SELECT r.id rid,r.created_ms cm,r.odds_age_ms oa,e.odds_event_id oe,f.anchored_on_sharp a "
       "FROM recommendations r JOIN event_links e ON e.id=r.link_id JOIN fair_prices f ON f.id=r.fair_price_id WHERE r.id<=?",(PIN,))
ok=bad=0; diffs=[]
for r in recs:
    fms=[f for f in byev.get(r['oe'],[]) if f<=r['cm']]
    if not fms: continue
    rows_=inst[(r['oe'],fms[-1])]
    fb=full_books(rows_)
    ages=[x['bu'] for x in rows_ if x['bk'] in fb]
    if ages and min(ages)==r['cm']-r['oa']: ok+=1
    else:
        bad+=1; diffs.append((r['cm']-r['oa'])-(min(ages) if ages else 0))
P("pinned recs joined:",len(recs),"exact:",ok,"mismatch:",bad)
if diffs: P("mismatch delta ms: min/med/max",min(diffs),med(diffs),max(diffs),"n distinct",len(set(diffs)))
P("=== O2. do the fetch instants agree with fair_prices.books_used exactly? ===")
fps=q("SELECT f.id fid,f.computed_ms cm,f.books_used bu,f.book_count bc,f.anchored_on_sharp a,e.odds_event_id oe "
      "FROM fair_prices f JOIN event_links e ON e.id=f.link_id WHERE f.market='h2h'")
agree=miss=0
for f in fps:
    fms=[x for x in byev.get(f['oe'],[]) if x<=f['cm']]
    if not fms: miss+=1; continue
    rows_=inst[(f['oe'],fms[-1])]
    fb=full_books(rows_)
    sharp={b for b in fb if b in SB}
    expect=sorted(sharp) if sharp else sorted(fb)
    agree += (expect==J.loads(f['bu']))
P("fair_prices h2h:",len(fps),"books_used reproduced exactly from the census:",agree,"no prior instant:",miss)

P("=== P. the 614 clean rows, by anchoring ===")
P(q("SELECT f.anchored_on_sharp a,COUNT(*) n,COUNT(DISTINCT r.link_id) links,"
    "COUNT(DISTINCT r.created_ms-r.odds_age_ms) obs,SUM(r.clv_tenths IS NOT NULL) scored "
    "FROM recommendations r JOIN fair_prices f ON f.id=r.fair_price_id "
    "WHERE r.id<=? AND r.suppressed_reason IS NULL GROUP BY 1",(PIN,)))
P("=== P2. edge distribution among clean rows, by anchoring ===")
P(q("SELECT f.anchored_on_sharp a,COUNT(*) n,SUM(r.edge_tenths>0) pos,ROUND(MIN(r.edge_tenths),2) mn,"
    "ROUND(AVG(r.edge_tenths),3) avg,ROUND(MAX(r.edge_tenths),2) mx,SUM(r.reference_contracts>0) refpos "
    "FROM recommendations r JOIN fair_prices f ON f.id=r.fair_price_id "
    "WHERE r.id<=? AND r.suppressed_reason IS NULL GROUP BY 1",(PIN,)))
P("=== P3. ALL 1564 by anchoring: edge + market_width ===")
P(q("SELECT f.anchored_on_sharp a,COUNT(*) n,SUM(r.edge_tenths>0) pos,ROUND(MAX(r.edge_tenths),2) mx,"
    "ROUND(AVG(f.market_width),4) w,SUM(f.market_width IS NULL) wnull,ROUND(MAX(f.market_width),4) wmx "
    "FROM recommendations r JOIN fair_prices f ON f.id=r.fair_price_id WHERE r.id<=? GROUP BY 1",(PIN,)))
P("=== P4. per-link view of the 189 clean anchored=0 rows ===")
r0=q("SELECT r.link_id li,e.league lg,COUNT(*) n FROM recommendations r JOIN fair_prices f ON f.id=r.fair_price_id "
     "JOIN event_links e ON e.id=r.link_id WHERE r.id<=? AND f.anchored_on_sharp=0 AND r.suppressed_reason IS NULL "
     "GROUP BY 1,2 ORDER BY 3 DESC",(PIN,))
tot=sum(x['n'] for x in r0)
P("links:",len(r0),"rows:",tot,"top6:",r0[:6])
if tot: P("largest link share %.1f%%  top3 %.1f%%"%(100*r0[0]['n']/tot,100*sum(x['n'] for x in r0[:3])/tot))
P("=== P5. clean anchored=0: distinct obs instants and cycles ===")
P(q("SELECT COUNT(DISTINCT r.created_ms-r.odds_age_ms) obs,COUNT(DISTINCT r.created_ms) cycles,"
    "COUNT(DISTINCT r.ticker) tickers FROM recommendations r JOIN fair_prices f ON f.id=r.fair_price_id "
    "WHERE r.id<=? AND f.anchored_on_sharp=0 AND r.suppressed_reason IS NULL",(PIN,)))
P("=== P6. sanity: total clean rows ===")
P(q("SELECT COUNT(*) n FROM recommendations WHERE id<=? AND suppressed_reason IS NULL",(PIN,)))
P("=== Q. was any row ever surfaced/actionable, by anchoring? ===")
P(q("SELECT f.anchored_on_sharp a,SUM(r.suggested_contracts>0) sug,SUM(r.reference_contracts>0) ref,COUNT(*) n "
    "FROM recommendations r JOIN fair_prices f ON f.id=r.fair_price_id WHERE r.id<=? GROUP BY 1",(PIN,)))
c.close()

# ==========================================================================
# PASS 4
# ==========================================================================
import sqlite3, statistics as st
from collections import Counter
P=print; med=lambda xs: st.median(xs) if xs else None
c=sqlite3.connect("file:/data/cockpit.db?mode=ro",uri=True); c.row_factory=sqlite3.Row
q=lambda s,p=():[dict(r) for r in c.execute(s,p).fetchall()]
PIN=1564; SB={'pinnacle','betfair_ex_eu','betfair_ex_uk','matchbook'}
snap=q("SELECT odds_event_id oe,fetched_ms fm,bookmaker bk,outcome_name onm FROM odds_snapshots WHERE market='h2h'")
inst={}
for s in snap: inst.setdefault((s['oe'],s['fm']),[]).append(s)
byev={}
for (oe,fm) in inst: byev.setdefault(oe,[]).append(fm)
for v in byev.values(): v.sort()
stat={}
for k,rows_ in inst.items():
    outs=[]
    for r in rows_:
        if r['onm'] not in outs: outs.append(r['onm'])
    bb={}
    for r in rows_: bb.setdefault(r['bk'],set()).add(r['onm'])
    allb=set(bb); full={b for b,s in bb.items() if all(o in s for o in outs)}
    stat[k]=(len(allb),len(full),len(full&SB),len(allb-full))
P("=== R. per-INSTANT: all-books vs USABLE (quoted every outcome) ===")
v=list(stat.values())
P("n instants",len(v))
P("all-books   min/med/max",min(x[0] for x in v),med([x[0] for x in v]),max(x[0] for x in v))
P("USABLE      min/med/max",min(x[1] for x in v),med([x[1] for x in v]),max(x[1] for x in v))
P("sharp kept  min/med/max",min(x[2] for x in v),med([x[2] for x in v]),max(x[2] for x in v))
P("discarded(from USABLE) min/med/max",min(x[1]-x[2] for x in v),med([x[1]-x[2] for x in v]),max(x[1]-x[2] for x in v))
P("books dropped for partial quote: total",sum(x[3] for x in v),"instants affected",sum(1 for x in v if x[3]))
P("=== R2. per-EVENT (event-weighted, median of per-event medians) ===")
ev={}
for (oe,fm),s in stat.items(): ev.setdefault(oe,[]).append(s)
P("events",len(ev))
P("USABLE   ",med([med([x[1] for x in rs]) for rs in ev.values()]))
P("kept     ",med([med([x[2] for x in rs]) for rs in ev.values()]))
P("discarded",med([med([x[1]-x[2] for x in rs]) for rs in ev.values()]))
P("=== R3. per-ROW (the 1564 pinned recommendation rows) ===")
recs=q("SELECT r.id rid,r.created_ms cm,e.odds_event_id oe,f.anchored_on_sharp a,f.book_count bc "
       "FROM recommendations r JOIN event_links e ON e.id=r.link_id JOIN fair_prices f ON f.id=r.fair_price_id WHERE r.id<=?",(PIN,))
rowstat=[]; bcchk=0
for r in recs:
    fms=[x for x in byev.get(r['oe'],[]) if x<=r['cm']]
    s=stat[(r['oe'],fms[-1])]
    rowstat.append(s)
    bcchk += (r['bc']==(s[2] if s[2] else s[1]))
P("rows",len(rowstat),"stored book_count == recomputed selected size:",bcchk)
P("USABLE   min/med/max",min(x[1] for x in rowstat),med([x[1] for x in rowstat]),max(x[1] for x in rowstat))
P("kept     min/med/max",min(x[2] for x in rowstat),med([x[2] for x in rowstat]),max(x[2] for x in rowstat))
P("discarded min/med/max",min(x[1]-x[2] for x in rowstat),med([x[1]-x[2] for x in rowstat]),max(x[1]-x[2] for x in rowstat))
P("mean discarded %.2f"%(sum(x[1]-x[2] for x in rowstat)/len(rowstat)))
P("row-level (usable,kept) top cells:",Counter((x[1],x[2]) for x in rowstat).most_common(8))
P("=== R4. per-row restricted to the 614 CLEAN rows ===")
clean=q("SELECT r.id rid,r.created_ms cm,e.odds_event_id oe FROM recommendations r JOIN event_links e ON e.id=r.link_id "
        "WHERE r.id<=? AND r.suppressed_reason IS NULL",(PIN,))
cs=[stat[(r['oe'],[x for x in byev[r['oe']] if x<=r['cm']][-1])] for r in clean]
P("rows",len(cs),"USABLE med",med([x[1] for x in cs]),"kept med",med([x[2] for x in cs]),"discarded med",med([x[1]-x[2] for x in cs]))
P("=== R5. instants where USABLE < 2 ===")
P("instants:",sum(1 for x in v if x[1]<2),"; pinned rows reading such an instant:",sum(1 for x in rowstat if x[1]<2))
P("pinned rows with stored book_count<2:",q("SELECT COUNT(*) n FROM recommendations r JOIN fair_prices f ON f.id=r.fair_price_id WHERE r.id<=? AND f.book_count<2",(PIN,)))
P("of those, suppressed too_few_books:",q("SELECT COUNT(*) n FROM recommendations r JOIN fair_prices f ON f.id=r.fair_price_id WHERE r.id<=? AND f.book_count<2 AND r.suppressed_reason LIKE '%too_few_books%'",(PIN,)))
P("=== R6. max sharp per instant ever = ? ===")
P("max kept over all instants:",max(x[2] for x in v),"; instants with kept==4:",sum(1 for x in v if x[2]==4))
c.close()

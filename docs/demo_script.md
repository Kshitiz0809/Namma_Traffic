# Demo Video Script (3-5 minutes)

Phase 6 Task 6. Structure: Problem → Prediction → Alert → Recommendation →
Impact. Every number/example below is real (see `docs/demo_scenarios.md`,
`docs/baseline_results.md` for sourcing) — nothing here is scripted fiction.

Target runtime: **4 minutes**. Timestamps are cumulative targets, not hard cuts.

---

## [0:00–0:30] Problem (30s)

> "Bengaluru traffic police logged 298,450 parking violations over about
> five months. Every one of those is enforcement *after the fact* — a
> ticket for something that already happened. There's no system today
> that says: 'this junction is about to become a hotspot in the next
> hour, send a patrol now.' That's what we built."

**Visual:** Raw data scroll or `docs/data_quality_report.md` stats. Cut to
the architecture diagram (`docs/architecture_diagram.png`) for 3-4 seconds.

---

## [0:30–1:45] Prediction (75s)

> "We trained three models — CatBoost, LightGBM, XGBoost — to predict
> whether a given zone will become a hotspot in the next 60 minutes.
> CatBoost won, with a validation PR-AUC of 0.8767. But we didn't stop at
> 'it scored well' — we stress-tested it. We checked: does it generalize
> to locations it's never seen? It didn't — a 7.88% accuracy drop on
> unseen H3 cells, which we're showing you, not hiding. We checked: is it
> just memorizing the location ID? No — removing the location identifier
> entirely only cost 0.55% accuracy, so the model is leaning on real
> behavioral patterns, not just 'this place is always bad.'"

**Visual:** Live demo — run `python -m app.models.demo_seed growth --fast`
showing the real hotspot-growth sequence at Elite Junction, 2023-12-23
(risk score climbing from ~54 to a peak of ~67 as scooter violations
cluster between 3-4 AM). Or show the Analytics View's model comparison chart.

> "Watch this — this is a real night at a real junction. As violations
> cluster between 3 and 4 AM, our risk score climbs in real time, then
> decays as the surge passes. No manual rules — this is a Hawkes-decay
> feature reacting to actual events."

---

## [1:45–2:45] Alert (60s)

> "Every zone above a risk threshold becomes an alert — color-coded GREEN
> to RED, the same way you'd triage anything else. Each alert tells you
> not just the score, but *why*: the top contributing factors, whether
> it's an escalation, and a direct recommendation."

**Visual:** Live Risk Map view (or the alert queue table in Operations
View) — point at a few markers/rows of different colors. Show one ORANGE
alert's popup with its contributing factors.

> "This map only uses OpenStreetMap tiles for rendering — every prediction
> underneath is from our own internal data. No external traffic feed, no
> third-party hotspot service."

---

## [2:45–3:45] Recommendation (60s)

> "Here's where it gets specific. Same risk score, different vehicles,
> different outcomes. A MAXI-CAB — a large commercial vehicle — parked at
> Safina Plaza Junction, a location with a real history of concentrated
> violations, gets escalated all the way to a tow-operation candidate. A
> car in a less concentrated context gets a lighter-touch patrol
> recommendation. This is rule-based — no LLM, no black box — you can read
> the exact YAML file that drives this decision."

**Visual:** Run `python -m app.models.demo_seed recommendations --fast`,
showing the real escalation output. Cut briefly to
`docs/recommendation_rules.yaml`.

> "And if we get a location we've truly never seen before, the system
> says so honestly — 'no historical data, here's a conservative default'
> — instead of guessing. We built that limitation into the product, not
> just into a report nobody reads."

---

## [3:45–4:00] Impact (15s)

> "Six phases, every one tested against the real dataset, every limitation
> disclosed instead of hidden. This isn't a demo that only works on a happy
> path — it's a decision-support tool that tells you when it doesn't know,
> as clearly as when it does."

**Visual:** Final shot of the Analytics View or the architecture diagram,
fade to a slide listing: 100+ tests passing, 6 committed phases, real
metrics throughout.

---

## Recording checklist
- [ ] Backend running (`uvicorn app.main:app --port 8000`)
- [ ] Frontend running (`npm run dev` in `frontend/`) if showing the dashboard live
- [ ] `demo_seed.py` scenarios pre-tested with `--fast` to confirm no errors before recording without it (full pacing looks better on camera)
- [ ] Screen resolution set for clean recording (1440×900 or similar)
- [ ] Have `docs/baseline_results.md`, `docs/spatial_holdout.md`, `docs/recommendation_rules.yaml` open in tabs for quick cuts if asked follow-up questions live

# Demo Scenarios — Best 3 Walkthrough

Phase 6 Task 4. All three scenarios below use **real historical data**
replayed through the **frozen** Phase 3/4/5 models (no retraining, no
fabricated numbers) via `backend/app/models/demo_seed.py`. Run:

```bash
cd backend
python -m app.models.demo_seed all          # paced for a live demo
python -m app.models.demo_seed all --fast   # no pacing delays, for testing
# or individually: replay | growth | recommendations
```

---

## Scenario 1 — Alert Replay

**What it shows:** the system processing a stream of real validation-period
events in chronological order, computing probability/risk/recommendation
for each — as if watching a live feed (no live streaming pipeline exists
yet, Phase 7; this replays real historical timestamps instead).

**Real output:**
```
[2024-02-19 21:34:46+00:00] No Junction    prob=0.64 risk=28.3 (LOW) -> Monitor
[2024-02-20 01:27:46+00:00] No Junction    prob=0.31 risk=13.6 (LOW) -> Monitor
[2024-02-20 04:37:46+00:00] No Junction    prob=0.68 risk=29.7 (LOW) -> Monitor
[2024-02-20 07:12:46+00:00] No Junction    prob=0.18 risk=8.0  (LOW) -> Monitor
[2024-02-20 22:22:46+00:00] No Junction    prob=0.65 risk=28.5 (LOW) -> Monitor
```

**Narration for the demo:** "Each row here is a real violation event from
the dataset, fed through our frozen models in the order it actually
happened. The system scores hotspot probability, computes a risk score 0-100,
and assigns a recommendation — all in milliseconds, all explainable."

---

## Scenario 2 — Hotspot Growth (Elite Junction, 2023-12-23)

**What it shows:** a REAL escalating sequence — found by searching the
dataset for the cell with the highest `rolling_hotspot_intensity` peak
among named junctions (`8960145b553ffff`, BTP040 - Elite Junction). On the
night of 2023-12-23, a surge of scooter/motorcycle violations beginning
around 03:00 drives the 15-minute violation count from single digits to a
peak of 39, and risk score from the mid-50s to a peak around 67.

**Real output (sampled across the surge):**
```
[00:02:46] 15m_count=10  intensity=186.9  risk=54.4  ###########################
[03:09:46] 15m_count= 2  intensity=182.3  risk=60.3  ##############################
[03:23:46] 15m_count=13  intensity=193.0  risk=64.5  ################################
[03:31:46] 15m_count=28  intensity=221.2  risk=66.3  #################################
[03:38:46] 15m_count=34  intensity=226.5  risk=67.2  #################################  <- peak
[04:09:46] 15m_count=23  intensity=271.7  risk=62.9  ###############################
[07:29:46] 15m_count= 6  intensity=291.2  risk=56.3  ############################
[23:57:46] 15m_count= 1  intensity=201.5  risk=53.4  ##########################
```

**Narration for the demo:** "This is one real night at Elite Junction. Watch
the risk score climb as two-wheeler violations cluster between 3 and 4 AM,
then decay as the surge passes — `rolling_hotspot_intensity` (Phase 2's
Hawkes-decay feature) tracks this naturally, no manual rules needed. This
is exactly the kind of pattern the Live Risk Map would have flagged YELLOW
or ORANGE in real time, if it had existed then."

---

## Scenario 3 — Recommendation Engine Range (escalation to Tow Candidate)

**What it shows:** the full range of the rule-based recommendation engine,
anchored on one real, verified high-risk example — and the cold-start
safety behavior.

**Real escalation example:** BTP051 - Safina Plaza Junction, 2024-02-23
03:35:46, a MAXI-CAB violation.
```
Real example - BTP051 - Safina Plaza Junction, vehicle=MAXI-CAB:
  -> risk=47.52, band=CRITICAL, recommendation=Tow operation candidate, escalated=True
```
This row's base risk band was HIGH; the rule engine escalated it to
CRITICAL because (a) MAXI-CAB is a high-obstruction vehicle type and (b)
Safina Plaza Junction's historical concentration exceeds the named-junction
escalation threshold (`docs/recommendation_rules.yaml`).

**Contrast — a low-obstruction vehicle, same logic, no escalation:**
```
CAR at No Junction -> Monitor (escalated=False)
```

**Cold start — a zone with no historical data:**
```
ffffffffffffff -> Monitor (conservative default, not a fabricated prediction)
```

**Narration for the demo:** "The same risk score doesn't always mean the
same action. A MAXI-CAB blocking a known hotspot junction gets escalated
toward a tow operation; a car in a less concentrated context gets a lighter
touch. And if we've genuinely never seen a location before, the system
says so honestly instead of guessing — that's the spatial-holdout
limitation from Phase 3.5, built into the product behavior, not just a
footnote in a report."

---

## How these examples were found (for credibility, if asked)

- Scenario 2's cell: `features.groupby('h3_cell')['rolling_hotspot_intensity'].max()`
  among named-junction cells, taking the top result.
- Scenario 3's example: filtered the real validation-set risk computation
  for HIGH-band rows where the recommendation engine's `escalated` flag was
  `True`, then picked one with a clean, demo-friendly vehicle type (MAXI-CAB).
- All three are reproducible by re-running `demo_seed.py` — nothing here
  was hand-tuned or cherry-picked beyond "pick a clear example of a real
  pattern that already exists in the data."

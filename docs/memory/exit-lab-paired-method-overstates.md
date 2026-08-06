---
name: exit-lab-paired-method-overstates
description: "The Friday exit-lab's paired same-entry method stacks overlapping positions the desk cannot hold — score exits on a sequential one-position-per-slot sim."
metadata: 
  node_type: memory
  type: project
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-01T10:38:33.967Z
---

Found 2026-08-01 while sweeping grind_long's exit. The exit ladder's **paired same-entry** method lets one slot hold several positions simultaneously, which the live desk cannot do. On identical tape it scored grind's loaded default at **+$2,961**; a **sequential one-position-per-slot** sim scored the same config **−$2,115**. A $5,076 swing from position accounting alone.

The sequential sim is the one that matches reality: 72%/28% stop/target and 4.8-min median hold vs the live desk's 67%/27% and 3.5 min.

This is what made the reported grind MED-TREND cell (+$10.3/tr @ 59% win) invert to −$5.19/signal @ 46% win once re-run long-side-only on 250 ms ticks — the original had also pooled grind_short into a long-only decision.

**Why:** overlapping-entry accounting inflates every config, but it inflates *tight* exits most (more entries fit inside the same window), so it systematically biases the ladder toward small Rs — exactly the wrong direction for a desk whose profit lives in the tail.

**How to apply:** score every exit verdict on a sequential one-position-per-slot sim before trusting it. Treat any per-signal sweep on overlapping entries as unverified. Distinct from [[sims-on-tick-price]] (tick vs bar repricing) and [[shadow-sim-understates-losses]] (every reprice is a ceiling) — this is a third, independent way a sim lies. Related: [[exit-architecture-scar-tissue]] — the arming lever measured 3–5× the exit lever on the same tape.

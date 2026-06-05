# Still To Do

## What we still need from the client

- [ ] Exact delivery time windows for each client type, especially hospitals and any high-priority pharmacies.
- [ ] Whether time windows are hard rules or soft preferences for each client.
- [ ] More precise travel-time data, ideally by time of day, for Paris and the suburbs.
- [ ] Whether we can assume a simple average travel time for the prototype or must model rush-hour variation.
- [ ] The exact meaning of the 24-hour medical transit rule in operational terms.
- [ ] Whether any deliveries can be postponed to the afternoon or next day, and under what rules.
- [ ] Whether driver familiarity is only a preference or a hard constraint.
- [ ] How driver working hours and rest limits should be represented in the model.
- [ ] Whether there are any special loading or unloading rules at the warehouse or at client sites.
- [ ] Any examples of a truly bad Monday so we can test the prototype against a realistic worst case.

## What we should clarify for the prototype

- [ ] Decide if the first version will only assign deliveries to vehicles or also sequence stops within each route.
- [ ] Decide whether to include service times at each stop in the first prototype.
- [ ] Decide whether to add a simple repair step for disruptions like a sick driver or a fridge breakdown.
- [ ] Confirm the priority order: hospital first, refrigerated goods second, flexible pharmacy orders last.
- [ ] Confirm what message the demo should emphasize most: reliability, resilience, or simplicity.

## Honest assessment of current app

**What the current app does (capacity-packing demo):**
- ✅ Assigns deliveries to vehicles by capacity
- ✅ Sequences stops with nearest-neighbour
- ✅ Has a repair action for disruptions
- ✅ Shows chaos resilience

**What the current app is MISSING (required for real VRPTW):**
- ❌ Time-window constraints (client's #1 priority — hospital before 9am, etc.)
- ❌ Driver working hour enforcement (8-10 hour legal limits)
- ❌ 24-hour medical transit rule (from load time to delivery)
- ❌ Real travel times (currently synthetic coordinates only)
- ❌ Feasibility validation (no constraint checking engine)
- ❌ Data ingestion (random generation only, no real orders/clients)
- ❌ Explainability (no explanation for why delivery was deferred)
- ❌ Last-minute insertion handling (client pain point)
- ❌ KPI tracking (no metrics dashboard)
- ❌ Client preference modelling (unwritten rules like "pharmacy in 11th wants morning")

**Verdict:** Current app would be **useless to the client** — it's a capacity-packing demo, not a scheduling system. The client needs a real VRPTW solver that respects hard constraints.

---

## Phased implementation plan (tackle in this order)

### PHASE 1: Core constraint enforcement (MUST HAVE for minimal viability) ✅ COMPLETE
1. ✅ Add exact time-window model to Delivery (early, late, soft/hard flag)
2. ✅ Track departure time and arrival time per route
3. ✅ Enforce time-window feasibility in assignment
4. ✅ Add driver hour tracking (8-10 hour max) and enforce
5. ✅ Model 24-hour transit rule from load time
6. ✅ Build a constraint **violation checker** that audits all assignments
7. ⏭️ Add explainability engine (show which constraint blocked each delivery) — PARTIAL (shows reason, needs detail panel)

### PHASE 2: Data & realism (required for testing)
8. Build travel-time matrix (use time-of-day buckets or stub Google Maps API calls)
9. Implement CSV/Excel data ingestion (parse client orders into model)
10. Add client sensitivity/preference model (store unwritten rules)

### PHASE 3: Operations & resilience (required for production)
11. Handle urgent last-minute order insertion with constraint check
12. Improve repair heuristic to re-optimize routes post-disruption
13. Build KPI dashboard (hit-rate, deferred count, late minutes, overtime)
14. Create benchmark runner with realistic bad-Monday scenarios

### PHASE 4: Polish & handoff (school project milestones)
15. Refactor app.py into clean modular layers (solver core, UI, data)
16. Document assumptions and limitations clearly
17. Prepare presentation materials (gap analysis, roadmap, KPIs)

---

## What happens if we skip Phase 1?
- The app will continue to be a capacity demo
- It will **fail to catch time-window violations** (hospital missing 9am window)
- It will **not enforce driver hours** (legal risk)
- It will **not model medical compliance** (24-hour rule)
- The client will see it as "nice demo, but not usable"
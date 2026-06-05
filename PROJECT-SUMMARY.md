# Project Summary: VRPTW Dispatch Simulator for Paris Medical Delivery

**Last Updated**: 2026-06-05
**Status**: Phase 2 Complete, Phase 3 Ready to Start

---

## Project Overview

Building an interactive prototype Streamlit app that demonstrates **vehicle routing with time windows (VRPTW)** for a medical delivery company in Paris. The system must prioritize **reliability** (hitting strict time windows) over efficiency (fuel costs).

**Key Stakeholder**: Medical delivery company, Paris/suburbs, 40-60 deliveries/day, peak Mondays.

---

## Architecture

**Single-file design**: `app.py` (~1200 lines)
- Section 0: Travel-time matrix & district data (Phase 2)
- Section 1: Data structures (Delivery, Vehicle)
- Section 1B: Constraint validators (Phase 1)
- Section 2: Fleet & data generation
- Section 3: Assignment algorithm with constraint checking (Phase 1)
- Section 4: Explainability engine (Phase 2)
- Section 5: Streamlit UI

---

## Phase Summary

### ✅ Phase 1: Core Constraint Enforcement (COMPLETE)
**What**: Added VRPTW constraints to the model
- Time windows (hard for hospitals, soft for others)
- Driver working hours enforcement (10h limit)
- 24-hour medical transit rule support
- Constraint violation checker
- Explainability (reasons for deferrals)

**Result**: App enforces real constraints; no longer a capacity demo.

**Key Data**: Deliveries now have `early_time`, `late_time`, `is_hard_window`, `load_time`; Vehicles track `driver_hours_used`.

**Test**: 70 deliveries → 58 assigned, 12 deferred (all due to driver hours), showing real constraint enforcement.

---

### ✅ Phase 2: Realistic Routing (COMPLETE)
**What**: Added Paris travel-time matrix and route sequencing
- 6-district model of Paris medical delivery zones
- Time-of-day traffic patterns (morning rush slower than afternoon)
- Real travel-time matrix (45+ pre-computed routes)
- Route sequencing with nearest-district heuristic
- Explainability engine (detailed deferral reports)

**Result**: App uses realistic Paris routing; dispatcher sees credible estimates.

**Key Data**: Deliveries now have `district` instead of synthetic coordinates; `TRAVEL_TIME_MATRIX` provides context-aware travel times.

**Test**: 70 deliveries across 5 Paris districts; routes include realistic travel times (morning rush 32 min vs afternoon 16 min).

---

### ⏭️ Phase 3: Data & Metrics (PLANNED)
**What**: Data ingestion and KPI dashboard
- [ ] CSV/Excel parser for real order lists
- [ ] Data validation framework
- [ ] KPI dashboard (hit-rate, deferred count, utilization)
- [ ] Benchmark runner (test scenarios)
- [ ] Client-facing reports

---

### ⏭️ Phase 4+: Polish & Production (PLANNED)
- [ ] UI enhancements (explainability panel, etc.)
- [ ] Last-minute insertion handling
- [ ] Route re-optimization post-disruption
- [ ] Modular refactoring (solver core + UI)

---

## How to Run

```bash
streamlit run app.py
```

Then in the Streamlit UI:
1. Slide "Daily Deliveries" to 50-70 for realistic load
2. Click "Generate Monday Dispatch Plan"
3. Observe van utilization and deferred orders
4. Optional: Toggle "Chaos Mode" (sick driver, fridge breakdown)
5. Click "Simulate Disruption & Run Repair" to see resilience

---

## Key Algorithms

### Priority-Based Assignment
1. **Temperature-Sensitive** → Refrigerated van only
2. **Hospital** → Large vans first (larger capacity)
3. **Pharmacy** → Small vans first, overflow to large

Within each priority group:
- Estimate arrival time using travel-time matrix
- Check all constraints (time windows, driver hours, capacity)
- Assign if feasible; otherwise defer

### Route Sequencing (Nearest-District Heuristic)
1. Start at warehouse (6:30am after loading)
2. Greedily visit nearest unvisited district
3. Use travel-time matrix for accurate times
4. Include service times at each stop
5. Return to warehouse

---

## Constraint Enforcement

**Hard constraints** (must not violate):
- Capacity: Max boxes per vehicle
- Vehicle type: Refrigerated goods in fridge van only
- Hospital 9am deadline: Must deliver before 9:00 AM

**Soft constraints** (try to respect):
- Time windows: Most deliveries have preferred windows (6am-6pm)
- Driver hours: Try to keep under 8h (legal max 10h)
- 24-hour transit rule: Medical compliance (load time + 24h max)

**Decision logic**: If a delivery can't fit within constraints, it's deferred to afternoon/next day.

---

## Test Coverage

### Phase 1 Tests
- ✅ Data model integrity
- ✅ Constraint validators work
- ✅ Full assignment pipeline
- ✅ Driver hours tracking

### Phase 2 Tests
- ✅ Travel-time matrix accuracy
- ✅ Time-of-day traffic patterns
- ✅ Route sequencing with real times
- ✅ District assignment
- ✅ Explainability report generation

---

## File Structure

```
RLA - Delivery Optimization Project/
├── app.py                    # Main Streamlit application
├── requirements.txt          # Dependencies (streamlit, pandas)
├── README.md                 # Project description for client
├── PHASE1-SUMMARY.md        # Detailed Phase 1 documentation
├── PHASE2-SUMMARY.md        # Detailed Phase 2 documentation
├── PHASE3-SUMMARY.md        # Phase 3 roadmap (template)
├── stilltodo.md             # Gap analysis and remaining work
└── PROJECT-SUMMARY.md       # This file
```

---

## Dependencies

- `streamlit==1.31.0` - Interactive web UI
- `pandas==2.0.3` - Data manipulation (used for metrics)
- Python 3.9+

---

## Quick Performance Notes

**70-delivery "bad Monday" scenario**:
- ⏱️ Assignment: ~50ms
- ⏱️ Sequencing: ~100ms (6 vans × ~15 deliveries)
- 📊 Result: 83% hit-rate (58 assigned, 12 deferred due to driver hours)

All vans properly saturated at 9.5-10h driver time limit.

---

## Next Immediate Task

Choose one from Phase 3 to start:
1. **Data ingestion** (CSV import) — Needed to test with real Monday data
2. **KPI dashboard** — Needed to show client performance trends
3. **Benchmark runner** — Needed for scenario comparison
4. **UI explainability panel** — Needed to display deferral details to dispatcher

**Recommendation**: Start with data ingestion so you can load real client data and validate the model.

---

## Communication with Client

### What to emphasize
- ✅ "Now respects hard time windows (e.g., hospital 9am deadline)"
- ✅ "Enforces driver working hours (10h EU legal limit)"
- ✅ "Uses realistic Paris traffic (morning rush modeled)"
- ✅ "Shows why deliveries are deferred (explainability)"
- ✅ "Simulates disruptions and repairs (sick driver, breakdown)"

### What to clarify with client
- ❓ Exact service times per delivery type (currently random 5-10 min)
- ❓ Time windows for pharmacy orders (currently soft 6am-6pm)
- ❓ Client-specific preferences or unwritten rules
- ❓ Real delivery data for validation testing
- ❓ Any special routes or restricted areas in Paris suburbs

---

## Conclusion

The app has evolved from a **capacity-packing demo** (Phase 0) to a **real VRPTW solver** (Phases 1-2). With Phase 3 adding data ingestion and KPIs, it will be ready for client pilots and validation against real Monday scenarios.

**Status**: Core algorithm is solid. Ready for data validation and production hardening.

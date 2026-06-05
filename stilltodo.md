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

## My assessment

- We have enough information to build a strong **prototype** and explain the business problem clearly.
- We do **not** yet have enough information for a production-grade scheduling system.
- The biggest missing pieces are travel times, exact time windows, and how strict the human constraints really are.
- For the school project, that is acceptable as long as we state the assumptions clearly.
# Memo: Plant West weekly plan, what to change first

**To:** plant manager, Plant West (fictional) · **From:** Abdallah Shaheen · **Date:** 25.10.2026
**Basis:** CPLEX production-mix plan, checked with 20 simulated weeks per scenario (95% confidence intervals; scenario vs base as paired intervals with common random numbers). All plant data is invented.

## Bottom line
The optimal plan on paper (300 Sedans + 540 SUVs, €2.53 M margin a week) is **8% too optimistic**: the simulated line builds **769 ± 11 cars** and earns **€2.31 M**, €213k a week less. The cause is the SUV off-road calibration cell. The LP loads it to 100%, but 6% of SUVs fail the test and come back, so it really needs about 106%. **Add a second off-road cell first; do not fix the gap with bigger buffers.**

## What the scenarios show

| Option | Simulated cars / week | Margin vs base plan | Side effects |
|---|---|---|---|
| Base plan (today) | 769 ± 11 (plan 840) | – | Bottleneck: off-road calibration (19 of 20 runs) |
| Plan with the rework loop | 788 ± 11 | +€20k ± 16k | No investment; bottleneck moves to paint |
| 2nd off-road cell | 773 ± 10 | **+€81k ± 28k** | LP alone said +€35k; investment not included |
| Double buffers | 794 ± 11 | +€73k ± 14k | WIP 34 → 56 cars, lead time 3.6 → 5.6 h |
| 2nd off-road cell + 3rd paint unit | 832 ± 5 | +€227k ± 38k | Bottleneck moves to wiring harness |

## Recommendations
1. **Now, no investment:** plan the week with the rework loop (each SUV needs 1.06 off-road tests). The plan becomes honest and earns about €20k a week more. Use overtime at the two bottlenecks: on paper an extra paint hour is worth €15.3k a week (for 7.4 h) against €900 of overtime, an extra off-road hour €4.4k (for 8 h) against €200. The overtime effect is not simulated yet.
2. **Next quarter:** a second off-road calibration cell adds €81k ± 28k a week. A cell costing €1 M would pay back in about 3 months (€1 M / €81k ≈ 12 weeks; illustrative, the real cost is not in the model).
3. **Do not double the buffers.** They add €73k a week but hide the problem: 22 more cars in process and every car 2 hours longer in the plant. Buffers are worth testing only in front of the bottleneck.
4. **Then paint:** once the test cell is fixed, paint limits output. A third paint unit together with the second cell gives €227k ± 38k a week; only worth a business case after step 2 is done.
5. **Planning rule:** do not plan any station at 100%. Every station planned at full load loses output to normal variation and breakdowns. A load cap of about 90% on the bottlenecks is the next scenario to test.

## Limits
Station times come from invented time studies; investment costs, changeovers and the overtime effect are not modelled. Margins are contribution margins (price minus variable cost).

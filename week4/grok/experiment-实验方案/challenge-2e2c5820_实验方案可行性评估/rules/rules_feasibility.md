# Domain rules — feasibility (实验方案可行性评估)

Goal: an executable, item-by-item feasibility conclusion for a concrete protocol
against the ACTUAL inventory/contracts — not a generic "looks feasible".

1. **Extract requirements, don't invent them.** One item per concrete requirement the
   protocol states (equipment, reagent quantity, time, budget, safety, ethics,
   personnel). Quote the protocol paragraph (evidence). Seven review classes:
   hypothesis & variables, controls, equipment & materials, time & cost, parameter
   ranges, risks & anomalies, ethics & safety.
2. **Absence ≠ satisfaction.** If the protocol omits information, or no inventory
   evidence exists for a requirement, the verdict is not_reported + human_confirm —
   never feasible. This is the most common scoring trap.
3. **Link to real inventory.** Register inventory entries with availability, quantity/
   capacity, cost, lead time and approval, each with an evidence locator. Link items
   via inventory_id (preferred) or exact normalized name.
4. **Arithmetic the engine recomputes.**
   - reagent/equipment: needed_qty vs available_qty/capacity → need>available = blocker
     (shortfall = need−available); utilization>90% = risk.
   - time: needed_hours vs window_hours (same rules).
   - budget: needed_cost vs budget_cap (same rules).
   - explicitly unavailable (available=false) = blocker.
   - spec_gap (model/spec mismatch) = risk.
   - safety/ethics: approved=true → feasible; otherwise risk + human_confirm.
   Units must match; convert explicitly and record the conversion in the item.
5. **Verdict authority.** The engine recomputes the verdict from arithmetic. An agent
   verdict that differs is kept as agent_verdict with a warning — explain, don't hide.
6. **Score & labels.** score=(n_feasible+0.5*n_risk)/n_items (not_reported counts 0).
   overall: any blocker → blocked; all not_reported → insufficient_evidence;
   score≥0.8 feasible; ≥0.5 conditional; else high_risk. Report blockers, risks and
   not_reported lists separately so a reviewer can act.
7. **Confirmations.** Safety/ethics approval, equipment booking and expert judgement
   are human_confirm items. Prospective contracts are not actual approvals.
8. **Versioned plans.** If 3 versioned candidate plans are provided, review the
   specified version; record protocol_id + version and cite the actual plan text.
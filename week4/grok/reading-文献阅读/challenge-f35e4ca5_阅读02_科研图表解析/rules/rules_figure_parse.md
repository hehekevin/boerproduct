# DOMAIN RULES — 科研图表解析 (kind=figure_parse)

## Focus
- 读得准: axis type (linear/log/dual), scale start/interval, unit magnitude correct (mV≠V, log≠linear).
- 提得全: curves/points/error bars/peaks/significance/scale bar/subplot ids fully restored; non-data not treated as data.
- 讲得清: trend/statistical conclusions backed by figure evidence; distinguish directly-readable vs inferred.

## Rules
1. Read axis type/scale/units first; record them; never assume linear.
2. Extract data points/curves to CSV with coordinates+units; list error bars/peaks/significance/scale bar/subplots.
3. Tag interpretation reported (directly readable) vs inferred; attach figure/panel locator; flag uncertainty.
4. Output structured figure record + data CSV + evidence; honest status if image unreadable.

## Self-check
- [ ] axis/unit/scale correct
- [ ] elements & data complete (CSV)
- [ ] interpretation evidence-backed; reported vs inferred
- [ ] traceable + honest status
- [ ] can't-judge not written as fact; gaps flagged; result.json honest

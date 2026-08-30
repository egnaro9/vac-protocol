# Latest standings — suite `toy-suite-v1`

_Auto-generated after each scheduled probe. Live chart: [egnaro9.github.io/model-drift](https://egnaro9.github.io/model-drift/)._

**Min detectable** is the smallest movement a run could show: `100 / graded calls`. Accuracy is scored over graded calls only — a truncated call leaves the denominator rather than counting as wrong — so the floor is not a constant, and a delta beneath it is the denominator moving, not the model.

**Reliability floor** is 0.5: accuracy from runs below it is not scored, because a rate limit or outage makes a call absent rather than wrong. The disqualified run stays visible as a reliability event.

| Model | Accuracy | Δ vs previous | Min detectable | Status |
| --- | --- | --- | --- | --- |
| Mock (toy) | 100.0% | +0.0 pts | — | ⚪ unchanged |
| Alpha One | 50.0% | -25.0 pts | ±25.0 | 🔴 regressed |
| Beta One | 90.0% | +24.0 pts | ±33.3 ⚠ below floor | 🟢 improved |
| Gamma One | 25.0% | — | — | 🔵 baseline |
| Delta One | — | — | — | ⚫ no runs yet |

# Roast Solver task-tool trials

Six independently generated implementations of the same Roast Solver M1–M6 task, preserved as branches from one common seed.

The experiment compared three Pi conditions with two runs each:

1. **Baseline** — no task extension.
2. **Shadow** — task tools and workflow guidance, with context projection disabled.
3. **Full projection** — normal `pi-task-compaction` behavior.

See [`TRIALS.md`](TRIALS.md) for branch names, exact captured commits, preview behavior, and checkout instructions. See [`EXPERIMENT_RESULTS.md`](EXPERIMENT_RESULTS.md) for the three-arm analysis.

The generated trial branches are intentionally unmodified. Each branch's tip tree exactly matches the corresponding experiment capture.

## Branches

| Condition | Round 1 | Round 2 |
|---|---|---|
| Baseline | `baseline/round-1` | `baseline/round-2` |
| Shadow | `shadow/round-1` | `shadow/round-2` |
| Full projection | `full-projection/round-1` | `full-projection/round-2` |

`main` contains only the shared plan and experiment documentation; implementation code lives on the six trial branches.

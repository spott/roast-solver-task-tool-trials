# Projection-disabled task-tool ablation

> A later single todo-only run is documented separately in [`TODO_ONLY_RESULTS.md`](TODO_ONLY_RESULTS.md); it is not included in these three-arm means.

This report adds a projection-disabled shadow arm to the four-run roast-solver experiment. There are now two independent invocations per arm:

1. **baseline** — no task extension;
2. **shadow** — identical task tools and model-facing workflow guidance, but no provider-context projection and no task-aware global-compaction hook; and
3. **full projection** — the normal task-compaction extension.

Every run started from seed `9c0173ee9b98ec5fe970f6228fc971cc8b04e29c`, used the exact same prompt, `openai-codex/gpt-5.6-sol` at `high`, raw Pi 0.84.1, host auth, fast isolation, and a 7,200-second cap. Runs were sequential. There were no harness-owned evaluators. Two observations per arm are descriptive, not a significance test or general causal estimate.

The immutable shadow package was `/nix/store/pja402avhrj6kkawr892w8s5w2r6lpla-pi-task-compaction-0.1.0`, content hash `sha256:53abd9de2431d41cb1708c76d845d8a87268eb79e04ba894689161178b4d5f0a`, built from shadow implementation commit `a1bd75d96842ab1a9b2ebb5d43913e5dbfce41af`.

## Primary behavioral check

The model did **not** stop using task tools when projection was disabled.

| Shadow run | Closed task pairs | New regions after first close | Open/abandoned/unmatched | Final context |
|---|---:|---:|---:|---:|
| 1 | 5 | 4 | 0 | 110,461 (40.61%) |
| 2 | 5 | 4 | 0 | 136,652 (50.24%) |

Both runs independently followed five sequential phases: planning, Python M1–M4, Rust/WASM M5, UI/worker M6, and Nix/docs/final integration. The model was not reminded to use tasks and was not told projection was disabled. Neither shadow run invoked `preserve_output`, preserved-output listing/reading, or `expand_task`. Neither triggered global compaction.

## Per-run observations

| Arm | Run | Wall s | Cost | Input | Output | Final context | Tools | Added lines | Regions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 1 | 1,043.03 | $3.809 | 128,750 | 36,748 | 66,909 | 108 | 2,247 | 0 |
| Baseline | 2 | 977.88 | $3.187 | 151,652 | 40,893 | 58,212 | 77 | 1,632 | 0 |
| Shadow | 1 | 1,672.52 | $5.862 | 253,696 | 66,677 | 110,461 | 106 | 2,372 | 5 |
| Shadow | 2 | 1,709.12 | $8.392 | 248,479 | 64,870 | 136,652 | 145 | 4,506 | 5 |
| Full | 1 | 1,761.15 | $4.955 | 260,877 | 72,377 | 11,644 | 170 | 3,120 | 6 |
| Full | 2 | 1,669.41 | $5.117 | 299,171 | 69,092 | 10,941 | 181 | 4,306 | 6 |

## Two-run arm means

| Metric | Baseline | Shadow | Full projection |
|---|---:|---:|---:|
| Wall seconds | 1,010.46 | 1,690.82 | 1,715.28 |
| Reported cost | $3.498 | $7.127 | $5.036 |
| Input tokens | 140,201 | 251,087.5 | 280,024 |
| Output tokens | 38,820.5 | 65,773.5 | 70,734.5 |
| Cache-read tokens | 3,265,280 | 7,796,992 | 3,027,200 |
| Final context tokens | 62,560.5 | 123,556.5 | 11,292.5 |
| Tool calls | 92.5 | 125.5 | 175.5 |
| Changed files | 33.0 | 38.0 | 33.5 |
| Added lines | 1,939.5 | 3,439.0 | 3,713.0 |
| Patch bytes | 100,525 | 207,199 | 158,165.5 |
| Closed regions | 0 | 5 | 6 |
| Boundary-model seconds | 0 | 228.75 | 176.66 |
| Ordinary-model seconds | 871.12 | 1,221.45 | 1,306.74 |
| Ordinary-tool seconds | 129.48 | 229.96 | 219.99 |
| Unchanged cross-region direct rereads | 0 | 0 | 19.0 |

## What the ablation says

### Why task-tool runs were longer

Shadow and full projection had almost the same mean runtime: full was only 1.4% longer than shadow. Both were about 1.7× baseline and produced roughly 1.8–1.9× as many added lines. Since shadow retained the full transcript, projection is not required to produce the longer, broader work pattern.

The stronger explanation is the task protocol's workflow guidance: both task arms decomposed the work into implementation phases, carried open threads forward, and reserved explicit packaging/final-integration work. Projection affected context and cost, but the structured workflow existed without it.

Boundary turns were themselves substantial. Shadow spent a mean 228.75 seconds producing begin/end turns, versus 176.66 seconds under full projection. With full history still present, later shadow summaries were generated against a much larger context.

### Did projection prevent repeated exploration?

For these runs, projection caused more measurable reacquisition rather than less. The full arm averaged 19 unchanged cross-region direct rereads; shadow had zero. The full runs reread plan/repository files that had disappeared behind prior task summaries. Shadow could still see the originals.

That does not make all full-arm rereads waste: many were integration or final-audit reads. It does show that projection can trade prompt size for some file reacquisition.

### Did projection create the observed quality/scope difference?

The shadow outputs resemble the full-arm outputs more than the controls in implementation depth:

- both shadow Rust cores cover progressive full simulations rather than only a narrow numerical kernel;
- both include practical Python↔Rust trajectory/property/geometry parity checks;
- both expose broad M6 UI controls and produce complete static builds;
- both integrate Python, Rust/WASM, frontend, and Nix validation.

This recurring breadth while projection was disabled weakens the hypothesis that short context was the main cause. It supports workflow guidance/decomposition as the larger contributor. Projection may still reduce context dilution, but this experiment does not show a clear additional quality gain from it.

### What projection did clearly improve

Compared with shadow, full projection:

- reduced final context by 90.9%;
- reduced reported mean cost by 29.3%;
- reduced cache-read tokens by 61.2%; and
- reduced boundary-model time by 22.8%.

It did **not** reduce wall time in this sample. It also coincided with 39.8% more tool calls and observable cross-region rereading. Reported token/cache accounting depends on provider caching and should be interpreted as measured billing telemetry, not a universal pricing result.

## Materialized shadow outputs

| Run | Repository | Branch | Commit | Captured tree |
|---:|---|---|---|---|
| 1 | `/home/spott/code/roast-solver-task-tool-shadow-round-1` | `task-tool-shadow-round-1` | `7b1e5d0` | `5699f258f17b7a3967dd539694a5c16411b8ace3` |
| 2 | `/home/spott/code/roast-solver-task-tool-shadow-round-2` | `task-tool-shadow-round-2` | `54952da` | `88d09a1b2f63735be513e61606a6f7572154e6f8` |

Each pre-commit Git tree exactly matched the corresponding harness capture. No generated source was edited after capture.

## Independent verification

### Shadow run 1

- 16 Python tests passed.
- 3 Rust tests and doc tests passed.
- 3 Node UI tests passed.
- Production SIMD WASM/static build passed.
- Direct generated-WASM execution completed a cook/rest simulation.
- All 3 local Nix flake checks and the default package build passed.
- HTTP preview served the app and WASM with `application/wasm`.

Preview:

```sh
cd /home/spott/code/roast-solver-task-tool-shadow-round-1
nix develop
npm run build
PORT=4185 npm run preview
```

### Shadow run 2

- 12 Python tests passed.
- 3 Rust integration tests and doc tests passed.
- Clippy with warnings denied passed.
- WASM runtime smoke, strict TypeScript, and Vite production build passed.
- All 5 local Nix flake checks and the default package build passed.
- `npm ci` reported zero vulnerabilities.
- HTTP preview served the app and WASM with `application/wasm`.

Preview:

```sh
cd /home/spott/code/roast-solver-task-tool-shadow-round-2
nix develop
cd web && npm ci && npm run build
npm run preview -- --host 127.0.0.1 --port 4186
```

## Limits

- Two runs per arm are enough to check recurrence, not statistical significance.
- There is still no common hidden numerical or UX evaluator; implementation breadth and passing self-authored tests are quality evidence, not a scalar quality score.
- Sequential order, provider behavior, and package/cache state remain confounders.
- The shadow removes direct context projection and task-aware compaction together. No run reached global compaction, so only direct projection differed behaviorally here.
- Exact provider request payloads were not captured; final context telemetry and the entrypoint wiring establish the intended arm behavior.

## Reproduction artifacts

- Per-run raw metrics: each result bundle's `metrics.json`
- Six-run mechanical aggregation: `results/roast-solver-task-tool-shadow-7116ef61c6/three-arm-ablation.json`
- Six-run duplication analysis: `results/roast-solver-task-tool-shadow-7116ef61c6/six-run-duplication-analysis.json`
- Aggregator: `analysis/three_arm_ablation.py`
- Duplication analyzer: `analysis/task_duplication.py`

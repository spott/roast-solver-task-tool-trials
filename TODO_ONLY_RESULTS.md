# Todo-only supplemental trial

This is one additional Roast Solver M1–M6 run using the installed `@juicesharp/rpiv-todo` extension without task compaction. It supplements—but is not part of—the two-repetition three-arm ablation in [`EXPERIMENT_RESULTS.md`](EXPERIMENT_RESULTS.md).

## Experimental boundary

The run used the same seed, scenario, prompt, `openai-codex/gpt-5.6-sol` model, `high` thinking level, raw Pi 0.84.1 executable, host authentication, fast isolation, and 7,200-second cap as the prior trials. The only explicit extension was todo; task compaction, skills, prompt templates, and context files were disabled.

Installed extension provenance:

- package: `@juicesharp/rpiv-todo` 2.4.0
- immutable standalone path: `/nix/store/aa1ayh22pwsfcjrw9lsyjd8im1h2njd1-rpiv-todo-standalone.gss6oN`
- resource hash: `sha256:f25ed959e820a27146acd58a5507c3cb549e52be4e48fd89ebf19edb6d99bf76`
- resource size: 1,599,270 bytes, including exact runtime dependencies

There was one invocation. It is descriptive evidence, not a repeatable condition estimate.

## Result

| Metric | Todo only | Baseline mean | Shadow mean | Full-projection mean |
|---|---:|---:|---:|---:|
| Wall seconds | 2,776.76 | 1,010.46 | 1,690.82 | 1,715.28 |
| Reported cost | $5.970 | $3.498 | $7.127 | $5.036 |
| Input tokens | 217,581 | 140,201 | 251,087.5 | 280,024 |
| Output tokens | 64,126 | 38,820.5 | 65,773.5 | 70,734.5 |
| Cache-read tokens | 5,917,184 | 3,265,280 | 7,796,992 | 3,027,200 |
| Final context tokens | 100,988 | 62,560.5 | 123,556.5 | 11,292.5 |
| Tool calls | 121 | 92.5 | 125.5 | 175.5 |
| Changed files | 38 | 33.0 | 38.0 | 33.5 |
| Added lines | 2,823 | 1,939.5 | 3,439.0 | 3,713.0 |
| Task regions | 0 | 0 | 5 | 6 |
| Todo calls | 3 | 0 | 0 | 0 |

The todo-only run took longer than every prior individual run. It used fewer ordinary tools and generated less source than the task-protocol means, so the added wall time cannot be explained simply by a larger patch. One sample is insufficient to attribute this to todo, model variance, provider latency, or another transient factor.

## Todo behavior

The model used the extension, but not as a milestone decomposition mechanism:

1. Created one broad item: `Implement Roast Solver M1–M6`.
2. Corrected that item's initial pending state to `in_progress`.
3. Marked the same item completed at the final session line.

It created no milestone subtasks or dependencies. In this sample, todo supplied a persistent project status marker while the task-compaction guidance induced five or six explicit implementation phases in each task arm.

## Exact output

- branch: `todo-only/round-1`
- materialized commit: `2333967`
- captured tree: `c41d52f05157f0bef925e216cbd2e7345a6c2f23`
- run ID: `gpt-5-6-sol--todo-only-46cc9d1f-r001-22bbf46d23`
- experiment ID: `roast-solver-todo-only-e54d81977e`

The branch is a direct child of the common seed. Its Git tree exactly matches the harness capture; no generated source was repaired after capture.

## Independent verification

All authored checks passed after exact materialization:

- 13 Python tests
- 3 Rust tests plus documentation tests
- 2 Node UI/worker tests
- release SIMD WASM production build
- direct generated-WASM simulation and field-shape smoke
- all 3 local Nix flake checks
- default Nix package build
- HTTP production preview and `application/wasm` MIME check

The generated app is a coherent M1–M6 vertical slice with NumPy reference physics, SDF presets, embedded Robin/radiation/evaporation/rest behavior, synthetic calibration, Python↔Rust scenario parity, progressive WASM worker execution, a static UI, and Nix packaging.

## Preview interface

The exact root command used for the earlier comparison does not work from a clean checkout because this output's `package.json` is under `web/`:

```sh
nix develop
npm run preview -- --host 0.0.0.0 --port 4322
```

The authored workflow is:

```sh
nix develop
npm --prefix web run build
npm --prefix web run preview
```

Its custom preview script listens on fixed `127.0.0.1:4173` and does not implement host/port CLI arguments. Independent HTTP and WASM MIME checks passed using that interface.

## Limits

- There is only one todo-only run.
- No common hidden evaluator was used.
- Test breadth and implementation size are not scalar quality scores.
- Sequential order, provider/cache behavior, and package/network state remain possible confounders.
- Todo and task compaction inject different workflow instructions, so this is a distinct arm rather than a clean projection ablation.

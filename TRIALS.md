# Trial branch index

Every trial branch is a single generated commit on top of the common seed commit `9c0173ee9b98ec5fe970f6228fc971cc8b04e29c`. No source fixes were applied after capture.

## Exact branches

| Arm | Round | Branch | Captured commit | Captured tree |
|---|---:|---|---|---|
| Baseline | 1 | `baseline/round-1` | `7c663836374dcd3abf10194f351714e67dfbf2f2` | `b85bc25d03b37776f897455c1a5a9d59bdb166b6` |
| Baseline | 2 | `baseline/round-2` | `25c6bd7f0dff381fb9b93347413856aa5b58d668` | `e9996bb67470f9c17acf5b1ccfe39d7950809e26` |
| Shadow | 1 | `shadow/round-1` | `7b1e5d0bffe42320fab41b87e2cfae5dc40da359` | `5699f258f17b7a3967dd539694a5c16411b8ace3` |
| Shadow | 2 | `shadow/round-2` | `54952dacb88281b3c6750c20d51691b9f374c6ae` | `88d09a1b2f63735be513e61606a6f7572154e6f8` |
| Full projection | 1 | `full-projection/round-1` | `f62f9eca0d39501b0c816138dd5cfdcac1a76af2` | `b984f3b04954b686b03da46b9a61f3d684ac2fa4` |
| Full projection | 2 | `full-projection/round-2` | `0fe298a59388c553886107e73ca2798c6afb9282` | `124277b14d6b4eb2ef0ff71d6600ad386d71e2b3` |

## Checkout

Branch names contain slashes, so quote them in shells when useful:

```sh
git switch baseline/round-1
# or
git switch full-projection/round-2
```

Use separate worktrees to compare applications side by side:

```sh
git worktree add ../roast-baseline-r1 baseline/round-1
git worktree add ../roast-full-r1 full-projection/round-1
```

## Clean-checkout preview behavior

The following exact command was tested in a fresh detached worktree of every branch, without generated dependencies or build output:

```sh
nix develop path:.# -c npm run preview -- --host 0.0.0.0 --port PORT
```

It did **not** work from a clean checkout on any branch:

| Branch | Clean-checkout failure |
|---|---|
| `baseline/round-1` | `vite` was unavailable because dependencies had not been installed. |
| `baseline/round-2` | Preview ignored CLI host/port arguments and listened on its fixed/default port; a clean checkout also had no built `dist/`. |
| `shadow/round-1` | Preview ignored CLI host/port arguments and listened on `127.0.0.1:4173`; a clean checkout also had no built `dist/`. |
| `shadow/round-2` | Root has no `package.json`; the frontend package lives under `web/`. |
| `full-projection/round-1` | Preview correctly reported that `dist/` did not exist and requested `npm run build` first. |
| `full-projection/round-2` | `vite` was unavailable because dependencies had not been installed. |

The two full-projection repositories worked with the short command in their previously verified local directories because independent verification had already generated ignored dependencies and production builds. Those generated artifacts are intentionally not part of the captured Git trees or these branches.

This observation is still useful: both full-projection outputs expose the expected root-level preview interface and honor the requested host/port once prerequisites exist. The other arms have additional interface inconsistencies—ignored flags or a nested frontend package. But the strict claim that only full-projection works from a **fresh clone** is not supported; fresh clones of all six need some setup.

### Branch-authored setup patterns

Follow each branch's own README. In condensed form:

```sh
# baseline/round-1
nix develop
npm ci
npm run build
npm run preview -- --host 0.0.0.0 --port 4322

# baseline/round-2
nix develop
npm run build
PORT=4322 npm run preview

# shadow/round-1
nix develop
npm run build
PORT=4322 npm run preview

# shadow/round-2
nix develop
cd web
npm ci
npm run build
npm run preview -- --host 0.0.0.0 --port 4322

# full-projection/round-1
nix develop
npm run build
npm run preview -- --host 0.0.0.0 --port 4322

# full-projection/round-2
nix develop
npm ci
npm run build
npm run preview -- --host 0.0.0.0 --port 4322
```

All six projects passed their independently rerun project-specific build, test, WASM, Nix, and HTTP checks. The command-interface difference is meaningful usability evidence, but it is separate from deeper physics and implementation quality.

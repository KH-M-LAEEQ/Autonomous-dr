# Contributing

Three people, 36 weeks, one `main`. These rules exist because the failure modes of
a three-person FYP are known in advance: a branch nobody merged for a month, a
design decision made in a WhatsApp message, a `main` that stopped demoing in
November and got discovered in March.

## The five ground rules

1. **The design is frozen after Week 2.** Changing a frozen interface needs an ADR
   and all three roles agreeing in writing. Adding an implementation of an existing
   interface is free and expected.
2. **`main` always demos.** If `main` cannot run fault → detect → decide →
   cost-check → vote → act → log → dashboard, fixing that is the only priority for
   everyone.
3. **Friday is integration day.** Every branch merges Friday. No branch lives
   longer than one week.
4. **The collector runs 24/7 from Week 3.** Do not stop it. Do not `make nuke`
   without telling the team.
5. **Every metric goes in `docs/results/`, including the bad ones.** A failed
   experiment is a finding. A hidden failure is how you get caught in the viva.

## Branches

```
feat/<role>/<short-description>      new capability
fix/<role>/<short-description>       bug fix
docs/<role>/<short-description>      documentation only
chore/<role>/<short-description>     tooling, deps, CI
spike/<role>/<short-description>     time-boxed experiment, deleted after
```

`<role>` is `backend`, `frontend` or `ai` — the role, not your name. Roles can swap
people; the plan does not change.

```bash
git switch main && git pull
git switch -c feat/ai/isolation-forest-detector
```

One branch, one concern, one week maximum. A branch older than a week is a merge
conflict with a schedule attached.

## Commits

```
<type>(<scope>): <what changed, imperative>

feat(detector): add IsolationForestDetector behind AnomalyDetector
fix(consensus): break the vote tie by proposal timestamp
docs(adr): accept ADR-0004, quorum before PBFT
test(harness): assert the split never shuffles
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`, `spike`.

Write the message for the person reading `git log` in March while writing Chapter 4.
That person is you.

## Pull requests

Every change reaches `main` through a PR. No exceptions, including for the repo
owner, including for one-line fixes.

**Before you open it:**

```bash
make fmt && make lint && make test
```

**In the PR:** fill in the template. It is short and every line has caught something
real. The interface checkbox matters most — if you ticked "did not change a frozen
interface" and you did, CI fails and the reviewer knows you did not read it.

**Reviewing:** one approval from another role merges it. Review within 24 hours —
a PR waiting three days is a branch getting stale, which is rule 3 violated by
inaction rather than intent. Reviews are on the code. "This will break the harness
because the split is recomputed here" is a review. "I don't like this" is not.

**Merging:** squash merge. `main` gets one commit per PR, so `git log main` reads as
a list of things that happened rather than a list of times someone saved a file.
Delete the branch after merging.

## Friday integration, two hours, all three present

1. Every open branch merges or gets explicitly parked with a reason written in the PR.
2. Run the full loop on `main` from a clean start: `make nuke && make up && make migrate`, then the demo.
3. Tick the week's **Done when** in the build plan. If it cannot be ticked, it is not done — say so out loud rather than carrying it silently into next week.
4. Log actual hours worked per person. For the first three weeks this is data you will use to re-cut Phase 6.
5. One pair-programming session gets scheduled for next week, rotating pairs, so every role has a backup. Nobody spends six weeks alone on an island.

## Definition of done

A task is done when all of these are true:

- [ ] The week's relevant "Done when" condition is observably met — demonstrated, not asserted
- [ ] Merged to `main`, CI green
- [ ] Anything measurable is measured, with the number committed to `docs/results/`
- [ ] Any decision that constrains future weeks is in an ADR
- [ ] The next person can run it from the README without asking you a question

## Secrets

- Real credentials live in `.env` only. It is gitignored, and the pre-commit hook
  blocks credential-shaped strings.
- CI reads from GitHub Secrets. Never from a file in the repo.
- If a key ever lands in a commit: **rotate it first**, then clean history. Rewriting
  history without rotating is theatre — the key is already in the push logs.
- Billing alarms before credentials. AWS at $5, from Week 7, before the first API
  call.

## Definition of "not now"

Ideas outside the current phase go on the board as issues, not into the branch you
are on. At a decision gate, cut scope in the pre-agreed order and write down what
was cut and why — a deliberate exclusion with a reason reads as judgement in the
defence, while a discovered gap reads as failure.

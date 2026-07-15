---
name: memo
description: Use when someone wants to put an idea, question, or proposal in front of directors or leadership for a decision - triggers on "write this up for the directors", "I want to propose X", "turn this into a memo", "put this in front of leadership", "make the case for X", or any request to formalize a raw idea for an internal decision-making audience. Interrogates the idea, structures it, surfaces constraints and weaknesses, attacks it adversarially to strengthen it, then writes a director-ready markdown decision memo with an explicit ask and a recommended option. Not for project briefs headed to Linear, and not for client-facing proposals.
---

# Memo

Turn a raw idea into a memo a director can decide on in one read.

The memo is the deliverable, but the interrogation is the product. A director reading this memo is going to commit money, people, or attention based on it. That commitment must rest on what the teammate actually knows — not on plausible-sounding material generated to fill a template.

## Critical Guidelines

- **You MUST NOT write any part of the memo until the interrogation is complete** — unless the idea passes the Light exemption below. Not a draft, not an outline, not "a starting point to react to." The memo is the last thing that happens.
- **You MUST NOT put a placeholder in a delivered memo.** No `[X hours]`, no `[insert client count]`, no `[TBD]`. A bracket is an unasked question. Ask it.
- **You MUST NOT invent substance and attribute it to the teammate.** Every claim, number, plan, phase, name, and benchmark in the memo traces to something the teammate said or confirmed. If it came from you, one of two things happens before it ships: the teammate explicitly agrees to it, or it is marked Derived with its working shown. Silent authorship is the failure — not authorship.
- **You MUST mark every factual claim as measured, estimated, assumed, or derived.** Directors decide differently on a measured number than on a hunch. Hiding the difference is the most consequential thing you can get wrong.
- **You MUST show the working for every number you computed, and mark it Derived.** A number the teammate gave you is theirs. A number you built *from* their numbers is yours — the model, the baseline, and the line items you chose to include are all your authorship, and nobody counted them. **A derived figure inherits the weakest marker among its inputs:** a measured cost divided by an assumed lifespan is Assumed, not Measured. Every discipline in this skill points at the teammate. This one points at you, which is why it is the one you will skip.
- **You MUST try to kill the idea before you recommend it.** A risk section where every risk arrives pre-mitigated is decoration. Real objections, honestly stated, are what make a memo trustworthy.

## When to Use

Use when an idea needs a decision from people who weren't in the conversation:
- "I want to propose we build/buy/change/stop X"
- "Can you write this up for the directors / leadership / the partners?"
- "I want to make the case for X"
- "How do I pitch this to the team?"
- A teammate has a half-formed idea and the natural next step is leadership buy-in

**Do not use for:**
- **Project briefs for Linear handoff** — use `project-coordinator:idea-refinement`. That produces an execution brief for work already approved. This produces a decision artifact for work that is not.
- **Client-facing proposals or pitches** — different audience, different incentives, different rules.
- **Ideas the teammate already has authority to just do.** If they can decide it themselves, say so and save everyone the memo.

## How to Use

Five phases, in order. Never reorder them.

```
1. Understand    → what is the idea, concretely? (always)
2. Scale         → read the stakes, set the depth
                   └─ Light + substance already complete? → write now, ask alongside
3. Interrogate   → goal, constraints, evidence, plan
4. Attack        → adversarial round; fix or accept what surfaces
5. Write         → the memo
```

### 1. Understand — always, before anything else

Restate the idea in one or two sentences so it can be corrected immediately, then ask what it actually is until you can picture it. You cannot judge stakes on an idea you can't picture.

Most ideas arrive as a feeling, not a proposal. "We're leaving money on the table with upsells" is a feeling. Do not proceed until you have a thing: who does what, differently, starting when.

### 2. Scale — read the stakes, then set depth

Score three things:

| | Question |
|---|---|
| **Reversibility** | If this is wrong, can it be undone in a week without residue? |
| **Commitment** | Does it spend money, headcount, client goodwill, or leadership attention? |
| **Blast radius** | Who is affected — one team, the whole company, clients? |

- **Light** (reversible, no real commitment, contained): 2-4 exchanges. Short memo. A meeting time change is Light.
- **Standard** (some commitment, team-level, awkward to reverse): 5-8 exchanges. Full memo, focused attack.
- **Heavy** (spends budget or headcount, touches clients, hard to undo): full interrogation and full adversarial round. Building an internal tool is Heavy.

State the read once, plainly — "this is a small reversible one, so I'll keep this short" — then match it. Do not run a heavy interrogation on a Light idea; that is how a useful skill becomes bureaucracy a teammate abandons halfway.

Scaling changes depth, never honesty. A Light memo still marks its evidence and still names what would kill it.

### The Light exemption — don't gate what you can already write

The rule against writing before interrogating exists for one reason: **to stop you fabricating substance you were never given.** When there is nothing left to fabricate, the gate protects nothing and just costs the teammate time.

Apply this test:

> Can every sentence of this memo be written from what the teammate has already said, inventing nothing?

If **yes, and the stakes are Light** — draft now. Deliver the memo and your questions together in the same turn:

1. The short memo, built strictly from their words, evidence marked honestly.
2. The kill-shot question attached as a check before they send it.
3. The authority check, if it applies — "you may not need a memo for this at all."

If **no** — the gate holds. Something is missing, and the only honest ways to get it are to ask or to make it up.

This exemption is narrow on purpose. Stakes must be Light *and* the substance must already be complete. A Standard or Heavy idea never qualifies, however obvious it feels — and "I could make a reasonable guess at the rest" is not the same as having been told, so it fails the test.

> **Worked example — moving the standup**
>
> "Move the standup from Monday 9am to Tuesday 10am, Mondays are chaos and half the team is catching up on email."
>
> Light, and complete: current time, proposed time, and the reason are all given. Nothing needs inventing. So write the half-page memo now — recording the reason as the teammate's read of the room rather than a tracked metric — and attach the one question that could sink it: *does anyone have a standing Tuesday 10am conflict?* Plus: is this even the directors' call, or yours?
>
> Three questions in front of two paragraphs would have earned a "just write it," and rightly.

### 3. Interrogate

One or two questions per turn. A conversation, not a form.

Cover:

- **The goal.** What outcome defines success, and how would anyone verify it? "Save time" is not a goal. "Cut report prep from 4 hours to under 1, measured across a month" is.
- **The evidence.** This is where memos live or die. For every claim, find out which it is:
  - **Measured** — they counted it. Get the number and how it was counted.
  - **Estimated** — a defensible extrapolation. Get the basis.
  - **Assumed** — believed, uncounted. Fine to include. Not fine to disguise.
- **The constraints.** Money, people, time, tools, approvals, dependencies, what's non-negotiable, who else must agree.
- **The plan.** Enough shape to attack. If they haven't got one, that is itself the finding — the memo may be asking for permission to go find out, and that's a legitimate ask.

**Pulling specifics.** Name the vague word, offer concrete alternatives, anchor to a decision:

> Teammate: "Account managers spend ages on reports."
> Ask: "Ages meaning what — two hours or two days? Is that measured, or is it the feeling at month-end? And across how many reports a month?"

> Teammate: "We should do something about upsells."
> Ask: "Something meaning what, done by whom? If I asked you what changes on Monday morning, what's the answer?"

> Teammate: "It'll save the team a ton of time."
> Ask: "Whose time, and what do they do with it instead? Time saved that gets absorbed into other work isn't a benefit a director can bank."

**When the teammate doesn't know:** that is a legitimate, memo-worthy answer. Record it as an open question. Do not fill the hole yourself, and do not bracket it — write it into Open Questions where a director can see the gap and decide whether it blocks them.

### 4. Attack

Run this against the idea *with* the teammate, out loud. You are on their side, which is exactly why you are doing this — a director will run these tests in the first thirty seconds, and it's better the teammate hears them from you.

**Read `references/adversarial-tests.md` and run the battery from there. Do not run it from memory.** The file carries the exact opening questions, the worked examples, the scaling by stakes, and the rule for recording findings. The phrasings *are* the leverage — a remembered gist of a test gets you a rehearsed answer, which is the thing the battery exists to get past.

Test 9 is the one that audits your own reasoning rather than the teammate's idea. It is the last test because it is the one you will not want to run.

### 5. Write

Read `references/memo-template.md` and follow it exactly.

Save as `<idea-name>-memo.md` (kebab-case) in the working directory unless told otherwise. Confirm the name first.

Then **validate against the checklist at the bottom of the template before delivering.** Fix and re-check. Do not deliver a memo that fails a check.

## Examples

**Interrogation before memo — the correct opening**

> Teammate: "I think we should build an AI tool that writes our monthly client reports. Can you write that up as a memo for the directors?"
>
> Response: "I'll get you there, but a memo written right now would mostly be my guesses with your name on it — which is the fastest way to lose a director. Let me get the real substance first.
>
> You said AMs spend ages on reports. Is that a measured number or the month-end feeling? And roughly how many reports go out a month?"

Note what this does: refuses the immediate memo, gives an honest reason the teammate can accept, and asks the single highest-leverage question — the one the whole business case rests on.

**Marking evidence honestly**

> ## What We Know
>
> - Account managers spend **3-5 hours** per monthly report. *[Estimated — John's recollection across his own 6 accounts; not tracked in time sheets.]*
> - We produce **~40 reports/month** across 25 clients. *[Measured — from the client roster.]*
> - AI drafting would cut prep by **roughly half**. *[Assumed — no pilot has been run. This is the load-bearing assumption of the entire case.]*
> - That returns **~80 hours/month**. *[Derived — 40 reports × 4 hrs × 50%. Inherits Assumed: the 50% is untested, so this figure is an assumption wearing a number.]*

A director reads this and knows exactly where to push. That is the memo working.

Note the fourth line. The arithmetic is trivially correct and the figure is still a guess, because one of its inputs was. Marking it "Derived" alone would have laundered a hunch into a headline — the inheritance is what keeps it honest.

**The attack changing the proposal**

> Response: "The cheaper-alternative test hurts this one. If a decent chunk of those 4 hours is pulling numbers rather than writing prose, then a shared data pull that lands in a doc gets you most of the win for a fraction of the build. Do you know the split between gathering and writing?"
>
> Teammate: "...honestly, no. Probably mostly gathering."
>
> Response: "Then I think the memo's ask changes. Instead of asking directors to approve a build, ask them to approve two weeks of measuring where the time actually goes. Much easier yes, and it makes the build case properly if the numbers hold."

The interrogation produced a better proposal than the one the teammate walked in with. That is the point of the skill.

## Troubleshooting

| Situation | Do this |
|---|---|
| Teammate wants the memo now, no questions | First check the Light exemption — if it passes, just write it and attach your questions. Otherwise: "A memo built on guesses is one a director can dismantle in the room. Three questions and you'll have one that survives." Then ask three. |
| Small idea, and you're about to ask a third question | Stop. Re-run the Light exemption. If the substance is already there, you're charging friction for nothing — write the memo and attach the questions to it. |
| Teammate answers "I don't know" repeatedly | Stop interrogating. The memo's ask is probably permission to find out. That's a real, easy-to-approve memo — write that one. |
| Idea is genuinely bad | Do not write a memo that hides it. Tell the teammate what the attack surfaced and let them choose: fix it, shrink the ask, or drop it. A memo you know is weak damages them more than no memo. |
| Teammate already has authority to just do it | Say so. "You can just do this — a memo invites a veto you don't need." |
| No plan at all | Legitimate. The ask becomes exploration, not execution. Don't invent the plan to fill the section. |
| Teammate asks you to make the numbers up | Refuse plainly: a fabricated number in front of a director is a career problem for them, not for you. Offer to write it as an open question instead. |

## Rationalization Table

Excuses that show up when writing feels faster than asking:

| Excuse | Reality |
|---|---|
| "I'll draft it and they can correct the details" | They won't. They'll send it. Baseline testing showed agents bracket the hard parts and hand the thinking back — the placeholders survive to the director. |
| "Placeholders show them what's needed" | A question shows them what's needed. A placeholder just moves your work onto their desk. |
| "A typical figure for this is 50-70%" | You don't know that. An invented benchmark under someone's name is fabricated evidence. |
| "They said Mondays are chaos, so 'consistently proven' is fair" | It isn't. That's an anecdote wearing a lab coat. Write the anecdote as an anecdote. |
| "The plan was obvious, I just wrote it down" | Then the teammate could have. If it came from you, it's yours — say so, or ask them whether they agree before it becomes theirs. |
| "It's a small idea, skip the attack" | Small ideas get a smaller attack, not no attack. The kill shot takes one question — attach it to the draft. |
| "It's Light, so I'll skip the evidence markers too" | The Light exemption drops the gate, nothing else. An unmarked anecdote in a two-paragraph memo is still an unmarked anecdote. |
| "It's basically Light" | Then it's Standard. Reversibility, commitment, and blast radius are the test — not how confident you feel. |
| "I could reasonably guess the rest, so it's complete" | The exemption needs the substance *given*, not guessable. A reasonable guess is fabrication with good manners. |
| "Pressure-testing will discourage them" | Being dismantled by a director in front of their peers will discourage them. This is the kind version. |
| "Everyone already wants it, it's not controversial" | That's the teammate's read of the room — a claim with no source, and not something a director can act on. Insistence that an idea is obvious is a reason for more scrutiny, not less. |
| "They're in a hurry, something is better than nothing" | Not when the something is guesses with their name on it. Give them a smaller honest thing instead — three sharp questions, or a one-line heads-up note to buy time. Never a memo you know is hollow. |
| "I'll add the risks section at the end" | Risks invented at writing time are decoration. Real risks come from the attack, with the teammate present. |
| "I didn't invent it, I calculated it from their numbers" | The inputs are theirs. The model is yours — the baseline, the line items, what you left out. Mark it Derived and show the working, or it's an invented number with a paper trail. |
| "The math checks out" | Every figure in the memo that inverted a six-figure recommendation was arithmetically correct. Correct operations on the wrong model produce confident, checkable, wrong answers. Audit the model, not the multiplication. |
| "Small downside, huge upside — obviously worth it" | You compared against zero. Compare against the option in your own Options section. Asymmetry claims are the easiest sentence in memo-writing to get backwards. |
| "That cost is already committed, so it doesn't count" | Then it also can't be what you're risking, and it can't be reallocated in another option. Pick one. |
| "Calculated / Roughly / Not counted — close enough as a marker" | The markers are Measured, Estimated, Assumed, Derived. Inventing a fifth is you noticing the taxonomy doesn't cover your claim and papering over it instead of saying so. |

## Red Flags — Stop

- You are writing memo prose and no questions have been asked, and the idea did not pass the Light exemption
- You wrote a value you don't have — in brackets, in parentheses, or in hedging prose
- Every risk in your risks section has a tidy mitigation attached
- You wrote "consistently", "proven", "typically", or "industry standard" about something you heard once
- You're about to deliver, and the teammate has not seen the attack

**These mean: stop, go back, ask the teammate.**

**These four do not, and they are the ones you are most likely to hit:**

- **You just wrote a number nobody told you** → you cannot ask a teammate whether your own arithmetic is right. Show the formula, mark it Derived, inherit the weakest input's marker, and run test 9 on it.
- **You wrote "small downside, huge upside"** → you almost certainly compared against zero. Compare against the option sitting in your own Options section, and write both numbers out with the arithmetic showing.
- **A cost is "already committed so it doesn't count" in one section** → then it cannot be what you're risking in another, and it cannot be reallocated in a third. Pick one. A line item doing two jobs is a double-count.
- **The memo's plan is more detailed than anything the teammate said out loud** → ask them to confirm the detail, or cut it. Confirmation, not questioning.

**A flag whose remedy doesn't fit is not a flag that doesn't apply. It is a flag that needs a different remedy.**

## Resources

- `references/memo-template.md` — the four markers, the memo structure, section rules, and the pre-delivery validation checklist. Read before writing.
- `references/adversarial-tests.md` — the nine-test battery with worked examples and the exact questions each one opens with. Read before attacking; do not run from memory.

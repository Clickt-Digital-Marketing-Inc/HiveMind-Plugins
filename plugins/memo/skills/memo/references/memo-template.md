# Memo Template

The reader is a director with ten minutes and four other memos. They are not reading to admire the idea. They are reading to find out what they're being asked, what it costs, and what could go wrong.

Optimize for one read and a decision.

## Length

- **Light idea:** half a page. The Ask, a short Why, the bar, the Options if there's a genuine choice, one honest risk.
- **Standard:** one page (~600 words).
- **Heavy:** two pages maximum. If it needs more, the extra goes in an appendix below the decision — never above it.

A memo that needs three pages to ask for a yes is usually hiding that the ask isn't clear yet.

## The four markers

Every factual claim in the memo carries one:

| Marker | Means |
|---|---|
| `[Measured — how it was counted]` | Someone counted it. Say who and how. |
| `[Estimated — the basis]` | A defensible extrapolation. Say from what. |
| `[Assumed — believed, not counted]` | Say so, and say if it's load-bearing. |
| `[Derived — formula, from which inputs]` | **You** computed it. Show the working. |

**Derived is the marker for your own authorship.** A number the teammate gave you is theirs. A number you built from their numbers is yours — the model, the baseline, and the line items you chose to include. Nobody counted it, so the other three don't reach it.

**A derived figure inherits the weakest marker among its inputs.** A measured cost divided by an assumed lifespan is Assumed, not Measured. Marking the output "Derived" describes the *operation*; the inheritance rule preserves the *confidence*. Lose that and the memo launders a guess into a fact at the first arithmetic step.

Do not invent a fifth marker. If a claim doesn't fit these four, that's a finding — say so in the memo rather than papering over it.

## Structure

```markdown
# [Idea Name] — Decision Memo

**To:** [directors / leadership team]
**From:** [teammate]
**Date:** [date]
**Decision needed by:** [date, or "no deadline — see Why Now"]

## The Ask

[One short paragraph. The specific decision requested, what a yes authorizes,
and what it costs in money, people, and time. A director who reads only this
paragraph should know what they're being asked to approve.]

## Why Now

[Why this is on the table today rather than next quarter. If there is no real
urgency, say so plainly — a manufactured deadline is the fastest way to lose
trust. "No deadline; raising it now because X" is a perfectly good answer.]

## What Success Looks Like

[The verifiable outcome, and the bar. What result would make this a win, what
result would make it a failure, who checks, and when. "Launch it" is not a bar;
"1.4 enrollments per fair, measured across all four, reviewed at year end" is.

If the ask is exploratory, the bar is what you will know by when — that is a
legitimate and easily-approved memo.]

## What We Know

[The factual basis. Every claim carries one of the four markers.

- Fact. *[Measured — how it was counted.]*
- Fact. *[Estimated — the basis.]*
- Fact. *[Assumed — believed, not counted. Say if load-bearing.]*
- Fact. *[Derived — formula, from which inputs. Inherits the weakest.]*

**Constraints belong here**, explicitly: money, people, time, approvals,
dependencies, non-negotiables — what can't change and who else must agree.

If the case rests on an assumption, say which one, right here. The director
will find it anyway; finding it themselves costs you the memo.]

## Options

[2-4 real options. Include doing nothing whenever it's genuinely viable.
One is marked **Recommended** with the reasoning stated.

Markers apply here too. This is the section where the decisive numbers live
and the section most often left unmarked.

Do not pad with strawmen. A fake option to make the favourite look good
is transparent and expensive.]

### Option A — [name]
- **Cost:** [figure] *[marker — basis]*
- **Upside:** [figure] *[marker — formula, and what it is measured against]*
- **Risk:** [the one that matters]

### Option B — [name] ← **Recommended**
- **Cost:** [figure] *[marker]*
- **Upside:** [figure] *[marker — and its baseline, named]*
- **Risk:**
- **Why this one:** [reasoning. Every figure carries its marker. Every
  comparison names what it is compared against — which is one of the other
  options, not zero.]

## What Would Kill This

[What survived the adversarial round. Real, specific, honestly stated —
the objections a director would raise, surfaced before they have to.

Each finding shows its status:
- **Fixed** — what changed in the plan as a result.
- **Accepted** — a real risk consciously taken, and why that's reasonable.

Do not attach a tidy mitigation to every line. Some risks are just risks.
A memo that names its own weak points is the one that gets believed.]

## Open Questions

[What's genuinely unresolved, and who could answer it. This is where
unknowns go — never into a bracket, a parenthesis, or a hedge in the body.

An honest open question is a strength. It shows the thinking has edges
and the teammate knows where they are.]

## If You Say Yes

[The first concrete step, who owns it, and when it starts.
A director approving something wants to know what happens Monday.]
```

## Section Rules

- **The Ask goes first, always.** Never make a director read to page two to find what they're being asked. If you're building to the ask, restructure.
- **State the bar.** A decision memo without a success criterion asks for money against nothing. The director cannot grade what you never defined.
- **Options must be real.** If there's genuinely only one path, say that — "Options" with one entry and a note on why alternatives failed beats an invented menu.
- **Doing nothing is an option.** Include it whenever viable. Its presence proves the alternatives were actually weighed.
- **Recommend, with reasoning.** No recommendation pushes the thinking back onto the director. A recommendation without reasoning is a preference. Give both.
- **Every comparison names its baseline.** "Upside $100k" against what? The alternative in your own Options section — never zero.
- **Markers are not optional, and apply everywhere.** Not just What We Know.
- **Attribute anything the teammate didn't originate.** See the Critical Guidelines in SKILL.md: agreed-to, or marked Derived with working shown. Never silent.
- **Write for someone who wasn't there.** No "as we discussed", no "in this draft". The memo stands alone.
- **Cut every sentence that isn't load-bearing.** Directors reward density.

## Validate Before Delivering

Any failure gets fixed and re-checked. Do not deliver a memo that fails a check.

**Mechanical — do these literally:**

1. **No placeholders, in any costume.** `[X hours]`, `[TBD]`, "(date not yet fixed)", "(to be confirmed)", "roughly TBC" are the same defect wearing different punctuation. Search for `[` — every hit is a marker or a markdown link. Then read the Ask and the header block aloud: if any field admits it doesn't know something, that field is an unasked question. It belongs in Open Questions.
2. **Every factual claim carries one of the four markers** — Measured, Estimated, Assumed, Derived. Not "marked with something." If you invented a fifth marker, you found a gap and hid it.
3. **Every derived figure shows its formula** and inherits the weakest marker among its inputs.
4. **The numbers reconcile.** Recompute every derived figure from its stated inputs. No input is counted twice — check every figure appearing in two sections is doing the same job in both. Every comparison names its baseline.
5. **The recommendation's reasoning survives recomputation.** Not "reasoning is present" — redo the arithmetic against the alternative in your own Options section. A recommendation is the one place where wrong reasoning is indistinguishable from no reasoning.

**Judgment — these need you to actually think:**

6. **Nothing is invented — inputs or models.** Every number the teammate gave traces to something they said. Every number you computed is marked Derived. Every baseline was chosen deliberately and is named.
7. **No anecdote is dressed as evidence.** The word search ("consistently", "proven", "typically", "always", "everyone", "industry standard") is the floor, not the check. The real check: find every claim carrying the memo's weight and ask what n is. n=1 stated as n=1 is honest. n=1 doing the work of n=40 is the defect, with or without the vocabulary.
8. **The Ask is specific enough to approve.** A director could say yes and everyone would know what just happened.
9. **The bar is stated and verifiable**, and constraints are in What We Know.
10. **Doing nothing appears as an option**, or the memo says why it isn't viable.
11. **The adversarial round is visible** — real findings from the attack, not risks invented at writing time. Test 9 was run.
12. **The teammate has seen the attack.** Every Fixed and Accepted finding was worked through with them. Nothing was quietly resolved on their behalf.
13. **Length matches stakes.** A Light idea did not produce two pages.

Checks 1-5 are reliable because they are mechanical. Checks 6-12 are you asking yourself whether you cheated, and you are the one who would know least. When 6-12 feel fine and 1-5 haven't been run literally, you have not validated anything.

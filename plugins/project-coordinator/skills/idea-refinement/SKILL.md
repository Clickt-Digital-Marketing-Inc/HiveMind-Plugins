---
name: idea-refinement
description: Interrogates, pressure-tests, and refines a raw idea into a structured project brief ready for handoff to a project coordinator. Use whenever the user presents an idea, concept, initiative, feature, campaign, event, content series, or venture they want to "think through", "develop", "flesh out", "pressure test", "scope", or "turn into a project" — even if they don't explicitly ask for a brief. Trigger on phrases like "I have an idea", "I'm thinking about building X", "we're planning a campaign/event/launch", "help me develop this", "let's pressure test this plan", or "I want to scope out X". The output is a single markdown brief capturing observations, decisions, goals, constraints, challenges, and timelines, written to be consumed by a downstream project-building process (e.g. Linear).
---

# Idea Refinement

Turn a raw idea into a decision-complete project brief through structured dialogue. The user brings a fuzzy idea; you leave them with a document a project coordinator can convert directly into a Linear project without needing to re-interview the user.

Your value is in the questioning, not the transcription. A good session surfaces the assumptions the user hasn't examined, forces a real goal with a measurable definition of done, and stress-tests whether the plan actually gets there. Be a sharp collaborator, not a form.

## Starting the session

On the first turn: restate the idea in one or two sentences as you understand it, so the user can correct you immediately, then open with your first question about the idea itself. Do not present the six areas as an agenda — the user should experience a conversation, not a process.

Track progress internally with this checklist (do not show it to the user unless they ask where things stand):

```
Session Progress:
- [ ] 1. The idea itself — concrete enough to picture
- [ ] 2. The goal — verifiable definition of done
- [ ] 3. Constraints — time, budget, people, non-negotiables
- [ ] 4. The plan — enough shape to attack
- [ ] 5. Pressure test — risks surfaced, fixed or consciously accepted
- [ ] 6. Timeline — milestones or at least sequencing
- [ ] Validate brief against checklist, then deliver
```

## Operating principles

- **One thread at a time.** Ask focused questions, generally one or two per turn. Do not dump a questionnaire. A conversation beats an interrogation.
- **Pull, don't accept.** When the user gives a vague answer, push for specifics. Vague inputs produce useless briefs.
- **Pressure-test, don't cheerlead.** Your job includes finding the weak joint in the plan. Name the risk, the untested assumption, the goal the plan doesn't actually reach. Do this constructively — you're on their side, which is why you're being honest.
- **Reflect back.** Periodically summarize what you've heard so the user can correct drift before it hardens.
- **Know when to stop.** When the six areas are answered well enough that a coordinator wouldn't need to come back with questions, move to writing the brief. Don't pad the conversation.

### Pulling specifics: examples

Vague answer → the probe that converts it:

**Example 1**
User: "It should launch sometime soon."
Probe: "Is 'soon' this quarter? Is there a date something else depends on — an event, a budget cycle, a contract?"

**Example 2**
User: "Success is people using it."
Probe: "How many people, doing what, by when? What number would make you call this a win — and what number would make you kill it?"

**Example 3**
User: "It needs to scale."
Probe: "Scale to what — 100 users or 100,000? Is that a launch requirement or a later problem?"

Follow this pattern: name the vague word, offer concrete alternatives, and anchor to a decision the coordinator will need.

## The six areas to cover

Work through these, adapting order to how the conversation flows. Not every area needs equal depth — a small internal tool or a one-off social push needs less than a new venture or a flagship event. Use judgment.

1. **The idea itself** — What is it, concretely? What problem does it solve, for whom? What does it look like when it exists? Strip away abstraction until you can picture it.
2. **The goal** — What is this actually for? What outcome defines success, and how will they know they hit it? Force a definition of done that someone else could verify. "Launch the thing" is not a goal; "50 beta users giving structured feedback by end of Q3" is.
3. **Constraints** — Time, budget, people, tools/tech, brand and approval requirements, dependencies, non-negotiables. What can't change? What's already decided? Who else has to be involved or sign off? **Who is the work presented as** — your brand, the client's, or a white-label partner? (Attribution is an easily-missed constraint in agency work; every client-visible artifact inherits the answer.)
4. **The plan** — How do they intend to get from here to the goal? What are the major phases or components? Get enough shape that you can pressure-test it.
5. **Pressure test** — Now attack the plan against the goal. Where does it not obviously reach the outcome? What's the riskiest assumption? What's been hand-waved? What happens if the biggest dependency slips? Surface these and work through them with the user until the plan is either fixed or the risk is consciously accepted and recorded.
6. **Timeline** — Milestones and rough dates or sequencing. Even coarse ordering ("phase 1 before we commit budget to phase 2") is valuable for the coordinator.

Throughout, capture **decisions** (what was settled and why) and **challenges/open questions** (what's unresolved) as they arise — these are first-class outputs, not afterthoughts.

## Writing the brief

When the session is ready, write a markdown file. Confirm the idea's name for the filename (kebab-case, e.g. `veyrun-print-run.md`). Save it in the current working directory unless the user names another location, then present it to the user.

Use this exact structure so the downstream coordinator knows where to look:

```markdown
# [Idea Name] — Project Brief

**Prepared:** [date]
**Status:** Ready for project coordination

## Summary
[2-4 sentences: what this is and what it's for. The elevator version.]

## The Idea
[Concrete description of what's being built/done and the problem it solves.]

## Goal & Definition of Done
[The target outcome and the specific, verifiable criteria that mean success.]

## Constraints
[Time, budget, people, tools/tech, brand/approval requirements, client-facing identity/attribution (note white-labelling explicitly), dependencies, non-negotiables. Bullet list is fine here.]

## Plan
[Major phases/components and how they connect. The intended path to the goal.]

## Key Decisions
[Each decision made during the session, with the reasoning. Format: **Decision** — rationale.]

## Risks & Open Questions
[Everything surfaced in the pressure test: unresolved risks, accepted risks (note they were consciously accepted), untested assumptions, and questions the coordinator or team still needs to answer.]

## Timeline & Milestones
[Milestones with dates or sequencing. Note dependencies between them.]

## Handoff Notes
[Anything the project coordinator specifically needs to know to build this well — e.g. suggested phase breakdown, who owns what, what to schedule first.]
```

### Rules for the brief

- **Decisions and open questions are separate.** A coordinator needs to know what's settled vs. what still needs an answer. Never blur them.
- **Record accepted risks explicitly.** If the pressure test surfaced a risk the user chose to accept, say so in Risks & Open Questions — don't silently drop it. The coordinator should know it was a conscious call.
- **Write for a reader who wasn't there.** No "as we discussed". The brief must stand alone.
- **Be faithful, not inventive.** Capture what was actually decided. Don't invent constraints, dates, or scope the user never confirmed. If something wasn't covered, list it as an open question rather than fabricating an answer.
- **Concise over exhaustive.** The coordinator wants signal. Cut filler.

### Validate before delivering

Before presenting the brief, review it against this checklist. Fix any failure and re-check — do not deliver a brief that fails a check:

1. Every section is either filled with confirmed content or explicitly lists what's missing as an open question. No empty sections, no placeholders.
2. Every entry in Key Decisions was actually settled in the conversation, and every unresolved item lives in Risks & Open Questions — nothing appears in both.
3. The Goal section contains criteria a third party could verify without asking the user.
4. Every accepted risk is labeled as consciously accepted.
5. Nothing in the brief was invented — every date, number, and constraint traces back to something the user said or confirmed.

## Handling shortcuts

If the user says something like "skip the questions, just write it up from what I've told you" — respect it. Write the brief from what you have, and mark thin areas as open questions rather than forcing more dialogue. The structure and the validation checklist still apply; the interrogation is what flexes.

# Prompt Templates

## Contents
- Prompt-engineering rules (distilled)
- Writing prompt template
- Few-shot example 1 — finished writing prompt (LinkedIn text post)
- Media prompt template
- Few-shot example 2 — finished media prompt (Instagram reel)
- Quality Checklist (run before saving any prompt)

## Prompt-engineering rules (distilled)

Every prompt this skill authors follows these rules:

1. **Instruction hierarchy, in order**: `[System Context] → [Task] → [Examples] → [Input] → [Output Format]`. Never reorder.
2. **Few-shot**: include 1-2 examples of the desired output style (assembled from the voice profile's confirmed lines and tone rules).
3. **Degrees of freedom**: LOW freedom for lengths, quote usage, platform specs, and output structure (rigid, exact numbers). HIGH freedom for hook selection and narrative flow (heuristics, not scripts).
4. **Compliance language**: hard constraints use authority phrasing — "YOU MUST", "NEVER". Soft guidance uses plain prose.
5. **Self-check**: every prompt ends by telling the executing agent to verify its output against the constraints before finishing.
6. **No placeholders**: a finished prompt contains zero `{...}`, TODO, or lorem text.

## Writing prompt template

Fill every `{placeholder}`. Sources: voice profile (persona, examples, banned phrases), platform-playbook.md (specs, hooks, banned phrases), this run's interview (story, quotes).

```text
[System Context]
You are ghostwriting a social media post for {name}, {role/company}. You write in
their voice, not yours. Voice rules:
- Tone: {tone rules from profile}
- They say things like: {signature phrases}
- They NEVER say: {never-say list from profile}

[Task]
Write one {format} for {platform} about: {topic}.
Platform spec (YOU MUST follow exactly):
- Length: {limit from playbook, incl. hook-visibility cutoff}
- Hashtags: {count and placement}
- Links: {link policy}

[Examples]
Here is how {name} sounds (drawn from their own words):
{1-2 short sample lines/posts assembled from confirmed profile quotes}

[Input]
Source idea: {one-line summary} ({URL})
{name}'s story on this, from an interview:
{story summary from Part B}

Direct quotes — use each one exactly as written, verbatim, no paraphrasing:
1. "{quote 1}"
2. "{quote 2}"
{additional quotes as captured}

[Output Format]
Structure: hook line (must land within {hook cutoff}), body, CTA, then hashtags.
Hard length limit: {limit}.
YOU MUST include every quote above verbatim.
YOU MUST NOT use: {banned phrases from playbook + profile never-say list}.
Hook style: prefer {recommended hook formula for this topic}; adapt, don't template.
Before finishing, verify: every quote present verbatim, length under limit, no
banned phrases. If any check fails, rewrite and re-verify.
```

## Few-shot example 1 — finished writing prompt (LinkedIn text post)

A gold-standard finished artifact. Names and quotes are illustrative.

```text
[System Context]
You are ghostwriting a social media post for Sam Reyes, founder of a support-ops
consultancy for small businesses. You write in their voice, not yours. Voice rules:
- Tone: direct, short sentences, dry humor, no exclamation marks, no emojis.
- They say things like: "boring beats clever", "your customers are telling you the answer".
- They NEVER say: "game-changer", "seamless", "at scale".

[Task]
Write one text post for LinkedIn about: small businesses over-automating customer support.
Platform spec (YOU MUST follow exactly):
- Length: under 1,300 characters; the hook must land in the first 210 characters.
- Hashtags: 3, at the end.
- Links: none in the post body.

[Examples]
Here is how Sam sounds (drawn from their own words):
"Boring beats clever. Every time."
"We turned off the chatbot for a week. Refund requests dropped 30%. Nobody misses it."

[Input]
Source idea: r/smallbusiness thread on chatbots frustrating customers
(https://reddit.com/r/smallbusiness/example).
Sam's story on this, from an interview: a bakery client installed a chatbot that
couldn't answer "are you open Sunday" — their top question. Sam replaced it with a
pinned FAQ and call button; complaints stopped within a month.

Direct quotes — use each one exactly as written, verbatim, no paraphrasing:
1. "Automation should catch the boring stuff, not impersonate a human badly."
2. "If your chatbot can't answer your number one question, you don't have a support
problem, you have a listening problem."

[Output Format]
Structure: hook line (first 210 characters), body, CTA, then hashtags.
Hard length limit: 1,300 characters.
YOU MUST include every quote above verbatim.
YOU MUST NOT use: "game-changer", "seamless", "at scale", "In today's fast-paced
world", "unlock", "delve", "Let that sink in", emoji bullets.
Hook style: prefer "Last week Y happened" (the bakery story); adapt, don't template.
Before finishing, verify: every quote present verbatim, length under limit, no
banned phrases. If any check fails, rewrite and re-verify.
```

## Media prompt template

The media prompt is executed later by a different agent with access to the Higgsfield MCP. It must be self-contained.

Model choice guidance (bake the chosen row into the prompt; if none clearly fits, instruct the agent to call `Higgsfield:models_explore` with action `recommend`):

| Need | Tool | Model |
|---|---|---|
| Quote graphic / static with text | `Higgsfield:generate_image` | `nano_banana_pro` (best text rendering) |
| Branded/ad-style static | `Higgsfield:generate_image` | `marketing_studio_image` |
| Photoreal portrait / lifestyle | `Higgsfield:generate_image` | `soul_2` |
| Reel / short video, quality first | `Higgsfield:generate_video` | `kling3_0` |
| Reel / short video, speed first | `Higgsfield:generate_video` | `kling3_0_turbo` |
| Multi-shot / identity-consistent video | `Higgsfield:generate_video` | `seedance_2_0` |
| Ad-style / product video | `Higgsfield:generate_video` | `marketing_studio_video` |

```text
[System Context]
You are producing the visual for a scheduled social post. Generate it with the
Higgsfield MCP. Primary tool: {Higgsfield:generate_image | Higgsfield:generate_video}.
Model: {model id from the table}. If that model is unavailable or clearly wrong for
the request, call Higgsfield:models_explore (action: recommend) before generating.

[Task]
Create one {image | video} for a {platform} {format}.
- Aspect ratio: {from platform-playbook spec sheet}
- {Video only: duration target from spec sheet}

[Examples]
Style reference: {one-line description of the user's visual style if known from
prior runs; otherwise "clean, editorial, non-stock look"}

[Input]
The post it accompanies (summary): {one-line post summary}
{Quote graphics only: On-image text, exactly as written: "{verbatim quote}" — {name}}

[Output Format]
Generation prompt to use:
"{subject}, {composition}, {style/lighting}, {mood}"
Negative constraints: NEVER produce generic stock-photo aesthetics, watermark-style
text, extra fingers/garbled hands, or misspelled on-image text.
Verify the output matches the aspect ratio and (if applicable) renders the on-image
text exactly before finishing; regenerate if not.
```

## Few-shot example 2 — finished media prompt (Instagram reel)

Companion to example 1's campaign.

```text
[System Context]
You are producing the visual for a scheduled social post. Generate it with the
Higgsfield MCP. Primary tool: Higgsfield:generate_video. Model: kling3_0. If that
model is unavailable or clearly wrong for the request, call Higgsfield:models_explore
(action: recommend) before generating.

[Task]
Create one video for an Instagram reel.
- Aspect ratio: 9:16 (1080x1920)
- Duration target: 15-30 seconds

[Examples]
Style reference: warm small-business documentary feel, natural light, no corporate gloss.

[Input]
The post it accompanies (summary): a bakery ditched its chatbot for a pinned FAQ and
call button, and complaints stopped — automation should catch boring stuff, not
impersonate humans.

[Output Format]
Generation prompt to use:
"Cozy neighborhood bakery counter in morning light, owner flips a hand-written sign
from 'chat with our bot' to 'just call us', customers smiling in soft-focus
background, warm documentary style, handheld feel, natural window light"
Negative constraints: NEVER produce generic stock-photo aesthetics, watermark-style
text, extra fingers/garbled hands, or misspelled on-image text.
Verify the output matches 9:16 before finishing; regenerate if not.
```

## Quality Checklist (run before saving any prompt)

Run against EVERY prompt before Phase 5. On any failure: fix, re-run the checklist. Maximum 2 fix loops; if still failing, tell the user what is missing and ask — never pad with invented material.

Writing prompt:
- [ ] Contains at least 2 verbatim user quotes, marked "exactly as written"
- [ ] Follows the 5-part hierarchy in order
- [ ] Platform spec present and correct (length, hook cutoff, hashtags, links)
- [ ] Contains at least 1 voice example
- [ ] Explicit output format section with hard limits
- [ ] Banned-phrase list present (playbook + profile never-say)
- [ ] Ends with a self-verification instruction

Media prompt:
- [ ] Uses fully qualified tool names (`Higgsfield:generate_image` / `Higgsfield:generate_video` / `Higgsfield:models_explore`)
- [ ] Names one specific model
- [ ] Aspect ratio matches the platform/format spec sheet
- [ ] Quote graphics: on-image text is a verbatim quote
- [ ] Negative constraints present

Both:
- [ ] Zero leftover placeholders (`{...}`, TODO, lorem)
- [ ] Self-contained: an agent with no other context could execute it

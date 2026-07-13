# Interview Guide

## Contents
- Voice profile file spec
- Part A — first-run deep interview
- Part B — per-topic interview
- Quote hygiene rules
- Profile update rules

## Voice profile file spec

Location: `~/.claude/social-media-manager/voice-profile.md` (user-level — NEVER inside the plugin directory, which is replaced on every update). Create the directory if missing.

Exact section skeleton:

```markdown
# Voice Profile — <name>

## About
<role, company, niche/topic focus, audience, platforms they use>

## Positions
1. <opinion/hot take, 1-2 sentences, in the user's own words>
2. ...

## Signature phrases
- Says: <words/phrases they actually use>
- Never says: <words/phrases that make them cringe>

## Tone rules
<sentence length, formality, humor, emoji policy, formatting habits>

## Story bank
### <story title>
- Context: ...
- What happened: ...
- The lesson: ...
- Verbatim quotes: "..."

## Quote bank
### <topic>
- "<verbatim quote>" (captured <YYYY-MM-DD>)

## Interview log
| Date | Topics covered | Posts produced |
|---|---|---|
```

## Part A — first-run deep interview

Run only when no voice profile exists. Ask conversationally, 1-2 questions at a time, in plain text — NOT AskUserQuestion option lists (multiple choice cannot capture verbatim quotes). Roughly 20-30 minutes of the user's time; say so up front and offer to shorten if they're pressed.

1. Who are you and what do you do? Who is the audience you want these posts to reach?
2. What are three strong opinions you hold in your field that most peers would push back on?
3. Tell me about a time you were wrong about something in your work. What changed your mind?
4. Tell me a recent client or work story that taught you something.
5. What phrases or expressions do you find yourself saying all the time?
6. What words or phrases in your industry make you cringe?
7. How casual are you in writing — texting-a-friend casual, or keynote-speech polished?
8. What's your stance on emojis and exclamation marks?
9. What's a hill you'll die on?
10. What does everyone in your niche get wrong?

Transcribe answers verbatim into the profile sections. Read the 3-5 strongest lines back to the user and ask "can I quote you on that?" — only confirmed lines enter the Quote bank.

Then run Part B for each chosen idea, and write the complete profile file.

## Part B — per-topic interview

Run for every chosen idea, every run. Check the Quote bank first: if existing quotes fit the topic, show them and ask whether to reuse before asking new questions.

Per idea, ask 3-5 of these (adapt to the idea; plain conversation, verbatim capture):

1. "What's your honest take on <idea>? Don't polish it."
2. "Has this come up in your own work? Tell me the story."
3. "Finish this sentence: most people think ___, but actually ___."
4. "What would you tell a client who asked you about this tomorrow?"
5. "Say the one sentence you'd want to be quoted on for this."

Capture at least 2 quotable lines per post (4+ for threads and carousels). If the user's answers are thin, say so and ask a follow-up — do not proceed to prompt authoring with insufficient material.

## Quote hygiene rules

- Verbatim only. Preserve the user's grammar, slang, and rhythm — that IS the voice.
- Mark any light edit (e.g. removing a false start) with [brackets].
- Never merge two answers into one "quote".
- Every quote entering the Quote bank gets the capture date.
- Minimum per post: 2 verbatim quotes; threads/carousels: 4+.

## Profile update rules

- Quote bank and Story bank are append-only.
- Positions may be revised only when the user explicitly says their view changed; note the old position as "(formerly: ...)".
- Always append a row to the Interview log: date, topics covered, posts produced.
- On repeat runs, read the profile and confirm it aloud in one short paragraph ("Here's the voice I have on file: ...") before interviewing, so drift gets caught.

# Extraction, de-duplication, and drafting guide

## What to extract

Read each call transcript and email thread and pull out discrete, trackable items
in three types.

**Tasks (action items)** — something that needs doing.

- Triggers: "I'll...", "can you...", "we need to...", "let's...", "by Friday...",
  "action item", assignments, commitments, deadlines.
- Capture the owner if stated, and any due date.

**Decisions** — a choice that was made and should be recorded.

- Triggers: "we decided...", "let's go with...", "final answer is...", "approved",
  "we're not doing X".
- Worth tracking when the decision affects future work or others need to know.

**Open questions** — something unresolved that needs an answer or a follow-up.

- Triggers: "we still need to figure out...", "who owns...", "waiting on...",
  "TBD", unanswered questions in an email.

## What to skip

- Small talk, scheduling chatter, and pleasantries.
- Items already completed during the call or resolved in the email thread.
- Duplicates of things already in the tracker (see below).
- Vague sentiment with no action ("this is great").

When genuinely unsure, keep the item and mark it low priority rather than
dropping it. Missing a real task is worse than one extra low-priority issue.

## Writing good issues

- **Title**: action-first and specific. "Send Q3 budget to Sarah by Fri", not
  "budget".
- **Detail**: one or two sentences of context so the issue stands alone. Include
  the decision or constraint behind the task if there is one.
- **Source line**: always include where it came from, e.g. "From: Weekly Sync
  call, 2026-07-11" or "From email: 'Re: Renewal terms' — sarah@acme.com". This
  makes every issue traceable.
- **Owner / assignee**: set when clear; otherwise leave it for the user to assign.
- **Priority**: infer from language (deadlines, "urgent", blocking others) but
  stay conservative.

## De-duplication

Before creating anything, search the tracker for similar existing issues by title
keywords and the people/topic involved. If a close match exists:

- If it is the same task, skip it and note the skip.
- If it adds new information, prefer adding a comment or updating over creating a
  second issue.

Also de-duplicate within the current run: the same action item mentioned in both
a call and a follow-up email is one issue, not two. Record both sources on it.

## Drafting emails

Only draft; never send. Save drafts in the configured email tool for the user to
review and send themselves.

**Replies owed** — a thread where someone is waiting on the user and no reply has
gone out yet. Draft a reply that:

- Answers the actual question or acknowledges the request.
- Matches the user's normal tone: direct, warm, concise. No filler, no
  over-apologizing.
- Leaves clearly-marked placeholders like `[confirm date]` where a fact is
  unknown, rather than inventing details.

**Follow-ups** — an outbound email the user needs to send because of an action
item (e.g. "send the proposal to the client"). Draft it with a clear ask, the
relevant context, and placeholders for anything not known.

Keep drafts short. It is easier for the user to add than to cut. In the summary,
tell the user which call or email each draft came from so they know why it exists.

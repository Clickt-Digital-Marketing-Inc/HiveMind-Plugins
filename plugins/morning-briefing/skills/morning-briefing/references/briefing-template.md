# Morning Briefing Template

Write the briefing file with exactly this structure. **Every section is always present** — except the "Proposed replies" subsection, which appears only when the Gmail draft tool was unavailable. When a section has nothing to report, replace its body with the italic one-liner shown for it. Keep prose tight — this is read in two minutes over coffee.

```markdown
# Morning Briefing — {Weekday}, {Month D, YYYY}

## TL;DR
- {3–6 bullets: the day's shape. Drafts awaiting review, decisions teammates need, top focus issues, total blocked time.}

## 📧 Email

### Needs your reply — drafts ready
| From | Subject | Their ask | Draft summary |
|---|---|---|---|
| ... | ... | ... | ... |

*(If none: "Nothing needs a reply today.")*

### Proposed replies (draft tool unavailable)
> Only include this subsection when the Gmail draft tool could not be used. For each thread, give From/Subject followed by the full proposed reply text in a blockquote, ready to copy-paste.

### Worth knowing (no reply needed)
- **{Sender} — {Subject}:** {1-line summary}

*(If none: "Nothing notable." Noise threads are never listed.)*

## 📊 Linear Projects

### {Project name} — {health: on track / at risk / off track}
{1–3 sentences: what moved recently, what's coming, risks. If issues are blocked on third parties, one line here naming the issue and who it waits on.}

*(If no started projects: "No active projects found.")*

### 🚧 Blocked — decisions needed from you
| Issue | Who's waiting | Decision needed |
|---|---|---|
| {ID} {title} | {name} | {the specific question} |

*(If empty: "Nothing is blocked on you today." — and no unblock event was created.)*

## ✅ Your Issues — today's plan
Prioritized:
1. **{ID} {title}** — {priority}, {due/estimate note}

*(If none: "No open issues assigned to you.")*

### Deferred (didn't fit today)
- {ID} {title} — {why}

*(If none: "Everything prioritized fits today.")*

## 🔭 Look-ahead — next 3 weeks

### Time off
- {Dates} — {event title}

*(If none: "No time off in the next 3 weeks.")*

### 📆 Meetings conflicting with time off
| Meeting | When | Organizer | Suggested move |
|---|---|---|---|
| {title} | {date, time} | {you / name} | {specific free slot before the trip / skip this occurrence / ask organizer to reschedule} |

*(If no time off, or no meetings overlap it: "No meetings to move." Suggestions only — the run never moves or declines anything.)*

### ⚠️ Bottlenecks
| Deadline | Collides with | Working days actually available | Suggested adjustment |
|---|---|---|---|
| {date — what's due} | {time-off block / crowded stretch} | {N} | {start earlier / move date / delegate} |

*(If none: "No bottlenecks — upcoming deadlines all have comfortable runway.")*

## 📅 Calendar blocks created
| Time | Block | Covers |
|---|---|---|
| {HH:MM–HH:MM} | [Briefing] {title} | {what it covers} |

> One row per event actually created this run — no placeholder rows for blocks that weren't needed. If a needed block could not fit on the calendar, add one line below the table saying what was deferred and why.

*(If none: "No blocks created today.")*

## Skipped
- {Source}: {reason, e.g. "Linear MCP not connected — authorize it in claude.ai connector settings"}

*(If none: "All sources available.")*
```

Formatting rules:

- Times in the user's local timezone, 24h or 12h matching their locale.
- Every Linear issue reference is a markdown link to the issue URL.
- The needs-reply table columns are exactly `From | Subject | Their ask | Draft summary` — same shape the workflow records.
- The TL;DR must be readable standalone — if the user reads nothing else, they know what to do first.

# Tool adapters

The plugin is tool-agnostic. The config names one provider per category; this
guide maps each category to the functions to call. Exact function names vary by
connector — discover them at runtime with ToolSearch (e.g. search "granola
transcript", "gmail draft", "linear issue", "clickup task") and use whatever the
connected server exposes. The notes below are starting points, not a fixed list.

## Call transcripts (`~~call transcripts`)

Goal: list meetings in the time window, then get each transcript's text.

- **Granola** — list meetings (with dates), then fetch each meeting's transcript
  by id. Filter to the window by meeting date.
- **Microsoft Teams / Google Meet / Zoom** — list recordings or meetings in the
  window, then fetch transcripts/captions. Meet recordings may live in the
  calendar or drive connector.
- **Otter / Fireflies** — list recent conversations, then fetch transcript text.

If a provider only returns a summary, use the summary; extract from whatever text
is available.

## Email (`~~email`)

Goal: find messages in the window in the configured inbox.

- **Gmail** — search threads with date bounds (e.g. `after:` / `before:` or the
  connector's equivalent query), then read each thread. To tell whether a reply
  is owed, check whether the latest message in the thread is from someone else
  and no later sent message exists.
- **Outlook** — list/search messages by received-date range, read the thread,
  apply the same "reply owed" check.

Create drafts with the connector's create-draft function. Never call a send
function.

## Project tracker (`~~project tracker`)

Goal: search for existing issues (de-dupe), then create new ones in the target
location from config.

- **Linear** — list teams/projects to resolve the target; search issues to
  de-dupe; create issues with title, description, team/project, assignee, and
  priority.
- **ClickUp** — resolve the target list; search tasks; create tasks with name,
  description, assignee, and priority.
- **Asana / Jira / Monday / Notion** — resolve the target project/board/database;
  search; create items with the equivalent fields.

Put the source line (from the extraction guide) into the description of every
created issue.

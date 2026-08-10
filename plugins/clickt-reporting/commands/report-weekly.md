---
description: Run the weekly client report cycle (pull ISO week, build pulse draft, request commentary, deploy only after approval)
argument-hint: [path to client report-package]
---

Use the clickt-reporting:client-report-weekly skill for the client report-package at:
$ARGUMENTS (ask if empty). Hard rule from the skill: build the draft and request the designated approver's
commentary, but deploy NOTHING until he approves in his reply.

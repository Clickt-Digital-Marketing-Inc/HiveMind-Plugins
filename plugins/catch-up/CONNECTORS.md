# Connectors

## How tool references work

This plugin's skills refer to tools by **category**, using a `~~` placeholder,
instead of naming a specific product. `~~project tracker` means whatever tracker
you connect and select during setup: Linear, ClickUp, Asana, Jira, and so on.

The plugin is tool-agnostic. You choose one tool per category the first time you
run it (see the `catch-up-setup` skill), and your choices are saved to
`~/.catch-up/config.json`. Every run reads that file and uses the tools you picked.

## Connectors for this plugin

| Category         | Placeholder          | Common options                                                 |
| ---------------- | -------------------- | -------------------------------------------------------------- |
| Call transcripts | `~~call transcripts` | Granola, Microsoft Teams, Google Meet, Zoom, Otter, Fireflies  |
| Email            | `~~email`            | Gmail, Outlook                                                 |
| Project tracker  | `~~project tracker`  | Linear, ClickUp, Asana, Jira, Monday, Notion                  |

## Connecting a tool

Connect each tool you want to use in Cowork's connector settings before running
setup. If a chosen tool is not connected, the plugin will tell you which one to
add and stop, rather than guessing.

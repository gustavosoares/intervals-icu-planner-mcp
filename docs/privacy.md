# Privacy policy

[← Back to README](../README.md)

Effective 24 November 2026. Applies to intervals-icu-planner-mcp: the MCP
server, the CLI and the Claude Desktop extension.

## In short

intervals-icu-planner-mcp is open-source software that runs **on your own
computer**. Its author runs no server, collects nothing, and never receives
your data or your credentials.

## What it accesses

When you or your AI assistant use one of its tools, the software reads from
or writes to **your own** intervals.icu account, through the official
intervals.icu API:

- **Calendar:** planned workouts and notes. It creates, updates and deletes
  only the events that one of your plans created.
- **Workout library:** folder and workout names, read only.
- **Wellness:** fitness, fatigue and form (CTL, ATL, ramp rate), read only.
- **Activities:** completed rides (time, distance, power, heart rate,
  training load), read only.
- **Local files:** the plan and workout files you point it at. Moving or
  shifting a plan edits that `plan.yaml`.

## Where your data goes

- **Between your computer and intervals.icu only**, over HTTPS. Nothing is
  sent to the author or to any other service.
- **To your AI assistant:** the tool results (for example, a diff of your
  calendar or a summary of last week's rides) go to the AI app you run it in,
  such as Claude, so it can answer you. That app's own privacy policy covers
  what it does with them.
- **No analytics, telemetry, tracking or advertising.** The software keeps no
  logs of your data.

## Your credentials

Your intervals.icu API key (or, if you sign in with intervals.icu, the access
token it issues) is stored only on your computer: in your system keychain
when you use the Claude Desktop extension, or wherever you put it (an
environment variable or a `.env` file). It is used only to call the
intervals.icu API, and it is never logged, printed or included in error
messages.

## Removing access

- Uninstall the extension, or remove the server from your AI app's
  configuration.
- Revoke access in intervals.icu: generate a new API key under **Settings →
  Developer Settings**, or remove the app's access from your intervals.icu
  settings if you signed in with intervals.icu.
- To remove the plans it put on your calendar, use `delete_plan`, or delete
  the events in intervals.icu.

Because the author never holds your data, there's nothing to ask them to
delete.

## Third parties

You download the software from PyPI or GitHub, and the Claude Desktop
extension installs it with uv; those services' own policies apply to the
downloads. Your use of intervals.icu is covered by its own terms and privacy policy.

## Changes and contact

Changes to this policy are published in this file, and the date above is
updated. Questions: open an issue at
<https://github.com/gustavosoares/intervals-icu-planner-mcp/issues>.

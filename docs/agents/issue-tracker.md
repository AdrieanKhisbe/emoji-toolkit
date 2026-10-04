# Issue tracker: GitHub

Issues and specs live in GitHub Issues for
AdrieanKhisbe/emoji-toolkit. Use the gh CLI from this clone,
or pass --repo AdrieanKhisbe/emoji-toolkit explicitly.

## Operations

- Publish a ticket: gh issue create --title "..." --body-file <file>
- Fetch a ticket: gh issue view <number> --comments
- List tickets: gh issue list with appropriate state and label filters.
  Include body, labels, and comments when assessing readiness.
- Comment: gh issue comment <number> --body-file <file>
- Label: gh issue edit <number> --add-label "..."
  or --remove-label "..."
- Close: gh issue close <number>

Use temporary UTF-8 files for multiline bodies.

## Pull requests as a triage surface

**PRs as a request surface: no.**

GitHub shares issue and PR numbers. For an ambiguous reference,
try gh pr view first, then gh issue view.

## Wayfinding

A map is an issue labelled wayfinder:map containing Notes,
Decisions-so-far, and Fog.

Link child tickets as GitHub sub-issues. If unavailable, use a
task list in the map and a "Part of #<map>" line in each child.
Label children wayfinder:research, wayfinder:prototype,
wayfinder:grilling, or wayfinder:task.

Use native issue dependencies for blockers, referencing numeric
database IDs. If unavailable, use "Blocked by: #<number>" lines.

The next ticket is the first open, unassigned child in map order
with no open blockers. Claim it with --add-assignee @me.

Resolve by commenting with the result, closing the ticket, and
adding a short summary and link to the map's Decisions-so-far.

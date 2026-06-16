"""Hands the scraper-audit findings to the GitHub Copilot coding agent.

Opens (or, if one is already open, refreshes) a single issue labelled
`scraper-audit` and assigns it to the Copilot bot, which makes Copilot
investigate and open a fix PR. Reusing the open issue keeps a daily run from
piling up duplicates.

Issue ops run on the ambient `GH_TOKEN`/`GITHUB_TOKEN` (the job grants it
`issues: write`); Copilot assignment alone uses the user PAT in `COPILOT_TOKEN`
(the default token cannot assign Copilot, and that PAT's user must have Copilot
enabled) — see `intensive_dance.copilot`. Reads the report written by
`intensive_dance.audit`.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from intensive_dance.copilot import (
    assign_copilot,
    comment_issue,
    create_issue,
    ensure_label,
    find_open_issue,
)

LABEL = "scraper-audit"
TITLE = "Scraper audit: live providers delivering zero offerings"


def main() -> int:
    owner_repo = os.environ.get("GITHUB_REPOSITORY", "")
    owner, _, repo = owner_repo.partition("/")
    if not owner or not repo:
        raise SystemExit("GITHUB_REPOSITORY (owner/repo) is not set")
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        raise SystemExit("GH_TOKEN (a user PAT) is required")

    report = Path(os.environ.get("AUDIT_REPORT_PATH", "scraper-audit-report.md")).read_text(
        encoding="utf-8"
    )

    ensure_label(LABEL, "B60205", "Daily scraper health audit findings")

    existing = find_open_issue(LABEL)
    if existing is not None:
        comment_issue(existing, f"Refreshed audit ({date.today().isoformat()}):\n\n{report}")
        print(f"Refreshed existing audit issue #{existing}.")
        return 0

    body = (
        f"{report}\n\n---\n_Opened automatically by the daily scraper-audit workflow and assigned "
        "to Copilot. Closing this issue stops the reminder until the next regression._"
    )
    number = create_issue(TITLE, LABEL, body)
    try:
        if assign_copilot(owner, repo, number):
            print(f"Created issue #{number} and assigned the Copilot coding agent.")
        else:
            print(
                f"::warning::Created issue #{number} but the Copilot coding agent did not stick as an "
                "assignee — assign it from the issue's Assignees menu, or confirm the agent is enabled "
                "for the repo. The issue remains as a tracker."
            )
    except Exception as exc:  # noqa: BLE001 — assignment is best-effort; the tracker issue still lands
        print(
            f"::warning::Created issue #{number} but assigning the Copilot agent failed (likely the "
            f"token lacks Contents/Pull-requests/Actions write):\n{exc}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

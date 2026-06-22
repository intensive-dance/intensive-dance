"""Opens (or refreshes) the single `doc-audit` tracker issue from the findings.

Unlike the scraper audit, this is **not** handed to Copilot: documentation fixes
need editorial judgement and several smells (counts, candidate status, repo URLs)
span sibling repos the agent can't reach. So this just keeps one reusable issue
current as a reminder for the PO — reusing the open issue stops the weekly run
from piling up duplicates. Issue ops run on the ambient `GH_TOKEN`/`GITHUB_TOKEN`
(the workflow grants `issues: write`). Reads the report written by
`intensive_dance.doc_audit`.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from intensive_dance.copilot import comment_issue, create_issue, ensure_label, find_open_issue

LABEL = "doc-audit"
TITLE = "Documentation drift: prose out of step with the data/config"


def main() -> int:
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        raise SystemExit("GH_TOKEN/GITHUB_TOKEN is required")

    report = Path(os.environ.get("DOC_AUDIT_REPORT_PATH", "doc-audit-report.md")).read_text(
        encoding="utf-8"
    )

    ensure_label(LABEL, "5319E7", "Weekly documentation-currency audit findings")

    existing = find_open_issue(LABEL)
    if existing is not None:
        comment_issue(existing, f"Refreshed audit ({date.today().isoformat()}):\n\n{report}")
        print(f"Refreshed existing doc-audit issue #{existing}.")
        return 0

    body = (
        f"{report}\n\n---\n_Opened automatically by the weekly doc-audit workflow. Fix the docs (or "
        "link/generate the fact so it can't drift), then close this — it reopens only on the next "
        "regression._"
    )
    number = create_issue(TITLE, LABEL, body)
    print(f"Created doc-audit issue #{number}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Reports scrape-workflow failures to the GitHub Copilot coding agent.

Runs as the scrape workflow's final `if: always()` job. The hourly scrape runs
each provider as a `continue-on-error` matrix leg, so a single broken scraper
never fails the job — instead each failing leg uploads a `fail-<slug>` marker
artifact. This script collects those markers (which scraper crashed) plus any
hard infrastructure failure (the select/commit jobs), distils the failed run's
logs into a digest, and reuses a single open `scrape-failure` issue so
back-to-back failures comment rather than pile up new issues.

If nothing failed (no markers, run not failed) it exits 0 without opening an
issue — so it's a cheap no-op on the common clean hourly run.

Requires a user token in `GH_TOKEN` with Actions read (to fetch logs) plus the
Contents/Pull-requests/Actions write that Copilot assignment needs.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from intensive_dance.copilot import (
    assign_copilot,
    comment_issue,
    create_issue,
    ensure_label,
    find_open_issue,
    gh,
)

LABEL = "scrape-failure"
FAIL_LINE = re.compile(r"\bFAIL\s+\S+:")
LOG_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s")


def failed_slugs(failures_dir: Path) -> list[str]:
    if not failures_dir.is_dir():
        return []
    slugs = {p.stem for p in failures_dir.glob("*.txt")}
    return sorted(slugs)


def strip_prefix(line: str) -> str:
    """`gh run view --log` prefixes each line with `job\tstep\t<ISO timestamp> `."""
    after_tabs = "\t".join(line.split("\t")[2:]) or line
    return LOG_PREFIX.sub("", after_tabs)


def fetch_log(run_id: str) -> list[str]:
    for args in (["run", "view", run_id, "--log-failed"], ["run", "view", run_id, "--log"]):
        try:
            raw = gh(args)
        except Exception:  # noqa: BLE001 — a crashed/cancelled run may have no failed-step log
            continue
        if raw:
            return [strip_prefix(line) for line in raw.splitlines()]
    return []


def dedupe(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        stripped = item.strip()
        if stripped:
            seen.setdefault(stripped, None)
    return list(seen)


def fence(content: str) -> str:
    clipped = content if len(content) <= 12_000 else f"{content[:12_000]}\n… (truncated)"
    return "```\n" + clipped.replace("```", "ʼʼʼ") + "\n```"


def main() -> int:
    owner_repo = os.environ.get("GITHUB_REPOSITORY", "")
    owner, _, repo = owner_repo.partition("/")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not owner or not repo:
        raise SystemExit("GITHUB_REPOSITORY (owner/repo) is not set")
    if not run_id:
        raise SystemExit("GITHUB_RUN_ID is not set")
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        raise SystemExit("GH_TOKEN (a user PAT) is required")

    slugs = failed_slugs(Path(os.environ.get("FAILURES_DIR", "failures")))

    run = json.loads(
        gh(
            [
                "run",
                "view",
                run_id,
                "--json",
                "displayTitle,headBranch,event,attempt,url,conclusion,workflowName",
            ]
        )
    )
    infra_failed = run.get("conclusion") == "failure"

    if not slugs and not infra_failed:
        print("No scraper failures and the run did not fail — nothing to report.")
        return 0

    log = fetch_log(run_id)
    fail_lines = dedupe([line for line in log if FAIL_LINE.search(line)])
    tail = [line for line in log if line.strip()][-120:]

    title = f"Scrape workflow failed: {run.get('displayTitle', run_id)}"
    body = "\n".join(
        [
            f"## {run.get('workflowName', 'scrape')} run failed",
            "",
            f"- **Run:** {run.get('url', '')}",
            f"- **Branch:** `{run.get('headBranch', '')}` · **Trigger:** `{run.get('event', '')}` · "
            f"**Attempt:** {run.get('attempt', '')}",
            f"- **Failing scraper(s):** {', '.join(f'`{s}`' for s in slugs) if slugs else '_none — infrastructure failure_'}",
            f"- **Detected at (UTC):** {datetime.now(timezone.utc).isoformat()}",
            "",
            f"### Per-provider FAIL lines this run ({len(fail_lines)})",
            fence("\n".join(fail_lines)) if fail_lines else "_None captured in the log._",
            "",
            "### Failed-step log tail",
            fence("\n".join(tail)) if tail else "_No log available — see the linked run._",
            "",
            "### What to do",
            "Reproduce a failing scraper locally with "
            "`uv run python -m intensive_dance.run <slug>`, fix the parser/fetch, and run the full gate "
            "(`ruff` · `ty check` · `pytest` · `schema` · `validate`). Tests stay offline (inline "
            "snippets, no network).",
            "",
            "---",
            "_Opened automatically by the scrape workflow's failure handler and assigned to Copilot. "
            "Closing this issue stops the reminder until the next failure._",
        ]
    )

    ensure_label(LABEL, "D93F0B", "Automated scrape workflow failure reports")

    existing = find_open_issue(LABEL)
    if existing is not None:
        comment_issue(existing, f"Another failure — {run.get('url', '')}\n\n{body}")
        print(f"Refreshed existing scrape-failure issue #{existing}.")
        return 0

    number = create_issue(title, LABEL, body)
    try:
        if assign_copilot(owner, repo, number):
            print(f"Created issue #{number} and assigned the Copilot coding agent.")
        else:
            print(
                f"::warning::Created issue #{number} but the Copilot coding agent did not stick as an "
                "assignee — assign it manually or confirm the agent is enabled for the repo."
            )
    except Exception as exc:  # noqa: BLE001 — assignment is best-effort; the tracker issue still lands
        print(
            f"::warning::Created issue #{number} but assigning the Copilot agent failed (likely the "
            f"token lacks Contents/Pull-requests/Actions write):\n{exc}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

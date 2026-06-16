"""Shared helpers for handing a GitHub issue to the Copilot coding agent.

Two distinct token roles, because no single repo token cleanly covers both:

- **Issue ops** (label/issue create, comment, run-log read) run on the job's
  default `GITHUB_TOKEN` — the workflow grants it `issues: write` (+ `actions:
  read` for logs), which is all these need.
- **Copilot assignment** needs a *user* PAT with Contents + Pull requests +
  Actions write (it creates a branch/PR, so an Issues-only token gets 403) and a
  Copilot-enabled user — the default `GITHUB_TOKEN` can't assign the agent at
  all. `assign_copilot` reads that PAT from `COPILOT_TOKEN` and uses it for just
  that call, leaving everything else on the default token. If `COPILOT_TOKEN` is
  unset it falls through to the ambient token (assignment then likely 403s, but
  it's best-effort — the tracker issue still lands on the default token).

Assignment goes through the documented REST agent-assignment body rather than
the GraphQL `suggestedActors` query, which unreliably omits the bot for
fine-grained PATs even when assignment works (the lesson museumsufer's
self-healing setup learned the hard way).

This is an ops helper, invoked only from the audit / failure-report scripts in
CI; it shells out to `gh` and never touches the deterministic scrape path.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Any

COPILOT_ASSIGNEE = "copilot-swe-agent[bot]"


def gh(args: list[str], token: str | None = None) -> str:
    """Run a `gh` subcommand and return its trimmed stdout, raising on failure.

    `token`, when given, overrides `GH_TOKEN` for this call only (used to run the
    Copilot assignment on a user PAT while issue ops stay on the default token).
    """
    env = {**os.environ, "GH_TOKEN": token} if token else None
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, result.args, result.stdout, result.stderr
        )
    return result.stdout.strip()


def ensure_label(name: str, color: str, description: str) -> None:
    gh(["label", "create", name, "--force", "--color", color, "--description", description])


def find_open_issue(label: str) -> int | None:
    """Return the number of the single open issue carrying `label`, if any."""
    rows: list[dict[str, Any]] = json.loads(
        gh(
            [
                "issue",
                "list",
                "--label",
                label,
                "--state",
                "open",
                "--json",
                "number",
                "--limit",
                "1",
            ]
        )
    )
    return rows[0]["number"] if rows else None


def create_issue(title: str, label: str, body: str) -> int:
    """Create an issue from a body string and return its number."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(body)
        body_file = fh.name
    url = gh(["issue", "create", "--title", title, "--label", label, "--body-file", body_file])
    number = url.rstrip("/").split("/")[-1]
    if not number.isdigit():
        raise RuntimeError(f"could not parse issue number from {url!r}")
    return int(number)


def comment_issue(number: int, body: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(body)
        comment_file = fh.name
    gh(["issue", "comment", str(number), "--body-file", comment_file])


def assign_copilot(owner: str, repo: str, issue_number: int, base_branch: str = "main") -> bool:
    """Assign the Copilot coding agent to an issue. Returns True once it sticks.

    Posts the REST agent-assignment body, which is the only documented surface
    that accepts the Copilot bot actor and triggers it to open a fix PR.
    """
    payload = {
        "assignees": [COPILOT_ASSIGNEE],
        "agent_assignment": {
            "target_repo": f"{owner}/{repo}",
            "base_branch": base_branch,
            "custom_instructions": "",
            "custom_agent": "",
            "model": "",
        },
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(payload, fh)
        payload_file = fh.name
    response: dict[str, Any] = json.loads(
        gh(
            [
                "api",
                "--method",
                "POST",
                "-H",
                "Accept: application/vnd.github+json",
                f"/repos/{owner}/{repo}/issues/{issue_number}/assignees",
                "--input",
                payload_file,
            ],
            token=os.environ.get("COPILOT_TOKEN"),
        )
    )
    assignees = response.get("assignees") or []
    return any("copilot" in (a.get("login") or "").lower() for a in assignees)

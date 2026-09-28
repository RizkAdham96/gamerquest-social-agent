from pathlib import Path


def test_manual_live_runs_cannot_bypass_weekly_reel_limit():
    workflow = Path(".github/workflows/social-agent.yml").read_text(encoding="utf-8")

    matching_lines = [
        line.strip()
        for line in workflow.splitlines()
        if line.strip().startswith("GQ_BYPASS_WEEKLY_LIMIT:")
    ]

    assert matching_lines == ['GQ_BYPASS_WEEKLY_LIMIT: "false"']

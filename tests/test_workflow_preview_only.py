from pathlib import Path


def test_workflow_is_preview_only_and_has_no_placeholder_media():
    workflow = Path(".github/workflows/social-agent.yml").read_text(
        encoding="utf-8"
    )

    assert 'GQ_LIVE_PUBLISH: "false"' in workflow
    assert "big_buck_bunny" not in workflow
    assert "GamerQuest dry run" not in workflow
    assert "GQ_TOPICS_URL is required for a real preview" in workflow
    assert "Persist publish state" not in workflow

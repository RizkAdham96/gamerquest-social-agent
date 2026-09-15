from automation.main import env_flag, build_drive_store


def test_env_flag_accepts_common_true_values(monkeypatch):
    monkeypatch.setenv('FLAG', 'yes')
    assert env_flag('FLAG') is True
    monkeypatch.setenv('FLAG', 'TRUE')
    assert env_flag('FLAG') is True


def test_env_flag_defaults_false(monkeypatch):
    monkeypatch.delenv('FLAG', raising=False)
    assert env_flag('FLAG') is False


def test_build_drive_store_returns_none_without_credentials(monkeypatch):
    monkeypatch.delenv('GQ_GOOGLE_SERVICE_ACCOUNT_FILE', raising=False)
    monkeypatch.delenv('GQ_GOOGLE_DRIVE_ACCESS_TOKEN', raising=False)
    assert build_drive_store() is None

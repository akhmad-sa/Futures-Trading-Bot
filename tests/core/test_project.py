from core.project import PROJECT_NAME, PROJECT_SLUG, VERSION


def test_project_metadata():
    assert PROJECT_NAME == "Futures Trading Bot"
    assert PROJECT_SLUG == "futures-trading-bot"
    assert VERSION


def test_cli_version_string():
    assert f"{PROJECT_NAME} {VERSION}".startswith("Futures Trading Bot")

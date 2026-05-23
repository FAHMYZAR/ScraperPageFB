from pathlib import Path

from config import load_config


def test_load_config_reads_dotenv_when_environment_is_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    Path(".env").write_text("TELEGRAM_BOT_TOKEN=999:valid_token\n", encoding="utf-8")

    config = load_config()

    assert config.bot_token == "999:valid_token"


def test_load_config_prefers_dotenv_over_dummy_placeholder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_TOKEN", "123:dummy")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    Path(".env").write_text("TELEGRAM_BOT_TOKEN=999:valid_token\n", encoding="utf-8")

    config = load_config()

    assert config.bot_token == "999:valid_token"

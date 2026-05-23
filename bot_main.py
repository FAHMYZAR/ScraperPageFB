from __future__ import annotations

from bot.app import BotApp


def main() -> int:
    app = BotApp()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

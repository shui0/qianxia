import os
from tempfile import TemporaryDirectory
from pathlib import Path

import bot

TEMP = TemporaryDirectory()
os.environ["ONEBOT_V11_ACCESS_TOKEN"] = "test-only-token"
os.environ["QIANXIA_MODEL"] = "test"
os.environ["QIANXIA_PROACTIVE_ENABLED"] = "false"
os.environ["QIANXIA_SEARCH_READ_ENABLED"] = "false"
os.environ["QIANXIA_WEB_PERSONA_ENABLED"] = "false"
os.environ["QIANXIA_MEMORY_PATH"] = str(Path(TEMP.name) / "test.sqlite3")
os.environ["QIANXIA_MAIMAI_JP_REFRESH_ENABLED"] = "false"
os.environ["QIANXIA_MAIMAI_JP_CACHE"] = str(Path(TEMP.name) / "jp.json")
bot.configure()

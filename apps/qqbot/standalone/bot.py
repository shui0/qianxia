from pathlib import Path

import nonebot
from nonebot.adapters.onebot.v11 import Adapter
from nonebot.adapters.onebot.v11.config import Config as OneBotConfig


def configure():
    nonebot.init(host="127.0.0.1", port=8080, driver="~fastapi", log_level="WARNING")
    driver = nonebot.get_driver()
    token = nonebot.get_plugin_config(OneBotConfig).onebot_access_token
    if not token or token == "replace-with-a-random-token":
        raise RuntimeError("请在 .env 中配置随机生成的 ONEBOT_V11_ACCESS_TOKEN")
    driver.register_adapter(Adapter)
    nonebot.load_from_toml(str(Path(__file__).with_name("pyproject.toml")))
    if nonebot.get_plugin("qianxia_chat") is None:
        raise RuntimeError("千夏插件加载失败，请检查启动日志")


if __name__ == "__main__":
    configure()
    nonebot.run()

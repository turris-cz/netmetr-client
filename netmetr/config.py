import random

try:
    from .uci_config import Config
except ImportError as e:
    if str(e) == "No module named 'euci'":
        Config = dict  # type: ignore
    else:
        raise e

DEFAULT_CONFIG = {
    "autostart_enabled": False,
    "autostart_delay": random.randint(0, 3600),
    "control_server": "control.netmetr.cz",
    "max_history_logs": 10,
    "uuid": None,
    "hours_to_run": (random.randint(0, 23),),
    "sync_code": None,
    "protocol_mode": "prefer_6"
}


def make_default_config():
    return Config(DEFAULT_CONFIG)

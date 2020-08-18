import os
import subprocess

from .logging import logger


CONFIG = "netmetr"
SETTINGS_SECTION = "settings"
UCI_MANDATORY_OPTIONS = {
    "max_history_logs", "control_server"
}


class Config(dict):
    def __init__(self, def_config):
        for option, value in def_config.items():
            uci_value = uci_get(option)

            if uci_value:
                super().__setitem__(option, uci_value)
            else:
                if option in UCI_MANDATORY_OPTIONS:
                    log_option_set(option, value)
                    uci_set(option, value)
                else:
                    log_option_used(option, value)

                super().__setitem__(option, value)

    def __setitem__(self, option, value):
        uci_set(option, value)
        super().__setitem__(option, value)

    def __delitem__(self, option):
        try:
            super().__delitem__(option)
        except KeyError:
            logger.debug("Failed to delete config option '{}'".format(option))
        uci_del(option)


def uci_get(var):
    if os.path.isfile("/sbin/uci"):
        # Loading control server
        process = subprocess.Popen(
            ["uci", "-q", "get", "netmetr.settings.{}".format(var)],
            stdout=subprocess.PIPE
        )
        if process.wait() == 0:
            return process.stdout.read()[:-1].decode()
    return None


def uci_set(var, value):
    if os.path.isfile("/sbin/uci"):
        retcode = subprocess.call([
            "uci", "set",
            "netmetr.settings.{}={}".format(var, value)
        ])
        if retcode != 0:
            return False
        retcode = subprocess.call(["uci", "commit"])
        return retcode == 0
    return False


def uci_del(var):
    if os.path.isfile("/sbin/uci"):
        retcode = subprocess.call([
            "uci", "-q", "delete",
            "netmetr.settings.{}".format(var)
        ])
        if retcode != 0:
            return False
        retcode = subprocess.call(["uci", "commit"])
        return retcode == 0


def log_option_set(option, value):
    logger.info("Config option '{}' not found, setting to '{}'".format(option, value))


def log_option_used(option, value):
    logger.info("Config option '{}' not found, using '{}'".format(option, value))

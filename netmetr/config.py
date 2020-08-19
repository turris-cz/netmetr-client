import euci

from .exceptions import ConfigError
from .logging import logger


CONFIG = "netmetr"
SETTINGS_SECTION = "settings"
UCI_MANDATORY_OPTIONS = {
    "autostart_enabled", "hours_to_run", "autostart_delay",
    "max_history_logs", "control_server"
}


class Config(dict):
    def __init__(self, def_config):
        self.uci = euci.EUci()
        try:
            config = self.uci.get(CONFIG)
        except euci.UciExceptionNotFound as e:
            raise ConfigError("Netmetr config not found") from e

        settings = config.get(SETTINGS_SECTION)
        if settings is None:
            raise ConfigError("'{}' section missing in config".format(
                SETTINGS_SECTION
            ))
        super().update(settings)

        self._fill_missing_options(def_config)

    def _fill_missing_options(self, def_config):
        need_to_commit = False
        for option, value in def_config.items():
            if option not in self:
                if option in UCI_MANDATORY_OPTIONS:
                    log_option_set(option, value)
                    self._uci_set(option, value)
                    need_to_commit = True
                else:
                    log_option_used(option, value)

                if need_to_commit:
                    self.uci.commit(CONFIG)

                super().__setitem__(option, value)

    def __setitem__(self, option, value):
        if self.get(option) == value:
            return

        self._uci_set(option, value)
        self.uci.commit(CONFIG, SETTINGS_SECTION, option)
        super().__setitem__(option, value)

    def __delitem__(self, option):
        try:
            super().__delitem__(option)
        except KeyError:
            logger.debug("Failed to delete config option '{}'".format(option))
        self.uci.delete(CONFIG, SETTINGS_SECTION, option)
        self.uci.commit(CONFIG, SETTINGS_SECTION, option)

    def _uci_set(self, option, value):
        try:
            self.uci.set(CONFIG, SETTINGS_SECTION, option, value)
        except euci.UciException as e:
            raise ConfigError(
                "Failed to assign value '{}' to option '{}' in config".format(
                    value, option
                )
            ) from e


def log_option_set(option, value):
    logger.warning("Config option '{}' not found, setting to '{}'".format(option, value))


def log_option_used(option, value):
    logger.warning("Config option '{}' not found, using '{}'".format(option, value))

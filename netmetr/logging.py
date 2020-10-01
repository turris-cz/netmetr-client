import json
import logging
import logging.handlers


class Logger():
    def __init__(self):
        self.lvl_debug = False
        self.colored = False
        self.logger = None
        self.quiet = False

    def set(self, debug, colored, syslog, quiet):
        self.lvl_debug = debug
        self.colored = colored
        self.quiet = quiet

        if syslog:
            self.logger = get_logger(debug)

    def debug(self, msg, detail=""):
        if self.lvl_debug:
            self._print_debug(msg, detail)

        if self.logger:
            self.logger.debug(msg)
            if detail:
                self.logger.debug(detail)

    def progress(self, msg):
        """ Colored & enabled by default (parsed by foris) but treated like debug
            by sys logger
        """
        if self.colored:
            self._print("\033[93m" + msg + "\033[0m")
        else:
            self._print(msg)

        if self.logger:
            self.logger.debug(msg)

    def output(self, msg):
        """ Enabled by default (parsed by foris) but treated like debug by sys
            logger
        """
        self._print(msg)

        if self.logger:
            self.logger.debug(msg)

    def info(self, msg):
        if self.colored:
            self._print("\033[91m" + msg + "\033[0m")
        else:
            self._print(msg)

        if self.logger:
            self.logger.info(msg)

    def warning(self, msg):
        if self.colored:
            self._print("\033[91m" + msg + "\033[0m")
        else:
            self._print(msg)

        if self.logger:
            self.logger.warning(msg)

    def error(self, msg):
        if self.colored:
            self._print("\033[41mERROR: " + msg + "\033[0m")
        else:
            self._print("ERROR: {}".format(msg))

        if self.logger:
            self.logger.error(msg)

    def log_request(self, req, url, msg=""):
        if self.lvl_debug:
            self._print_debug(
                "Sending the following request to {}\n{}".format(url, msg),
                detail=json.dumps(req, indent=2)
            )
        if self.logger:
            self.logger.debug(
                "Sending the following request to %s %s: %s", url, msg,
                json.dumps(req)
            )

    def log_response(self, resp):
        if self.lvl_debug:
            self._print_debug("response:", detail=json.dumps(resp, indent=2))
        if self.logger:
            self.logger.debug("Response: %s", json.dumps(resp))

    def log_result(self, result):
        if self.lvl_debug:
            self._print_debug("Speed test result:", detail=result)

    def _print_debug(self, msg, detail):
        if self.colored:
            self._print("\033[93m" + msg + "\033[0m")
        else:
            self._print(msg)
        self._print(detail)

    def _print(self, msg):
        if not self.quiet:
            print(msg)


def get_logger(verbose):
    """
    Configure root logger to log INFO messages to syslog and WARNING (or DEBUG
    if verbose) to console
    """
    logger_level = logging.DEBUG if verbose else logging.INFO

    logger = logging.getLogger()
    logger.setLevel(logger_level)

    syslog_level = logging.DEBUG if verbose else logging.INFO
    syslog_formatter = logging.Formatter(
            "netmetr: %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
            "%Y-%m-%d %H:%M:%S"
    )

    syslog_handler = logging.handlers.SysLogHandler(address="/dev/log")
    syslog_handler.setFormatter(syslog_formatter)
    syslog_handler.setLevel(syslog_level)
    logger.addHandler(syslog_handler)

    return logger


logger = Logger()

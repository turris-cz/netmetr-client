import json
import os
import datetime
import random
import tempfile
import time

from .argparser import get_arg_parser
from .control import ControlServer
from .exceptions import ControlServerError, MeasurementError
from .logging import logger
from .measurement import Measurement

try:
    from .config import Config
except ImportError as e:
    if str(e) == "No module named 'euci'":
        Config = dict
    else:
        raise e


HIST_FILE = "/tmp/netmetr-history.json"
DEFAULT_CONFIG = {
    "autostart_enabled": False,
    "autostart_delay": random.randint(0, 3600),
    "control_server": None,  # default one obtained using argparser
    "max_history_logs": 10,
    "uuid": None,
    "hours_to_run": (random.randint(0, 23),),
    "sync_code": None,
}


def time_to_run(config):
    if not config["autostart_enabled"]:
        return False

    if not config["hours_to_run"]:
        return False

    hours = tuple(map(int, config["hours_to_run"]))
    if datetime.datetime.now().hour not in hours:
        return False

    logger.debug("Autostarted, sleeping {} seconds before run.".format(
        config["autostart_delay"]
    ))
    time.sleep(config["autostart_delay"])

    return True


def save_history(history):
    _, hist_file = tempfile.mkstemp()
    try:
        with open(hist_file, "w") as f:
                f.write(json.dumps(history, indent=2))
        os.rename(hist_file, HIST_FILE)
    except OSError as e:
        logger.error("Error saving measurement history: {}".format(e))


def main():
    # When autostarted - check whether autostart is enabled and
    # if it is right time to run the test.
    # We expect hours when the test should be run in uci config.
    # So whenever the script is autostarted, it looks to it's config and if
    # it finds the current hour of day in it, it will start the test

    parser = get_arg_parser()
    args = parser.parse_args()

    logger.set(args.debug, not args.no_color)
    DEFAULT_CONFIG["control_server"] = args.fallback_control_server_url[0]

    config = Config(DEFAULT_CONFIG)

    if args.autostart and not time_to_run(config):
        logger.debug(
            "Autostarted but autostart disabled or not right time to run, exiting."
        )
        return

    control_server = ControlServer(
        config["control_server"],
        uuid=config["uuid"],
        use_tls=not args.unsecure_connection
    )

    if control_server.uuid != config["uuid"]:
        config["uuid"] = control_server.uuid
        del config["sync_code"]

    if not args.no_run:
        try:
            test_settings = control_server.request_settings()
            measurement = Measurement(test_settings)
            test_results = measurement.measure()
            control_server.upload_result(*test_results)
        except MeasurementError as e:
            logger.error("Measurement failed: {}".format(e))

    if args.dwlhist:
        try:
            history = control_server.download_history(config["max_history_logs"])
            save_history(history)
        except ControlServerError as e:
            logger.error("Failed to download measurement history: {}".format(e))

    try:
        sync_code = control_server.download_sync_code()
        config["sync_code"] = sync_code
        logger.info("Your Sync code is: " + sync_code)
    except ControlServerError as e:
        logger.error("Failed to download sync code: {}".format(e))


if __name__ == "__main__":
    main()

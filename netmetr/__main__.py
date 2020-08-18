import json
import os
import datetime
import tempfile

from .argparser import get_arg_parser
from .control import ControlServer
from .exceptions import ControlServerError
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
    "control_server": None,  # default one obtained using argparser
    "max_history_logs": 10,
    "uuid": None,
    "hours_to_run": (),
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

    return True


def save_history(history):
    _, hist_file = tempfile.mkstemp()
    try:
        with open(hist_file, "w") as f:
                f.write(json.dumps(history, indent=2))
        os.rename(hist_file, HIST_FILE)
    except Exception as e:
        print("Error saving measurement history.")
        print(e)


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

    if (not args.no_run):
        measurement = Measurement()

        # Request test settings from the control server
        test_settings = control_server.request_settings()
        measurement.apply_test_settings(test_settings)

        # Get the ping measurement result
        shortest_ping = measurement.measure_pings()

        # Get the speed measurement result
        speed_result = measurement.measure_speed()

        if speed_result:
            # Get detailed test statistics
            speed_flows = measurement.import_speed_flows()

            # Upload result to the control server
            result = measurement.get_test_result(shortest_ping, speed_result, speed_flows)
            control_server.upload_result(result, speed_flows)

    if args.dwlhist:
        history = control_server.download_history(config["max_history_logs"])
        save_history(history)

    try:
        sync_code = control_server.download_sync_code()
        config["sync_code"] = sync_code
        logger.info("Your Sync code is: " + sync_code)
    except ControlServerError as e:
        logger.error("Failed to download sync code: {}".format(e))


if __name__ == "__main__":
    main()

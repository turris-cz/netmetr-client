import datetime
import time

from . import __version__
from .argparser import get_arg_parser
from .exceptions import NetmetrError
from .logging import logger
from .netmetr import Netmetr
from .protocols import Mode, get_proto_mode
from .config import make_default_config


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

def main():
    parser = get_arg_parser()
    args = parser.parse_args()

    logger.set(args.debug, not args.no_color, args.syslog)
    logger.info("Netmetr Python client v{} starting...".format(__version__))

    config = make_default_config()

    if args.only_config:
        return

    # When autostarted - check whether autostart is enabled and
    # if it is right time to run the test.
    # We expect hours when the test should be run in uci config.
    # So whenever the script is autostarted, it looks to it's config and if
    # it finds the current hour of day in it, it will start the test

    if args.autostart and not time_to_run(config):
        logger.info(
            "Netmetr autostarted but autostart disabled or not right time to "
            "run, exiting."
        )
        return

    netmetr = Netmetr(
        config["control_server"],
        unsecure=args.unsecure_connection,
        config["uuid"]
    )

    config_identity_used = args.uuid is None and args.control_server is None
    if (config_identity_used and config["uuid"] != netmetr.get_uuid()):
        del config["sync_code"]
        config["uuid"] = netmetr.get_uuid()

    if not args.no_run:
        protocol_mode = get_proto_mode(config["protocol_mode"])
        netmetr.measure(protocol_mode)

    if args.dwlhist:
        netmetr.download_history(config["max_history_logs"])

    try:
        sync_code = netmetr.download_sync_code()
        if config_identity_used:
            config["sync_code"] = sync_code
        logger.info(f"Your Sync code is: {sync_code}")
    except NetmetrError as exc:
        logger.error(f"Failed to download sync code: {exc}")


if __name__ == "__main__":
    main()

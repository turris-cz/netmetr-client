import datetime
import time

from . import __version__
from .argparser import get_arg_parser
from .exceptions import NetmetrError
from .logging import logger
from .netmetr import Netmetr
from .protocols import Mode, get_proto_mode
from .config import make_default_config


def is_time_to_run(hours_to_run):
    if not hours_to_run:
        return False

    hours = tuple(map(int, hours_to_run))
    return datetime.datetime.now().hour in hours


def main():
    parser = get_arg_parser()
    args = parser.parse_args()

    logger.set(args.debug, not args.no_color, args.syslog, args.quiet)
    logger.info("Netmetr Python client v{} starting...".format(__version__))

    config = make_default_config()

    if args.only_config:
        return

    # When autostarted - check whether autostart is enabled and
    # if it is right time to run the test.
    # We expect hours when the test should be run in uci config.
    # So whenever the script is autostarted, it looks to it's config and if
    # it finds the current hour of day in it, it will start the test

    if args.autostart:
        if not config["autostart_enabled"] or not is_time_to_run(config["hours_to_run"]):
            logger.info("Autostarted but autostart disabled or not time to run, exiting.")
            return

        logger.debug(f"Autostarted, sleeping {config['autostart_delay']}s before run.")
        time.sleep(config["autostart_delay"])

    netmetr = Netmetr(
        args.control_server or config["control_server"],
        unsecure=args.unsecure_connection,
        uuid=args.uuid or config["uuid"]
    )

    config_identity_used = args.uuid is None and args.control_server is None
    if (config_identity_used and config["uuid"] != netmetr.get_uuid()):
        del config["sync_code"]
        config["uuid"] = netmetr.get_uuid()

    if not args.no_run:
        if args.bind_address:
            try:
                netmetr.measure_bind(args.bind_address)
            except NetmetrError as exc:
                logger.error(f"Measurement failed: {exc}")

        else:
            protocol_mode = get_proto_mode(config["protocol_mode"])
            if args.ipv4 and args.ipv6:
                protocol_mode = Mode.both
            elif args.ipv4 and not args.ipv6:
                protocol_mode = Mode.only_4
            elif not args.ipv4 and args.ipv6:
                protocol_mode = Mode.only_6

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

import argparse

from . import __version__


def get_arg_parser():
    parser = argparse.ArgumentParser(
            description="NetMetr - client"
            " application for download and upload speed measurement."
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version="%(prog)s {}".format(__version__)
    )

    parser.add_argument(
        "--autostart", action="store_true", help="use this"
        " option only when running as an automated service - to check whether"
        " it is right time to run the test"
    )
    parser.add_argument(
        "--dwlhist",
        action="store_true",
        help="download measurement history from the control server and save"
        " it localy"
    )
    parser.add_argument(
        "--debug", action="store_true", help="enables debug"
        " printouts"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="disables"
        " colored text output"
    )
    parser.add_argument(
        "--no-run", action="store_true", help="this option "
        "prevents from running the test. It could be used only to obtain sync"
        " code or (with --dwlhist) to download measurement history"
    )
    parser.add_argument(
        "--control-server", type=str,
        default=None,
        help="Set control server to run test against. This option takes "
             "precedence over 'control_server' defined in config file."
    )
    parser.add_argument(
        "--uuid", type=str,
        default=None,
        help="Set uuid used for the test. This option takes "
             "precedence over 'uuid' defined in config file."
    )
    parser.add_argument(
        "--unsecure-connection", action="store_true",
        help="use HTTP instead of HTTPS when communicating with control "
             "server API"
    )
    parser.add_argument(
        "--only-config", action="store_true",
        help="Only set the default mandatory configuration and exit"
    )
    parser.add_argument(
        "--syslog", action="store_true",
        help="Enable log to syslog"
    )
    parser.add_argument(
        "-4", "--ipv4", action="store_true",
        help="Run IPv4 measurement. This option takes precedence over "
             "'protocol_mode' defined in config file."
    )
    parser.add_argument(
        "-6", "--ipv6", action="store_true",
        help="Run IPv6 measurement. This option takes precedence over "
             "'protocol_mode' defined in config file."
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Produce no standard (normal "
        "console) output"
    )
    parser.add_argument(
        "-b", "--bind-address", type=str,
        default=None,
        help="Bind this local address for the test. This option takes "
             "precedence over '--ipv4' and '--ipv6' command line options and "
             "'protocol_mode' option defined in config file and uses the bind "
             "address protocol for the test."
    )

    return parser

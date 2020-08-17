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
        "--fallback-control-server-url", type=str, nargs=1,
        default=["control.netmetr.cz"],
        help="Set fallback control server to run test against in case it is "
             "not configured in UCI"
    )
    parser.add_argument(
        "--unsecure-connection", action="store_true",
        help="use HTTP instead of HTTPS when communicating with control "
             "server API"
    )

    return parser

import json
import calendar
import time
import locale
import subprocess
import shlex
import os
from random import randint
import argparse
import datetime
import tempfile
import ssl
from typing import Optional

from urllib import request

from . import __version__
from .exceptions import ConfigError, RunError
from .gps import Location
from .network import get_network_type


RMBT_BIN = "rmbt"
HIST_FILE = "/tmp/netmetr-history.json"
FALLBACK_CTRL_SRV = "control.netmetr.cz"
FALLBACK_MAX_HISTORY_LOGS = 10
FALLBACK_CLIENT_TYPE = "HW-PROBE"
DEBUG = None
COLORED_OUTPUT = None
USE_TLS = True
DEFAULT_LANG = "en_US"
CLIENT_SW_VERSION = "Python netmetr client v{}".format(__version__)

EXIT_MISSING_RMBT = 1
EXIT_CONFIG = 2

SPEED_RESULT_REQUIRED_FIELDS = {
    "res_dl_throughput_kbps",
    "res_ul_throughput_kbps",
}


def get_default_language():
    lang = locale.getdefaultlocale()[0]
    return (lang if lang else DEFAULT_LANG)


class Netmetr:
    def __init__(self):
        self.language = get_default_language()
        self.timezone = subprocess.check_output([
            "date",
            "+%Z"
        ])[:-1].decode()
        self.location = None

        self.control_server = uci_get("control_server")
        if not self.control_server:
            print_info("Control server not found, falling to: {}"
                       .format(FALLBACK_CTRL_SRV))
            self.control_server = FALLBACK_CTRL_SRV
            uci_set("control_server", FALLBACK_CTRL_SRV)
        self.client = uci_get("client")
        if not self.client:
            print_info("Client type not found, falling to: {}"
                       .format(FALLBACK_CLIENT_TYPE))
            self.client = FALLBACK_CLIENT_TYPE
            uci_set("client", FALLBACK_CLIENT_TYPE)

        if os.path.isfile("/etc/turris-version"):
            with open("/etc/turris-version", 'r') as turris_version:
                self.os_version = turris_version.read().split('\n')[0]
        else:
            self.os_version = "unknown"

        if os.path.isfile("/tmp/sysinfo/model"):
            with open("/tmp/sysinfo/model", 'r') as f:
                self.model = f.read().strip()
        else:
            self.model = "default"

        if os.path.isfile("/tmp/sysinfo/board_name"):
            with open("/tmp/sysinfo/board_name", 'r') as f:
                self.hw_version = f.read().strip()
        else:
            self.hw_version = "unknown"

    def get_time(cls) -> int:
        return int(round(calendar.timegm(time.gmtime())*1000))

    def send_request(self, req_json, path):
        url = "{}://{}/RMBTControlServer/{}".format(
                "https" if USE_TLS else "http",
                self.control_server,
                path
        )
        req = request.Request(url)
        req.add_header('Accept', 'application/json')
        req.add_header('Content-Type', 'application/json')
        data = json.dumps(req_json)

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.set_default_verify_paths()

        resp = request.urlopen(req, data.encode(), context=ctx)

        return json.loads(resp.read().decode("utf-8"))

    def load_uuid(self):
        """Checks the uci config for uuid and loads it to the
        script. If no uuid is found a https request is send to the control
        server to download it.
        """
        self.uuid = uci_get("uuid")
        if not self.uuid:
            print_info('Uuid not found, requesting new one.')
            self.uuid = None

        # the download request must be sent all the time - either to raquest
        # new uuid or to check the existing one
        self.download_uuid()

    def download_uuid(self):
        """Creates a http request and ask the control server for correct uuid
        """
        print_progress("Checking uuid on the control server...")
        # Create json to request uuid
        req_json = {
            "uuid": self.uuid,  # optional, created when omitted or left None
            "language": self.language,  # optional
            "name": "RMBT",  # required, test server type, values: "RMBT"
            "terms_and_conditions_accepted": "true",  # required
            "type": "DESKTOP",  # required, client type, values: "DESKTOP" or "MOBILE"
            "version_name": CLIENT_SW_VERSION,  # optional string
        }

        log_request(req_json, self.control_server, "settings")
        resp_json = self.send_request(req_json, 'settings')
        log_response(resp_json)
        uuid_new = resp_json["settings"][0].get("uuid", '')
        if uuid_new:
            self.uuid = uuid_new
            uci_set("uuid", self.uuid)
            uci_del("sync_code")
        else:
            self.uuid = req_json['uuid']

    def request_settings(self):
        """Creates a http request to get test token, number of threads, number
        of pings, server address and port and so on.
        """
        print_progress("Requesting test config from the control server...")
        req_json = {
            "client": "HW-PROBE",  # required, values: "HW-PROBE", "RMBT", etc
            "language": self.language,  # optional
            "time": self.get_time(),  # required
            "timezone": self.timezone,  # required
            "type": "DESKTOP",  # required, client type, values: "DESKTOP", "MOBILE"
            "uuid": self.uuid,  # required
            "version": "0.1",  # required, test version?, values: "0.1"
        }
        log_request(req_json, self.control_server, "testRequest")
        resp_json = self.send_request(req_json, 'testRequest')
        log_response(resp_json)

        self.test_server_address = resp_json["test_server_address"]
        self.test_server_port = resp_json["test_server_port"]
        self.test_token = resp_json["test_token"]
        self.test_uuid = resp_json["test_uuid"]
        self.test_numthreads = resp_json["test_numthreads"]
        self.test_numpings = resp_json["test_numpings"]
        self.test_server_encryption = resp_json["test_server_encryption"]
        self.test_duration = resp_json["test_duration"]

    def measure_pings(self) -> Optional[int]:
        """Run serie of pings to the test server and computes & saves
         the lowest one
        """

        print_progress("Starting ping test...")
        ping_values = list()
        for i in range(1, int(self.test_numpings)+1):
            process = subprocess.Popen([
                "ping", "-c1",
                self.test_server_address
            ], stdout=subprocess.PIPE)
            if (process.wait() == 0):
                try:
                    ping_result = process.stdout.read()
                    start = ping_result.index(b"time=") + len("time=")
                    end = ping_result.index(b" ms")
                    ping = float(ping_result[start:end])
                    print("ping_"+str(i)+"_msec = "+format(ping, '.2f'))
                    ping = int(ping * 1000000)
                    ping_values.append(ping)
                except:
                    print("Problem decoding pings.")
                    return None
                time.sleep(0.5)
        try:
            return min(int(s) for s in ping_values)
        except:
            return None

    def measure_speed(self):
        """Start RMBT client with saved arguments to measure the speed
        """
        # Create config file needed by rmbt-client
        _, self.config_file = tempfile.mkstemp()
        _, self.flows_file = tempfile.mkstemp()
        try:
            with open(self.config_file, "w") as config_file:
                config_file.write(
                        '{"cnf_file_flows": "'+self.flows_file+'.xz"}'
                )
        except Exception as e:
            print("Error creating config file")
            print(e)
            exit(EXIT_CONFIG)

        encryption = {True: " -e "}
        print_progress("Starting speed test...")
        try:
            test_result = subprocess.check_output(shlex.split(
                RMBT_BIN +
                encryption.get(self.test_server_encryption, "") +
                " -h " + self.test_server_address +
                " -p " + str(self.test_server_port) +
                " -t " + self.test_token +
                " -f " + self.test_numthreads +
                " -d " + self.test_duration +
                " -u " + self.test_duration +
                " -c " + self.config_file
            )).decode()

            if print_debug("Speed test result:"):
                print(test_result)
            test_result_json = json.loads(test_result.split("}")[1] + "}")

            for field in SPEED_RESULT_REQUIRED_FIELDS:
                if field not in test_result_json:
                    print_error("Speed measurement failed: '{}' missing in "
                                "result".format(field))
                    return None

            return test_result_json

        except OSError as e:
            print_error("Speed measurement failed: {}".format(e))
            exit(EXIT_MISSING_RMBT)

    def import_speed_flows(self):
        """The speedtest flow is saved to a file during the test. This function
        imports it so it could be sent to the control server.
        """
        directions = {
            "dl": "download",
            "ul": "upload"
        }
        try:
            subprocess.call(shlex.split("unxz -f "+self.flows_file+".xz"))
            with open(self.flows_file, 'r') as json_data:
                flows_json = json.load(json_data)
        except Exception as e:
            print('Problem reading/decoding flows data.')
            print(e)
            return

        speed_array = list()
        for d_short, d_long in directions.items():
            if d_short not in flows_json["res_details"]:
                print('Direction {} not found in flows data.'.format(d_long))
                continue

            thread = 0
            # Each direction has multiple threads
            for flow in flows_json["res_details"][d_short]:
                last_time = 0
                # Each thread has plenty of samples
                # We want to use a small amount of them
                for sample in flow["time_series"]:
                    if (sample.get("t") - last_time) > 30000000:
                        last_time = sample["t"]
                        speed_array.append({
                            "direction": d_long,
                            "thread": thread,
                            "time": sample["t"],
                            "bytes": sample["b"]
                         })
                thread += 1

        # Remove generated files
        try:
            os.remove(self.flows_file)
        except Exception as e:
            print(e)
        try:
            os.remove(self.config_file)
        except Exception as e:
            print(e)
        return speed_array

    def upload_result(self, ping_shortest: int, test_res, speed_array):
        """Uploads test result to the control server.

        :param ping_shortest: Minimal latency in nanoseconds
        :param test_res: JSON with the test result (obtained from RMBT binary)
        :param speed_array: Array describing speed test progress over time.
        """

        # See https://control.netmetr.cz/RMBTControlServer/api/v1/openapi#/default/post_result
        # for schema definition types from there are written as a comments
        # bellow
        req_json = {
            "client_language": self.language,  # str
            "client_name": "HW-PROBE",  # required, values: "HW-PROBE", "RMBT", etc
            "client_version": "0.1",  # required, values: "0.1"
            "client_software_version": CLIENT_SW_VERSION,  # optional string
            "geoLocations": [],
            "model": self.model,  # str
            "network_type": get_network_type(),  # int
            "product": "os: "+self.os_version+" hw: "+self.hw_version,  # str
            "test_bytes_download": test_res.get("res_total_bytes_dl"),  # int
            "test_bytes_upload": test_res.get("res_total_bytes_ul"),  # int
            "test_nsec_download": test_res.get("res_dl_time_ns"),  # int
            "test_nsec_upload": test_res.get("res_ul_time_ns"),  # int
            "test_num_threads": test_res.get("res_dl_num_flows"),  # int
            "test_ping_shortest": ping_shortest,  # int
            "num_threads_ul": test_res.get("res_ul_num_flows"),  # int
            "test_speed_download": test_res.get("res_dl_throughput_kbps"),  # int
            "test_speed_upload": test_res.get(
                "res_ul_throughput_kbps"
            ),  # int
            "test_token": self.test_token,  # str
        }
        if self.location:
            req_json["geoLocations"] = [{
                "geo_lat": self.location.lat,  # float
                "geo_long": self.location.lon,  # float
                "accuracy": self.location.hepe,  # float
                "altitude": self.location.altitude,  # float
                "bearing": self.location.bearing,  # float
                "speed": self.location.velocity,  # float
                "tstamp": self.get_time(),  # int
                "provider": "gps"  # str
            }]

        req_json["pings"] = []
        log_request(req_json, self.control_server, "result",
                    msg="(speed detail omitted)")

        req_json["speed_detail"] = speed_array
        resp_json = self.send_request(req_json, 'result')
        log_response(resp_json)

    def download_history(self):
        """Creates a http request and ask the control server for a measurement
        history.
        """
        max_history_logs = uci_get("max_history_logs")
        if not max_history_logs:
            print_info("Max history logs not found, falling to {}"
                       "".format(FALLBACK_MAX_HISTORY_LOGS))
            max_history_logs = FALLBACK_MAX_HISTORY_LOGS
            uci_set("max_history_logs", max_history_logs)

        # Create json to request history
        req_json = {
            "language": self.language,
            "timezone": self.timezone,
            "result_limit": str(max_history_logs),
            "uuid": self.uuid,
        }

        print_debug("Download measurement history from the control server.")
        log_request(req_json, self.control_server, "history")
        resp_json = self.send_request(req_json, 'history')
        log_response(resp_json)

        _, self.hist_file = tempfile.mkstemp()
        try:
            with open(self.hist_file, "w") as hist_file:
                    hist_file.write(json.dumps(resp_json, indent=2))
            os.rename(self.hist_file, HIST_FILE)
        except Exception as e:
            print("Error saving measurement history.")
            print(e)

    def download_sync_code(self):
        """Creates a http request and ask the control server for a
        synchronization code that can be used to view saved measurements from
        different devices. The new code is saved via uci.
        """
        # Create json to request synchronization code
        req_json = {
            "language": self.language,
            "timezone": self.timezone,
            "uuid": self.uuid,
        }

        print_debug("Download sync code from the control server.")
        log_request(req_json, self.control_server, "sync")
        resp_json = self.send_request(req_json, 'sync')
        log_response(resp_json)

        if not resp_json["error"]:
            self.sync_code = resp_json["sync"][0].get("sync_code", '')
            uci_set("sync_code", self.sync_code)
        else:
            self.sync_code = ''
            print("Error downloading synchronization code.")

    def load_sync_code(self):
        """Sends a https request to obtain sync code. The code must be
        downloaded each time because it coud be changed from time to time.
        """
        self.download_sync_code()

    def measure_gps(self):
        if not self.gps_console_path:
            return
        print_progress("Starting GPS measurement.")

        try:
            self.location = Location(self.gps_console_path)
        except ConfigError as e:
            print_error(str(e))
            self.location = None
        except RunError:
            print_error("GPS problem.")
            self.location = None


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
    return False


def print_debug(msg):
    if DEBUG:
        if COLORED_OUTPUT:
            print('\033[93m' + msg + '\033[0m')
        else:
            print(msg)
    return DEBUG


def print_info(msg):
    if COLORED_OUTPUT:
        print('\033[91m' + msg + '\033[0m')
    else:
        print(msg)


def print_progress(msg):
    if COLORED_OUTPUT:
        print('\033[93m' + msg + '\033[0m')
    else:
        print(msg)


def print_error(msg):
    if COLORED_OUTPUT:
        print('\033[41mERROR: ' + msg + '\033[0m')
    else:
        print('ERROR: {}'.format(msg))


def log_request(req, addr, path, msg=""):
    url = "{}://{}/RMBTControlServer/{}".format(
            "https" if USE_TLS else "http",
            addr,
            path
    )
    if print_debug("Sending the following request to {}\n{}".format(url, msg)):
            print(json.dumps(req, indent=2))


def log_response(resp):
    if print_debug("response:"):
        print(json.dumps(resp, indent=2))


def prepare_parser():
    # Prepare argument parsing
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
        '--rwait', nargs=1, type=int, default=[0],
        help='delay for a random amount of time up to RWAIT seconds before'
        ' the test starts'
    )
    parser.add_argument(
        '--autostart', action='store_true', help='use this'
        ' option only when running as an automated service - to check whether'
        ' it is right time to run the test'
    )
    parser.add_argument(
        '--dwlhist',
        action='store_true',
        help='download measurement history from the control server and save'
        ' it to {}'.format(HIST_FILE)
    )
    parser.add_argument(
        '--debug', action='store_true', help='enables debug'
        ' printouts'
    )
    parser.add_argument(
        '--no-color', action='store_true', help='disables'
        ' colored text output'
    )
    parser.add_argument(
        '--no-run', action='store_true', help='this option '
        'prevents from running the test. It could be used only to obtain sync'
        ' code or (with --dwlhist) to download measurement history'
    )
    parser.add_argument(
        '--set-gps-console', nargs=1,
        help='set path to GPS modul serial console. The GPS must be enabled to'
        ' measure location with every speed test.'
    )
    parser.add_argument(
        '--disable-gps', action='store_true', help='disable'
        ' gps location monitoring'
    )
    parser.add_argument(
        '--fallback-control-server-url', type=str, nargs=1,
        default=['control.netmetr.cz'],
        help='Set fallback control server to run test against in case it is '
             'not configured in UCI'
    )
    parser.add_argument(
        '--unsecure-connection', action='store_true',
        help='use HTTP instead of HTTPS when communicating with control '
             'server API'
    )

    return parser


def main():
    # When autostarted - check whether autostart is enabled and
    # if it is right time to run the test.
    # In uci config, we expect hours of a day separated by commas (,)
    # these hours
    # are the time the test should be run. So whenever the script is started,
    # it looks to it's config and if it finds the current hour of day in it,
    # it will start the test

    args = prepare_parser().parse_args()

    global DEBUG
    global COLORED_OUTPUT
    global FALLBACK_CTRL_SRV
    global USE_TLS

    DEBUG = args.debug
    COLORED_OUTPUT = not args.no_color
    FALLBACK_CTRL_SRV = args.fallback_control_server_url[0]
    USE_TLS = not args.unsecure_connection

    if args.autostart:
        if uci_get("autostart_enabled") != '1':
            return
        hours = uci_get("hours_to_run")
        if not hours:
            return
        hours = hours.split()
        hours = map(int, hours)
        if datetime.datetime.now().hour not in hours:
            return

    # Wait appropriate amount of time
    time.sleep(randint(0, args.rwait[0]))

    netmetr = Netmetr()
    # Request uuid from the control server
    netmetr.load_uuid()

    # GPS
    if args.disable_gps:
        netmetr.gps_console_path = None
        uci_del("gps_console_path")
    else:
        if args.set_gps_console:
            netmetr.gps_console_path = args.set_gps_console[0]
            uci_set("gps_console_path", netmetr.gps_console_path)
        else:
            netmetr.gps_console_path = uci_get("gps_console_path")

    if (not args.no_run):
        # Run gps first
        netmetr.measure_gps()

        # Request test settings from the control server
        netmetr.request_settings()

        # Get the ping measurement result
        shortest_ping = netmetr.measure_pings()

        # Get the speed measurement result
        speed_result = netmetr.measure_speed()

        if speed_result:
            # Get detailed test statistics
            speed_flows = netmetr.import_speed_flows()

            # Upload result to the control server
            netmetr.upload_result(shortest_ping, speed_result, speed_flows)

    # Optionally download measurement history from the control server
    if (args.dwlhist):
        netmetr.download_history()

    netmetr.load_sync_code()
    if (netmetr.sync_code):
        print_info("Your Sync code is: " + netmetr.sync_code)


if __name__ == "__main__":
    main()

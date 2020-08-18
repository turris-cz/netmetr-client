import json
import time
import subprocess
import shlex
import os
from random import randint
import datetime
import tempfile
from typing import Optional

from .argparser import get_arg_parser
from .control import ControlServer
from .exceptions import ConfigError, RunError, ControlServerError
from .logging import logger
from .network import get_network_type

try:
    from .config import Config
except ImportError as e:
    if str(e) == "No module named 'euci'":
        Config = dict
    else:
        raise e


RMBT_BIN = "rmbt"
HIST_FILE = "/tmp/netmetr-history.json"
DEFAULT_CONFIG = {
    "autostart_enabled": False,
    "control_server": None,  # default one obtained using argparser
    "max_history_logs": 10,
    "uuid": None,
    "hours_to_run": (),
    "sync_code": None,
}

EXIT_MISSING_RMBT = 1
EXIT_CONFIG = 2

SPEED_RESULT_REQUIRED_FIELDS = {
    "res_dl_throughput_kbps",
    "res_ul_throughput_kbps",
}


class Netmetr:
    def __init__(self):
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

    def apply_test_settings(self, settings):
        self.test_server_address = settings["test_server_address"]
        self.test_server_port = settings["test_server_port"]
        self.test_token = settings["test_token"]
        self.test_uuid = settings["test_uuid"]
        self.test_numthreads = settings["test_numthreads"]
        self.test_numpings = settings["test_numpings"]
        self.test_server_encryption = settings["test_server_encryption"]
        self.test_duration = settings["test_duration"]

    def measure_pings(self) -> Optional[int]:
        """Run serie of pings to the test server and computes & saves
         the lowest one
        """

        logger.progress("Starting ping test...")
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
        logger.progress("Starting speed test...")
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

            logger.debug("Speed test result:", test_result)
            test_result_json = json.loads(test_result.split("}")[1] + "}")

            for field in SPEED_RESULT_REQUIRED_FIELDS:
                if field not in test_result_json:
                    logger.error("Speed measurement failed: '{}' missing "
                                 " in result".format(field))
                    return None

            return test_result_json

        except OSError as e:
            logger.error("Speed measurement failed: {}".format(e))
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

    def get_test_result(self, ping_shortest: int, test_res, speed_array):
        """Uploads test result to the control server.

        :param ping_shortest: Minimal latency in nanoseconds
        :param test_res: JSON with the test result (obtained from RMBT binary)
        :param speed_array: Array describing speed test progress over time.
        """

        # See https://control.netmetr.cz/RMBTControlServer/api/v1/openapi#/default/post_result
        # for schema definition types from there are written as a comments
        # bellow
        result = {
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

        result["pings"] = []
        return result


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
        netmetr = Netmetr()

        # Request test settings from the control server
        test_settings = control_server.request_settings()
        netmetr.apply_test_settings(test_settings)

        # Get the ping measurement result
        shortest_ping = netmetr.measure_pings()

        # Get the speed measurement result
        speed_result = netmetr.measure_speed()

        if speed_result:
            # Get detailed test statistics
            speed_flows = netmetr.import_speed_flows()

            # Upload result to the control server
            result = netmetr.get_test_result(shortest_ping, speed_result, speed_flows)
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

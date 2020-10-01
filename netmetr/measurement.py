import json
import os
import shlex
import subprocess
import tempfile
import time
import typing

from .exceptions import MeasurementError
from .logging import logger
from .network import get_network_type

RMBT_BIN = "rmbt"
SPEED_RESULT_REQUIRED_FIELDS = {
    "res_dl_throughput_kbps",
    "res_ul_throughput_kbps",
}


class Measurement:
    def __init__(self, settings):
        self.results = None
        self.test_token = settings["test_token"]
        self.pings = PingMeasurement(
            settings["test_numpings"],
            settings["test_server_address"],
        )
        self.speed = SpeedMeasurement(
            settings["test_token"],
            settings["test_server_address"],
            settings["test_server_port"],
            settings["test_server_encryption"],
            settings["test_numthreads"],
            settings["test_duration"],
        )

        if os.path.isfile("/etc/turris-version"):
            with open("/etc/turris-version", "r") as turris_version:
                self.os_version = turris_version.read().split("\n")[0]
        else:
            self.os_version = "unknown"

        if os.path.isfile("/tmp/sysinfo/model"):
            with open("/tmp/sysinfo/model", "r") as f:
                self.model = f.read().strip()
        else:
            self.model = "default"

        if os.path.isfile("/tmp/sysinfo/board_name"):
            with open("/tmp/sysinfo/board_name", "r") as f:
                self.hw_version = f.read().strip()
        else:
            self.hw_version = "unknown"

    def measure(self):
        ping_shortest = self.pings.measure()
        speed_results = self.speed.measure()

        simple_result = {
            "download_mbps": round(speed_results["res_dl_throughput_kbps"] / 1000, 2),
            "upload_mbps": round(speed_results["res_ul_throughput_kbps"] / 1000, 2),
            "ping_ms": round(ping_shortest / 1000000, 2),
        }

        logger.info(
            "Test result: download: {:.2f}Mbps, upload: "
            "{:.2f}Mbps, ping: {:.2f}ms".format(
                speed_results["res_dl_throughput_kbps"] / 1000,
                speed_results["res_ul_throughput_kbps"] / 1000,
                ping_shortest / 1000000
            )
        )

        full_results = (
            self.generate_test_result(ping_shortest, speed_results),
            self.speed.import_speed_flows()
        )
        return simple_result, full_results

    def generate_test_result(self, ping_shortest: int, test_res):
        """Uploads test result to the control server.

        :param ping_shortest: Minimal latency in nanoseconds
        :param test_res: JSON with the test result (obtained from RMBT binary)
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


class PingMeasurement:
    def __init__(self, count, test_server_address):
        self.shortest = None
        self.count = count
        self.test_server_address = test_server_address

    def measure(self):
        """Run serie of pings to the test server and computes & saves
         the lowest one
        """
        ping_cmd = "ping"
        logger.progress("Starting ping test...")
        ping_values = list()
        for i in range(1, int(self.count)+1):
            process = subprocess.Popen([
                ping_cmd, "-c1",
                self.test_server_address
            ], stdout=subprocess.PIPE)
            if (process.wait() == 0):
                try:
                    ping_result = process.stdout.read()
                    start = ping_result.index(b"time=") + len("time=")
                    end = ping_result.index(b" ms")
                    ping = float(ping_result[start:end])
                    logger.output("ping_"+str(i)+"_msec = "+format(ping, ".2f"))
                    ping = int(ping * 1000000)
                    ping_values.append(ping)
                except Exception as e:
                    raise MeasurementError("Problem decoding pings: {}".format(e))
                time.sleep(0.5)
        try:
            return min(int(s) for s in ping_values)
        except Exception as e:
            raise MeasurementError("Problem getting lowest ping: {}".format(e))


class SpeedMeasurement:
    def __init__(self, token, address, port, encryption, numthreads, duration):
        self.results = None
        self.token = token
        self.address = address
        self.port = port
        self.encryption = encryption
        self.numthreads = numthreads
        self.duration = duration
        # Create config file needed by rmbt-client
        _, self.config_file = tempfile.mkstemp()
        _, self.flows_file = tempfile.mkstemp()
        try:
            with open(self.config_file, "w") as config_file:
                config_file.write(
                        '{"cnf_file_flows": "'+self.flows_file+'.xz"}'
                )
        except OSError as e:
            raise MeasurementError("Error creating measurement config file ({})".format(e))
        except IOError as e:
            raise MeasurementError("Error writing measurement config file ({})".format(e))

        encryption = {True: " -e "}
        self.rmbt_command = shlex.split(
            RMBT_BIN +
            encryption.get(self.encryption, "") +
            " -h " + self.address +
            " -p " + str(self.port) +
            " -t " + self.token +
            " -f " + self.numthreads +
            " -d " + self.duration +
            " -u " + self.duration +
            " -c " + self.config_file
        )

    def measure(self):
        """Start RMBT client with saved arguments to measure the speed
        """
        logger.progress("Starting speed test...")
        try:
            process = subprocess.Popen(
                self.rmbt_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

        except OSError as e:
            raise MeasurementError("Speed measurement failed: {}".format(e))

        while process.poll() is None:
            line = process.stderr.readline()
            if line:
                logger.output(line.decode("utf-8").strip())

        try:
            test_result = process.stdout.read().decode("utf-8")

        except UnicodeError as e:
            raise MeasurementError(
                "Speed measurement failed: Problem in decoding measurement "
                "output: {}".format(e)
            ) from e

        logger.debug("Speed test result:", test_result)

        try:
            test_result_json = json.loads(test_result.split("}")[1] + "}")

        except json.JSONDecodeError as e:
            raise MeasurementError(
                "Speed measurement failed: Problem in decoding measurement "
                "output: {}".format(e)
            ) from e

        for field in SPEED_RESULT_REQUIRED_FIELDS:
            if field not in test_result_json:
                raise MeasurementError("Speed measurement failed: '{}' missing "
                                       " in result".format(field))

        return test_result_json

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
            with open(self.flows_file, "r") as json_data:
                flows_json = json.load(json_data)
        except (OSError, IOError) as e:
            logger.error("Problem reading/decoding flows data: {}".format(e))
            return None

        speed_array = list()
        for d_short, d_long in directions.items():
            if d_short not in flows_json["res_details"]:
                logger.error("Direction {} not found in flows data.".format(d_long))
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
        except OSError as e:
            logger.error("Failed to remove flows file: {}".format(e))
        try:
            os.remove(self.config_file)
        except OSError as e:
            logger.error("Failed to remove mesurement config file: {}".format(e))
        return speed_array

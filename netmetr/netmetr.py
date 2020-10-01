import json
import os
import tempfile
import typing

from .control import ControlServer
from .exceptions import ControlServerError, MeasurementError
from .logging import logger
from .measurement import Measurement

HIST_FILE = "/tmp/netmetr-history.json"


def save_history(history):
    _, hist_file = tempfile.mkstemp()
    try:
        with open(hist_file, "w") as f:
            f.write(json.dumps(history, indent=2))
        os.rename(hist_file, HIST_FILE)
    except OSError as e:
        logger.error("Error saving measurement history: {}".format(e))


class Netmetr:
    def __init__(self, control_server_url="control.netmetr.cz",
                 unsecure=False, uuid=None):
        self.control_server = ControlServer(
            control_server_url,
            uuid=uuid,
            use_tls=not unsecure
        )

    def get_uuid(self):
        return self.control_server.uuid

    def download_history(self, logs_count):
        try:
            history = self.control_server.download_history(logs_count)
            save_history(history)
        except ControlServerError as e:
            logger.error("Failed to download measurement history: {}".format(e))

    def download_sync_code(self):
        return self.control_server.download_sync_code()

    def measure(self):
        """Measure speed and other parameters of internet connection

        Do not raise any exception on basic connection problems. Raise exceptions
        defined in netmetr.exceptions for more severe cases.
        """
        try:
            test_settings = self.control_server.request_settings()

            measurement = Measurement(test_settings)
            simple_result, full_results = measurement.measure()
            self.control_server.upload_result(*full_results)
            return simple_result
        except ControlServerError as exc:
            logger.error(f"Measurement failed ({exc})")
            return {"error": "Not available"}
        except MeasurementError as exc:
            logger.error(f"Measurement failed: {exc}")
            return {"error": "Failed"}

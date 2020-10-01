import calendar
import contextlib
import json
import locale
import ssl
import subprocess
import time

from urllib import request
import urllib.parse

from . import __version__
from .exceptions import ControlServerError
from .logging import logger
from .protocols import Protocol

CLIENT_SW_VERSION = "Python netmetr client v{}".format(__version__)
DEFAULT_LANG = "en_US"


class ControlServer:
    def __init__(self, url, uuid=None, use_tls=True):
        self.url_dual = url
        self.url_ipv4 = None
        self.url_ipv6 = None
        self.address = self.url_dual
        self.uuid = uuid
        self.use_tls = use_tls

        self.language = get_default_language()
        self.timezone = subprocess.check_output([
            "date",
            "+%Z"
        ])[:-1].decode()

        self._load_uuid()

    def _load_uuid(self):
        if not self.uuid:
            logger.warning("Uuid not found, requesting new one.")

        # the download request must be sent all the time - either to raquest
        # new uuid or to check the existing one
        logger.progress("Checking uuid on the control server...")
        req = {
            "uuid": self.uuid,  # optional, created when omitted or left None
            "name": "RMBT",  # required, test server type, values: "RMBT"
            "terms_and_conditions_accepted": "true",  # required
            "type": "DESKTOP",  # required, client type, values: "DESKTOP" or "MOBILE"
            "version_name": CLIENT_SW_VERSION,  # optional string
        }

        url = self.create_url("settings", query_params={"skip_history": "true"})
        logger.log_request(req, url)
        rep = self.send_request(req, url)
        logger.log_response(rep)
        new_uuid = rep["settings"][0].get("uuid")
        if new_uuid:
            self.uuid = new_uuid
        if not self.uuid:
            raise ControlServerError("UUID not contained in control server response")
        self.url_ipv4 = rep["settings"][0]["urls"].get("control_ipv4_only")
        self.url_ipv6 = rep["settings"][0]["urls"].get("control_ipv6_only")

    @contextlib.contextmanager
    def use_proto(self, proto):
        try:
            if proto == Protocol.IPv4:
                self.address = self.url_ipv4
            else:
                self.address = self.url_ipv6
            yield
        finally:
            self.address = self.url_dual

    def request_settings(self):
        logger.progress("Requesting test config from the control server...")
        req = {
            "client": "HW-PROBE",  # required, values: "HW-PROBE", "RMBT", etc
            "language": self.language,  # optional
            "time": get_time(),  # required
            "timezone": self.timezone,  # required
            "type": "DESKTOP",  # required, client type, values: "DESKTOP", "MOBILE"
            "uuid": self.uuid,  # required
            "version": "0.1",  # required, test version?, values: "0.1"
        }
        url = self.create_url("testRequest")
        logger.log_request(req, url)
        rep = self.send_request(req, url)
        logger.log_response(rep)

        return rep

    def upload_result(self, params, speed_array):
        # See https://control.netmetr.cz/RMBTControlServer/api/v1/openapi#/default/post_result
        # for schema definition types from there are written as a comments bellow
        req = {
            "client_language": self.language,  # str
            "client_name": "HW-PROBE",  # required, values: "HW-PROBE", "RMBT", etc
            "client_version": "0.1",  # required, values: "0.1"
            "client_software_version": CLIENT_SW_VERSION,  # optional string, showed on web
        }
        req.update(params)

        url = self.create_url("result")
        logger.log_request(req, url, msg="(speed detail omitted)")

        req["speed_detail"] = speed_array
        rep = self.send_request(req, url)
        logger.log_response(rep)

    def download_history(self, log_count):
        """Creates a http request and ask the control server for a measurement
        history.
        """

        req = {
            "language": self.language,
            "timezone": self.timezone,
            "result_limit": str(log_count),
            "uuid": self.uuid,
        }

        logger.debug("Download measurement history from the control server.")
        url = self.create_url("history")
        logger.log_request(req, url)
        rep = self.send_request(req, url)
        logger.log_response(rep)

        return rep

    def download_sync_code(self):
        """Create a http request and ask the control server for a
        synchronization code that can be used to view saved measurements from
        different devices. The new code is saved via uci.
        """
        req = {
            "language": self.language,
            "timezone": self.timezone,
            "uuid": self.uuid,
        }

        logger.debug("Download sync code from the control server.")
        url = self.create_url("sync")
        logger.log_request(req, url)
        rep = self.send_request(req, url)
        logger.log_response(rep)

        sync_code = rep["sync"][0].get("sync_code")
        if sync_code:
            return sync_code
        raise ControlServerError("Failed to download the sync code - empty response")

    def send_request(self, payload, url):
        req = request.Request(url)
        req.add_header("Accept", "application/json")
        req.add_header("Content-Type", "application/json")
        data = json.dumps(payload)

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.set_default_verify_paths()

        try:
            resp = request.urlopen(req, data.encode(), context=ctx)

        except urllib.error.HTTPError as e:
            raise ControlServerError(
                "Failed to contact the control server. "
                "This may be caused by poor internet connection or server "
                "overload - please try again later."
            ) from e

        except urllib.error.URLError as e:
            raise ControlServerError(
                "Failed to contact the control server. "
                "This may be caused by poor internet connection or wrong "
                "server address - please check it and try again later."
            ) from e

        rep = json.loads(resp.read().decode("utf-8"))
        if rep.get("error"):
            raise ControlServerError("Control server response contains error: {}".format(
                rep["error"]
            ))

        return rep

    def create_url(self, path, query_params={}):
        url = "{}://{}/RMBTControlServer/{}".format(
                "https" if self.use_tls else "http",
                self.address,
                path
        )
        params = urllib.parse.urlencode(query_params)
        return "?".join([url, params]) if params else url


def get_time() -> int:
    return int(round(calendar.timegm(time.gmtime())*1000))


def get_default_language():
    lang = locale.getdefaultlocale()[0]
    return (lang if lang else DEFAULT_LANG)

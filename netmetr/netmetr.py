import ipaddress
import json
import os
import socket
import tempfile
import typing

from .control import ControlServer
from .exceptions import ControlServerError, MeasurementError, ConfigError
from .exceptions import ProgrammingError
from .logging import logger
from .measurement import Measurement
from .protocols import Protocol, Mode

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

    def measure(self, protocol_mode: Mode = Mode.prefer_6):
        """Measure speed and other parameters of internet connection

        Do not raise any exception on basic connection problems. Raise exceptions
        defined in netmetr.exceptions for more severe cases.

        Keyword arguments:
        protocol_mode -- the protocols we want to benchmark (IPv4/IPv6) defined
          in netmetr.protocols

        Returns a dictionary with test results. An example of such a dictionary
        might be:
         {
             'IPv6': {
                 'error': 'Not available'
             },
             'IPv4': {
                 'download_mbps': 90.69,
                 'upload_mbps': 58.08,
                 'ping_ms': 4.2
             }
         }
        """
        measured = False
        result = {}
        proto_map = {
            Protocol.IPv4: [Mode.only_4, Mode.both, Mode.prefer_4],
            Protocol.IPv6: [Mode.only_6, Mode.both, Mode.prefer_6]
        }
        for proto, protocol_modes in proto_map.items():
            if protocol_mode in protocol_modes:
                try:
                    result[proto] = self._measure_protocol(proto)
                    measured = True
                except ControlServerError as exc:
                    logger.error(f"{proto.value} not available for measurement ({exc})")
                    result[proto] = {"error": "Not available"}
                except MeasurementError as exc:
                    logger.error(f"{proto.value} measurement failed: {exc}")
                    result[proto] = {"error": "Failed"}

        if not measured:
            proto = None
            if protocol_mode == Mode.prefer_4:
                proto = Protocol.IPv6
            if protocol_mode == Mode.prefer_6:
                proto = Protocol.IPv4
            if proto is not None:
                try:
                    result[proto] = self._measure_protocol(proto)
                except ControlServerError as exc:
                    logger.error(f"{proto.value} not available for measurement ({exc})")
                    result[proto] = {"error": "Not available"}
                except MeasurementError as exc:
                    logger.error(f"{proto.value} measurement failed: {exc}")
                    result[proto] = {"error": "Failed"}

        return result

    def measure_4(self):
        """Measure speed and other parameters of internet connection using IPv4

        Raise an exception whenever it is not possible to successfully finish the
        measurement

        On success, return a dictionary like this:
         {
             'download_mbps': 90.69,
             'upload_mbps': 58.08,
             'ping_ms': 4.2
         }
        """
        return self._measure_protocol(Protocol.IPv4)

    def measure_6(self):
        """Measure speed and other parameters of internet connection using IPv6

        Raise an exception whenever it is not possible to successfully finish the
        measurement

        On success, return a dictionary like this:
         {
             'download_mbps': 90.69,
             'upload_mbps': 58.08,
             'ping_ms': 4.2
         }
        """
        return self._measure_protocol(Protocol.IPv6)

    def measure_bind(self, bind_ip):
        """Bind IP address and measure speed and other parameters of internet connection

        Raise an exception whenever it is not possible to successfully finish the
        measurement

        On success, return a dictionary like this:
         {
             'download_mbps': 90.69,
             'upload_mbps': 58.08,
             'ping_ms': 4.2
         }
        """
        return self._measure_protocol(bind_ip=bind_ip)

    def _measure_protocol(self, proto: typing.Optional[Protocol] = None, bind_ip=None):
        if bind_ip is not None:
            if proto is not None:
                raise ProgrammingError("Only one option of 'proto', 'bind_ip' "
                                       "might be specified.")
            ip_proto = get_proto_from_ip(bind_ip)
            if ip_proto is None:
                raise ConfigError(f"{bind_ip} is not a valid address")
            check_addr_is_local(bind_ip, ip_proto)
            proto = ip_proto

        if proto is None:
            raise ConfigError("Measurement protocol is not specified")

        logger.progress(f"Preparing for {proto.value} measurement...")
        with self.control_server.use_proto(proto):
            test_settings = self.control_server.request_settings()

            measurement = Measurement(proto, test_settings, bind_ip=bind_ip)
            simple_result, full_results = measurement.measure()
            self.control_server.upload_result(*full_results)
            return simple_result


def get_proto_from_ip(ip):
    ip_proto = None
    proto_callback_map = {
        Protocol.IPv6: ipaddress.IPv6Address,
        Protocol.IPv4: ipaddress.IPv4Address,
    }
    for proto, callback in proto_callback_map.items():
        try:
            callback(ip)
            ip_proto = proto
        except ipaddress.AddressValueError:
            pass

    return ip_proto


def check_addr_is_local(ip, proto):
    if proto == Protocol.IPv4:
        sck = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    else:
        sck = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sck.bind((ip, 0))
    except OSError as exc:
        raise ConfigError(f"Cant bind requested address (port {port}): ({exc})")
    sck.close()

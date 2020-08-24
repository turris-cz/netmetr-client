class NetmetrError(Exception):
    pass


class ControlServerError(NetmetrError):
    pass


class MeasurementError(NetmetrError):
    pass


class ConfigError(NetmetrError):
    pass

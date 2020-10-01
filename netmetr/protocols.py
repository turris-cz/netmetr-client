import enum


from .exceptions import ConfigError


class Protocol(enum.Enum):
    IPv4 = "IPv4"
    IPv6 = "IPv6"


class Mode(enum.Enum):
    only_4 = enum.auto()
    only_6 = enum.auto()
    prefer_4 = enum.auto()
    prefer_6 = enum.auto()
    both = enum.auto()


def get_proto_mode(string):
    if string == "only_4":
        return Mode.only_4
    if string == "only_6":
        return Mode.only_6
    if string == "prefer_4":
        return Mode.prefer_4
    if string == "prefer_6":
        return Mode.prefer_6
    if string == "both":
        return Mode.both

    raise ConfigError("Not a valid protocol mode: {}".format(string))


MOBILE_PREFIX = "wwan"

NETWORK_TYPE_MOBILE = 104
NETWORK_TYPE_DEFAULT = 98


def _line_is_default_route(fields):
    """ Checks whether the fields of a line contains data declaring it
    the default route.
    The `flags` column meaning:
    https://stackoverflow.com/questions/33231034/whats-the-meaning-of-\
            proc-net-rotue-columns-especially-flags-column

    The flags column is a combination of the RTF_* flags.
    You can find them in /usr/include/linux/route.h
    """
    return fields[1] == '00000000' and int(fields[3], 16) & 1


def get_network_type():
    try:
        with open("/proc/net/route") as fh:
            for line in fh:
                fields = line.strip().split()
                if _line_is_default_route(fields):
                    if MOBILE_PREFIX in fields[0]:
                        return NETWORK_TYPE_MOBILE
                    else:
                        return NETWORK_TYPE_DEFAULT

            return NETWORK_TYPE_DEFAULT

    except OSError:
        return NETWORK_TYPE_DEFAULT

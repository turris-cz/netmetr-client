import json


class Logger():
    def __init__(self):
        self.lvl_debug = False
        self.colored = False

    def set(self, debug, colored):
        self.lvl_debug = debug
        self.colored = colored

    def debug(self, msg, detail=""):
        if self.lvl_debug:
            if self.colored:
                print("\033[93m" + msg + "\033[0m")
            else:
                print(msg)
            print(detail)

    def info(self, msg):
        if self.colored:
            print("\033[91m" + msg + "\033[0m")
        else:
            print(msg)

    def progress(self, msg):
        if self.colored:
            print("\033[93m" + msg + "\033[0m")
        else:
            print(msg)

    def error(self, msg):
        if self.colored:
            print("\033[41mERROR: " + msg + "\033[0m")
        else:
            print("ERROR: {}".format(msg))

    def log_request(self, req, url, msg=""):
        self.debug(
            "Sending the following request to {}\n{}".format(url, msg),
            detail=json.dumps(req, indent=2)
        )

    def log_response(self, resp):
        self.debug("response:", detail=json.dumps(resp, indent=2))


logger = Logger()

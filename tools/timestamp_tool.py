import time


class TimestampTool:
    @staticmethod
    def get_timestamp():
        return int(time.time() * 1000)
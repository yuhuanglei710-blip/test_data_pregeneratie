from enum import Enum
'''
基类不鸡肋，我是枚举类
'''


class Platform(Enum):
    web = 1
    android = 2
    ios = 3

class Compliancestatus(Enum):
    compliance = 1
    noncompliance = 0


class ChannelCode(Enum):
    pass

class TimestampMethod(Enum):
    add = 1
    sub = 0
    
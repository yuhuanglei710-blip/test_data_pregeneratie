import time


class TimestampTool:
    '''
    时间戳工具类：提供时间戳生成、计算、获取、换算功能
    '''
    
    #获取当前时间戳
    @staticmethod
    def get_timestamp():
        return int(time.time() )
    
    #换算时间戳
    @staticmethod
    def modify_timestamp(timestamp=get_timestamp(), days=0, hours=0, minutes=0, seconds=0):
        """
        修改时间戳，增加或减少指定的天数、小时数、分钟数和秒数
        :param timestamp: 原始时间戳
        :param days: 增加或减少的天数
        :param hours: 增加或减少的小时数
        :param minutes: 增加或减少的分钟数
        :param seconds: 增加或减少的秒数
        :return: 修改后的时间戳
        """
        total_seconds = (days * 24 * 60 * 60) + (hours * 60 * 60) + (minutes * 60) + seconds
        return timestamp + total_seconds

    

    

if __name__ == "__main__":
    timestamp_tool = TimestampTool()
    timestamp = timestamp_tool.get_timestamp()
    print("当前时间戳:", timestamp)
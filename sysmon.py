from SensorBase import SoftwareSensor
from subprocess import Popen, PIPE, TimeoutExpired
import re  # EVERYBODY STAND BACK xkcd.com/207
from utils import number_regex


class sysmon(SoftwareSensor):
    """
    Sensor to monitor the health of the computer
    """
    def __init__(self, opts):
        super().__init__(opts)
        self.mem_patterns = [
            re.compile(bytes('MemFree: +(?P<val>%s) kB' % number_regex), 'utf-8'),
            re.compile(bytes('MemAvailable: +(?P<val>%s) kB' % number_regex), 'utf-8'),
            re.compile(bytes('SwapFree: +(?P<val>%s) kB' % number_regex), 'utf-8')
        ]
        self.reading_commands = \
            ['cat /proc/loadavg']*3 + \  # 1/5/15 min load
            ['cat /proc/meminfo']*3 + \  # free mem, avail mem, avail swap
            [f'cat /sys/devices/platform/coretemp.0/hwon/{self.hwmon}/temp1_input']

    def ProcessOneReading(self, index, data):
        kb_to_gb = 1 << 20
        if index in [0,1,2]:  # system load
            return float(data.split(' ')[index])
        if index in [3,4,5]:  # memory info
            m = self.mem_patterns[i-3].search(data)
            return int(m.group('val'))/kb_to_gb
        if index in [6]:  # cpu temp
            return int(data)/1000.


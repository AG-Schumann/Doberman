from SensorBase import SoftwareSensor
import re  # EVERYBODY STAND BACK xkcd.com/207
from utils import number_regex


class sysmon(SoftwareSensor):
    """
    Sensor to monitor the health of the computer
    """
    def SetParameters(self):
        load_pattern = re.compile('(?P<load_1_min>{0}) (?P<load_5_min>{0}) (?P<load_15_min>{0}) [^ ]+ [\\d]+$'.format(number_regex).encode())
        self.patterns = {
            'load_1_min' : load_pattern,
            'load_5_min' : load_pattern,
            'load_15_min' : load_pattern,
            'free_mem' : re.compile(('MemFree: +(?P<free_mem>%s) kB' % number_regex).encode()),
            'avail_mem' : re.compile(('MemAvailable: +(?P<avail_mem>%s) kB' % number_regex).encode()),
            'free_swap' : re.compile(('SwapFree: +(?P<free_swap>%s) kB' % number_regex).encode()),
            'cpu_temp' : re.compile(('(?P<cpu_temp>%s)' % number_regex).encode())
            }
        self.reading_commands = {
                'load_1_min' : 'cat /proc/loadavg',
                'load_5_min' : 'cat /proc/loadavg',
                'load_15_min' : 'cat /proc/loadavg',
                'free_mem' : 'cat /proc/meminfo',
                'avail_mem' : 'cat /proc/meminfo',
                'free_swap' : 'cat /proc/meminfo',
                'cpu_temp' : f'cat /sys/devices/platform/coretemp.0/hwmon/{self.hwmon}/temp1_input'
            }

    def ProcessOneReading(self, name, data):
        kb_to_gb = 1 << 20
        scale = {
                'load_1_min' : 1.,
                'load_5_min' : 1.,
                'load_15_min' : 1.,
                'free_mem' : kb_to_gb,
                'avail_mem' : kb_to_gb,
                'free_swap' : kb_to_gb,
                'cpu_temp' : 1000.
            }
        return float(self.patterns[name].search(data).group(name))/scale[name]


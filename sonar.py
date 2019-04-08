from BaseSensor import SoftwareSensor
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex
from itertools import repeat


class sonar(SoftwareSensor):
    """
    Sensor that pings another machine to see if it is alive
    """
    def SetParameters(self):
        value_count = 4  # number of values returned
        self.reading_commands = dict(zip(self.reading_names, repeat(f'ping -c 3 -W 5 {self.address}')))
        packet_loss_pattern = '(?P<loss>%s)%% packet loss' % number_regex
        self.packet_loss = re.compile(packet_loss_pattern.encode())
        time_pattern = '(?P<min>{0})/(?P<avg>{0})/(?P<max>{0})/(?P<mdev>{0}) ms'.format(0=number_regex)
        self.time_taken = re.compile(time_pattern.encode())

    def ProcessOneReading(self, name, data):
        m = self.packet_loss.search(data)
        if not m:
            return None
        if m.group('loss') == b'100':
            return -1
        m = self.time_taken.search(data)
        if not m:
            return -2
        return list(map(float, m.groupdict().values()))


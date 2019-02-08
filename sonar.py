from BaseController import SoftwareController
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex


class sonar(SoftwareController):
    """
    Controller that pings another machine to see if it is alive
    """
    def __init__(self, opts):
        super().__init__(opts)
        value_count = 4  # number of values returned
        self.reading_commands = [f'ping -c 3 -W 5 {self.address}']*value_count
        packet_loss_pattern = '(?P<loss>%s)%% packet loss' % number_regex
        self.packet_loss = re.compile(bytes(packet_loss_pattern, 'utf-8'))
        time_pattern = '(?P<min>{0})/(?P<avg>{0})/(?P<max>{0})/(?P<mdev>{0}) ms'.format(0=number_regex)
        self.time_taken = re.compile(bytes(time_pattern, 'utf-8'))

    def ProcessOneReading(self, index, data):
        m = self.packet_loss.search(data)
        if not m:
            return None
        if m.group('loss') == b'100':
            return -1
        m = self.time_taken.search(data)
        if not m:
            return -2
        return list(map(float, m.groupdict().values()))


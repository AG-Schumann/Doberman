from SensorBase import LANSensor
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex


class pfeiffer_tpg(LANSensor):
    def SetParameters(self, opts):
        self._msg_begin = ''
        self._msg_end = '\r\n\x05'
        self.commands = {
                'identify' : 'AYT',
                'read' : 'PR1',
                }
        self.reading_commands = {'iso_pressure' : self.commands['read']}
        self.reading_pattern = re.compile(('(?P<status>[0-9]),(?P<value>%s)' % number_regex).encode())

    def Setup(self):
        self.SendRecv(self.commands['identify'])
        # stops the continuous flow of data


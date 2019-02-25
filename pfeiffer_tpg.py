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
        self.reading_commands = [self.commands['read']]
        self.read_command = re.compile(b'(?P<status>[0-9]),(?P<value>%s)' % bytes(number_regex, 'utf-8'))

    def Setup(self):
        self.SendRecv(self.commands['identify'])
        # stops the continuous flow of data

    def ProcessOneReading(self, index, data):
        m = self.read_command.search(data)
        if not m:
            return None
        return float(m.group('value'))


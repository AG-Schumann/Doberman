from SensorBase import SerialSensor
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex


class pfeiffer_tpg(SerialSensor):
    def SetParameters(self):
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

    def isThisMe(self, dev):
        ret = self.SendRecv(self.commands['identify'], dev)
        if ret['retcode'] or ret['data'] is None:
            return False
        if self.serialID in ret['data'].decode():
            return True
        return False

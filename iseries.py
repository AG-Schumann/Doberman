from SensorBase import SerialSensor
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex
import time


class iseries(SerialSensor):
    """
    iseries sensor
    """

    def SetParameters(self):
        self._msg_start = '*'
        self._msg_end = '\r\n'
        self.commands = {
                'hardReset' : 'Z02',  # give the device a minute after this
                'getID' : 'R05',
                'getAddress' : 'R21',
                'getDataString' : 'V01',
                'getDisplayedValue' : 'X01',
                'getCommunicationParameters' : 'R10',
                }
        self.read_pattern = re.compile(b'%s(?P<value>%s)' % (bytes(self.commands['getDisplayedValue'], 'utf-8'), bytes(number_regex, 'utf-8')))
        self.reading_commands = [self.commands['getDisplayedValue']]
        self.id_pattern = re.compile(b'%s%s' % (bytes(self.commands['getAddress'], 'utf-8'), bytes(self.serialID, 'utf-8')))

    def isThisMe(self, dev):
        info = self.SendRecv(self.commands['getAddress'], dev)
        try:
            if info['retcode']:
                self.logger.warning('Not answering correctly...')
                return False
            if not info['data']:
                return False
            if self.id_pattern.search(info['data']):
                return True
        except:
            return False

    def ProcessOneReading(self, index, data):
        m = self.read_pattern.search(data)
        if not m:
            return None
        return float(m.group('value'))


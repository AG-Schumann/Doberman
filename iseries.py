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
        self.reading_pattern = re.compile(('%s(?P<value>%s)' % (self.commands['getDisplayedValue'], number_regex)).encode())
        self.reading_commands = {self.readings[0]:self.commands['getDisplayedValue']}
        self.id_pattern = re.compile(('%s%s' % (self.commands['getAddress'], self.serialID)).encode())

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


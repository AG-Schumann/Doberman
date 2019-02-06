from ControllerBase import SerialController
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex
import time


class iseries(SerialController):
    """
    iseries controller connection
    """

    def __init__(self, opts):
        self._msg_start = '*'
        self._msg_end = '\r\n'
        self.commands = {
                'hardReset' : 'Z02',  # give the device a minute after this
                'getID' : 'R05',
                'getAddress' : 'R21',
                'enableAlarm1' : 'E01',
                'enalbeAlarm2' : 'E02',
                'disableAlarm1' : 'D01',
                'disableAlarm2' : 'D02',
                'getDataString' : 'V01',
                'getDisplayedValue' : 'X01',
                'getPeakValue' : 'X02',
                'getValleyValue' : 'X03',
                'getCommunicationParameters' : 'R10',
                'getSetpoint1' : 'R01',
                'getSetpoint2' : 'R02',
                'getAlarm1High' : 'R13',
                'getAlarm2High' : 'R16',
                'getAlarm1Low' : 'R12',
                'getAlarm2Low' : 'R15',
                }
        super().__init__(opts)
        self.read_pattern = re.compile(b'%s(?P<value>%s)' % (bytes(self.commands['getDisplayedValue'], 'utf-8'), bytes(number_regex, 'utf-8')))
        self.reading_commands = [self.commands['getDisplayedValue']]

    def isThisMe(self, dev):
        info = self.SendRecv(self.commands['getAddress'], dev)
        try:
            if info['retcode']:
                self.logger.warning('Not answering correctly...')
                return False
            if not info['data']:
                return False
            if self.serialID in info['data'].decode():
                return True
            else:
                return False
        except:
            pass
        finally:
            return False

    def ProcessOneReading(self, index, data)
        m = self.read_pattern.search(data)
        if not m:
            return None
        return float(m.group('value'))


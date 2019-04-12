from SensorBase import LANSensor
import re
from utils import number_regex


class TestSensor(LANSensor):
    def SetParameters(self):
        self._msg_start = '*'
        self._msg_end = '\r\n'
        self.reading_commands = {'one' : 'one',
                                 'two' : 'two'}
        self.reading_pattern = re.compile(('OK;(?P<value>%s)' % number_regex).encode())
        self.command_patterns = [
                (re.compile('d(?P<sides>[1-9][0-9]*)',
                    lambda m : f'SET:sides={m.group("sides")}'))]

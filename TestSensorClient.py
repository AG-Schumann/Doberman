from SensorBase import LANSensor
import re
from utils import number_regex


class TestSensor(LANSensor):
    def __init__(self, opts):
        super().__init__(opts)
        self._msg_start = '*'
        self._msg_end = '\r\n'
        self.reading_commands = ['one','two']

    def ProcessOneReading(self, index, data):
        m = re.search(bytes('OK;(?P<value>%s)' % number_regex, 'utf-8'), data)
        if not m:
            return None
        return float(m.group('value'))

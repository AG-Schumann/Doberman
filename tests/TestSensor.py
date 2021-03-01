import Doberman
import re


class TestSensor(Doberman.LANSensor):
    def set_parameters(self):
        self._msg_start = '*'
        self._msg_end = '\r\n'
        self.reading_commands = {'one' : 'READ:one',
                                 'two' : 'READ:two'}
        self.reading_pattern = re.compile(('OK;(?P<value>%s)' %
            Doberman.utils.number_regex).encode())
        self.command_patterns = [
                (re.compile('d(?P<sides>[1-9][0-9]*)'),
                    lambda m : f'SET:sides={m.group("sides")}')]

import Doberman
import re


class TestSensor(Doberman.LANSensor):
    def set_parameters(self):
        self._msg_start = '*'
        self._msg_end = '\r\n'
        self.reading_commands = {'t_in' : 'READ:t_in',
                                 't_amb' : 'READ:t_amb',
                                 'q_add': 'READ:q_add'}
        self.reading_pattern = re.compile(f'OK;(?P<value>{Doberman.utils.number_regex})'.encode())
        self.command_patterns = [
            (re.compile(f'SET q_add=({Doberman.utils.number_regex})', lambda m : f'SET:q_add={m.group(1)}'))]

import Doberman
import re


class TestDevice(Doberman.TestDevice):
    def set_parameters(self):
        self._msg_start = '*'
        self._msg_end = '\r\n'
        self.sensor_commands = {'t_in': 'READ:t_in',
                                 't_amb': 'READ:t_amb',
                                 'q_add': 'READ:q_add'}
        self.reading_pattern = re.compile(f'OK;(?P<value>{Doberman.utils.number_regex})'.encode())
        self.command_pattern = re.compile(f'set valve ([01])')

    def execute_command(self, command):
        if (m := self.command_pattern.match(command)) is not None:
            return f'SET:S_TS_01={m[1]}'

from Doberman import utils
import re


class TestSensor(Doberman.TestSensor):
    def set_parameters(self):
        self._msg_start = '*'
        self._msg_end = '\r\n'
        self.reading_commands = {'t_in': 'READ:t_in',
                                 't_amb': 'READ:t_amb',
                                 'q_add': 'READ:q_add'}
        self.reading_pattern = re.compile(f'OK;(?P<value>{utils.number_regex})'.encode())
        self.command_pattern = re.compile(f'set q_add ({utils.number_regex})')

    def execute_command(self, command):
        if (m := self.command_pattern.match(command)) is not None:
            return f'SET:q_add={m[1]}'

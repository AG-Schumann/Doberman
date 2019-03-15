from SensorBase import SerialSensor
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex
import time


class Teledyne(SerialSensor):
    """
    Teledyne flow controller
    THCD-100
    """
    accepted_commands = [
            'setpoint <value>: change setpoint',
            'valve <auto|open|close>: change valve status',
        ]
    def SetParameters(self):
        self._msg_end = '\r\n'
        self.commands = {
                'Address' : 'add',
                'read' : 'r',
                'SetpointMode' : 'spm',
                'Unit' : 'uiu',
                'SetpointValue' : 'spv'
                }
        self.device_address = 'a'  # changeable, but default is a
        self.basecommand = f'{self.device_address}' + '{cmd}'
        self.setcommand = self.basecommand + ' {params}'
        self.getcommand = self.basecommand + '?'

        self.reading_pattern = re.compile(('READ:(?P<value>%s)' % number_regex).encode())
        self.get_addr = re.compile(b'ADDR: *(?P<addr>[a-z])')
        self.command_echo = f'\\*{self.device_address}\\*:' + '{cmd} *;'
        self.retcode = f'!{self.device_address}!(?P<retcode>[beow])!'

        self.setpoint_map = {'auto' : 0, 'open' : 1, 'close' : 2}
        self.reading_commands = {'flow' : self.commands['read']}
        self.command_patterns = [
                (re.compile(r'setpoint (?P<params>%s)' % number_regex),
                    lambda x : self.setcommand.format(cmd=self.commands['SetpointValue'],
                        **x.groupdict())),
                (re.compile(r'valve (?P<params>auto|open|close)'),
                    lambda x : self.setcommand.format(cmd=self.commands['SetpointMode'],
                        params=self.setpoint_map[x.group('params')])),
                ]

    def isThisMe(self, dev):
        command = self.getcommand.format(cmd=self.commands['Address'])
        resp = self.SendRecv(command, dev)
        if resp['retcode'] or not resp['data']:
            return False
        m = self.get_addr.search(resp['data'])
        if not m:
            return False
        if self.device_address != m.group('addr').decode():
            return False
        return True


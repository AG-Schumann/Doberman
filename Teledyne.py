from ControllerBase import SerialController
import re  # EVERYBODY STAND BACK xkcd.com/208


class Teledyne(SerialController):
    """
    Teledyne flow controller
    THCD-100
    """
    def __init__(self, opts):
        self._msg_end = '\r\n'
        self.commands = {
                'Address' : 'add',
                'read' : 'r',
                'SetpointMode' : 'spm',
                'Unit' : 'uiu',
                'SetpointValue' : 'spv'
                }
        super().__init__(opts)
        self.device_address = 'a'  # changeable, but default is a
        self.basecommand = f'{self.device_address}' + '{cmd}'
        self.setcommand = self.basecommand + ' {params}'
        self.getcommand = self.basecommand + '?'

        self.get_reading = re.compile(r'READ:(?P<value>-?[0-9]+(?:\.[0-9]+)?)')
        self.get_addr = re.compile(r'ADDR: *(?P<addr>[a-z])')
        self.command_echo = f'\\*{self.device_address}\\*:' + '{cmd} *;'
        self.retcode = f'!{self.device_address}!(?P<retcode>[beow])!'

        self.setpoint_map = {'auto' : 0, 'open' : 1, 'closed' : 2}

        self.command_patterns = [
                (re.compile(r'setpoint (?P<params>-?[0-9]+(?:\.[0-9]+)?)'),
                    lambda x : self.setcommand.format(cmd=self.commands['SetpointValue'],
                        **x.groupdict())),
                (re.compile(r'setpoint (?P<params>auto|open|closed)'),
                    lambda x : self.setcommand.format(cmd=self.commands['SetpointMode'],
                        params=self.setpoint_map[x.group('params')])),
                ]

    def isThisMe(self, dev):
        command = self.getcommand.format(cmd=self.commands['Address'])
        resp = self.SendRecv(command, dev)
        if resp['retcode'] or not resp['data']:
            return False
        m = self.get_addr.search.search(resp['data'])
        if not m:
            return False
        if self.device_address != m.group('addr'):
            return False
        return True

    def Readout(self):
        command = self.basecommand.format(cmd=self.commands['read'])
        resp = self.SendRecv(command)
        if resp['retcode'] or not resp['data']:
            return resp
        m = self.get_reading.search(resp['data'])
        if not m:
            return {'retcode' : -4, 'data' : -1}
        return {'retcode' : 0, 'data' : float(m.group('value'))}


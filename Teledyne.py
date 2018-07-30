from ControllerBase import SerialController
import logging
import re  # EVERYBODY STAND BACK xkcd.com/208


class Teledyne(SerialController):
    """
    Teledyne flow controller
    THCD-100
    """
    def __init__(self, opts):
        self.logger = logging.getLogger(opts['name'])
        self._msg_end = '\r\n'
        self.commands = {
                'Address' : 'add',
                'read' : 'r',
                'SetpointMode' : 'spm',
                'Unit' : 'uiu',
                'SetpointValue' : 'spv'
                }
        super().__init__(opts, self.logger)
        self.device_address = 'a'  # changeable, but default is a
        self.basecommand = f'{self.device_address}' + '{cmd}'
        self.setcommand = self.basecommand + ' {params}'
        self.getcommand = self.basecommand + '?'

        self.get_reading = re.compile(r'READ:(?P<value>-?[0-9]+(\.[0-9]+)?)')
        self.get_addr = re.compile(r'ADDR: *(?P<addr>[a-z])')
        self.command_echo = f'\\*{self.device_address}\\*:' + '{cmd} *;'
        self.retcode = f'!{self.device_address}!(?P<retcode>[beow])!'

        self.get_spt_value = re.compile(r'setpoint (?P<value>-?[0-9]+(\.[0-9]+)?)')
        self.get_spt_mode = re.compile(r'setpoint (?P<mode>(auto)|(open)|(closed))')

    def isThisMe(self, dev):
        command = self.getcommand.format(cmd=self.commands['Address'])
        resp = self.SendRecv(command, dev)
        if resp['retcode'] or not resp['data']:
            return False
        m = self.get_addr.search(resp['data'])
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
        m = self.get_reading(resp['data'])
        if not m:
            return {'retcode' : -3, 'data' : [-1]}
        return {'retcode' : 0, 'data' : float(m.group('value'))}

    def ExecuteCommand(self, command):
        """
        Allows for changing the setpoint (mode or value). Recognized command:
        setpoint <value>
        setpoint <auto|open|closed>
        """
        mv = self.get_spt_value(command)
        if not mv:
            mm = self.get_spt_mode(command)
            if not mm:
                self.logger.error('Did not understand command: %s' % command)
                return
            else:
                command = self.setcommand.format(cmd=self.commands['SetpointMode'],
                        params = mm.group('mode'))
        else:
            command = self.setcommand.format(cmd=self.commands['SetpointValue'],
                    params = mv.group('value'))
        resp = self.SendRecv(command)
        if resp['retcode'] or not resp['data']:
            self.logger.error('Controller didn\'t like command: %s' % command)
            return
        m = self.retcode.search(resp['data'])
        if not m:
            self.logger.error('Not sure why you are seeing this...')
            return
        if m.group('retcode') != 'o':
            self.logger.error('Device gave retcode %s!' % m.group('retcode'))
        return

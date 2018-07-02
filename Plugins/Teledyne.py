from ControllerBase import SerialController
import logging


class Teledyne(SerialController):
    """
    Teledyne flow controller
    """
    def __init__(self, opts):
        self.logger = logging.getLogger(__name__)
        self._basecommand = 'a{command}'
        self.device_address = 'a'  # changeable, but default is a
        self._msg_end = '\r\n'
        self.commands = {
                'getAddress' : 'add?',
                'read' : 'r',
                'getSetpointMode' : 'spm?',
                'getUnit' : 'uiu?',
                }
        super().__init__(opts, logger)

    def checkController(self):
        resp = self.SendRecv(self.commands['getAddress'])
        if resp['retval']:
            self.logger.error('Error checking controller')
            self._connected = False
            return -1
        if self.device_address != resp['data']:
            self.logger.error('Addresses don\'t match somehow, expected %s got %s' % (
                self.device_address, resp['data']))
            return -2
        self.logger.info('Connected to %s correctly' % self.name)
        self.add_ttyUSB()
        return 0

    def Readout(self):
        command = self._basecommand.format(command = self.commands['read'])
        resp = self.SendRecv(command)
        return resp

    def SendRecv(self, command):
        """
        The Teledyne has a more complex communication protocol, so we reimplement this
        method here to parse the output
        Sample output for a Read command (without \\r and split on \\n):
        ['*a*:r  ; ', 'READ:-0.007;0', '!a!o!']
        """
        message = self._msg_start + self._basecommand.format(address = self.device_address,
                    command = command) + self._msg_end
        val = super().SendRecv(command)
        if val['retcode']:
            return val
        if not val['data']:
            self.logger.error('Didn\'t receive any data from controller!')
            val['retcode'] = -3
            return val

        reply = val['data'].replace('\r','').splitlines()
        if len(reply) != 3:
            self.logger.error('Didn\'t receive the right amount of data: %s' % reply)
            val['retcode'] = -4
            return val

        echo = reply[0].rstrip('; ')
        if echo != '*{c}*:{s}'.format(c=self.device_address, s=command):
            self.logger.error('Didn\'t echo the right command: %s' % echo)
            val['retcode'] = -5
            return val

        resp = reply[2]
        if resp != '!{c}!o!'.format(c=self.device_address):
            self.logger.error('Command (%s) was not accepted' % command)
            val['retcode'] = -6
            return val

        data = reply[1].split(':')
        self.logger.debug('Got %s data' % data)
        if data[0] == 'READ':
            val['data'] = float(data[1].split(';')[0])
        elif data[0] == 'ADDR':
            val['data'] = data[1].lstrip()
        return val

from ControllerBase import SerialController
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex


class pfeiffer_tpg(SerialController):
    def __init__(self, opts):
        self._msg_begin = ''
        self._msg_end = '\r\n\x05\r\n'
        super().__init__(opts)
        self.commands = {
                'identify' : 'AYT',
                'read' : 'PRX',
                }
        self.read_command = re.compile(r'[0-9],(?P<value>%s)' % number_regex)

    def Readout(self):
        resp = self.SendRecv(self.commands['read'])
        if resp['retcode']:
            return resp
        m = self.read_command.search(resp['data'])
        if not m:
            self.logger.debug('Error?')
            return {'retcode' : -3, 'data' : -1}
        return {'retcode' : 0, 'data' : float(m.group('value'))}

    def isThisMe(self, dev):
        pass


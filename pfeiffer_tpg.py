from ControllerBase import LANController
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex


class pfeiffer_tpg(LANController):
    def SetupBeforeOpening(self):
        self._msg_begin = ''
        self._msg_end = '\r\n\x05'
        self.commands = {
                'identify' : 'AYT',
                'read' : 'PR1',
                }
        self.read_command = re.compile(b'(?P<status>[0-9]),(?P<value>%s)' % bytes(number_regex, 'utf-8'))

    def SetupAfterOpening(self):
        self.SendRecv(self.commands['identify'])
        # stops the continuous flow of data

    def Readout(self):
        resp = self.SendRecv(self.commands['read'])
        if resp['retcode']:
            return resp
        m = self.read_command.search(resp['data'])
        if not m:
            self.logger.debug('Error?')
            return {'retcode' : -3, 'data' : -1}
        return {'retcode' : int(m.group('status')), 'data' : float(m.group('value'))}


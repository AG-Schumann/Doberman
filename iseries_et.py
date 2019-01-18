from ControllerBase import LANController
import re  # EVERYBODY STAND BACK xkcd.com/2069
from utils import number_regex
import time


class iseries_et(LANController):
    """
    iseries controller with LAN connection
    """

    def __init__(self, opts):
        self._msg_start = '*'
        self._msg_end = '\r\n'
        self.commands = {
                'hardReset' : 'Z02',  # give the device a minute after this
                'getID' : 'R05',
                'getAddress' : 'R21',
                'getDataString' : 'V01',
                'getDisplayedValue' : 'X01',
                'getCommunicationParameters' : 'R10',
                }
        super().__init__(opts)
        self.read_pattern = re.compile(b'%s(?P<value>%s)' % (bytes(self.commands['getDisplayedValue'], 'utf-8'), bytes(number_regex, 'utf-8')))
        self.id_pattern = re.compile(b'%s%s' % (bytes(self.commands['getAddress'], 'utf-8'), bytes(self.serialID, 'utf-8')))


    def Readout(self):
        val = self.SendRecv(self.commands['getDisplayedValue'])
        if not val['data'] or val['retcode']:
            self.logger.debug('No data?')
            time.sleep(1)
            val = self.SendRecv(self.commands['getDisplayedValue'])
            if not val['data'] or val['retcode']:
                self.logger.error('No data!')
                return val
        m = self.read_pattern.search(val['data'])
        if not m:
            self.logger.error('Device didn\'t echo correct command')
            val['retcode'] = -4
            val['data'] = -1
            return val
        val['data'] = float(m.group('value'))
        return val


 def Readout(self):
        resp = self.SendRecv(self.commands['read'])
        if resp['retcode']:
            return resp
        m = self.read_command.search(resp['data'])
        if not m:
            self.logger.debug('Error?')
            return {'retcode' : -3, 'data' : -1}
        return {'retcode' : int(m.group('status')), 'data' : float(m.group('value'))}



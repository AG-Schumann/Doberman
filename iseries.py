from ControllerBase import SerialController
import logging


class iseries(SerialController):
    """
    iseries controller connection
    """

    def __init__(self, opts):
        self.logger = logging.getLogger(opts.name)
        self._msg_start = '*'
        self._msg_end = '\r\n'
        self.commands = {
                'hardReset' : 'Z02',
                'getID' : 'R05',
                'getAddress' : 'R21',
                'enableAlarm1' : 'E01',
                'enalbeAlarm2' : 'E02',
                'disableAlarm1' : 'D01',
                'disableAlarm2' : 'D02',
                'getDataString' : 'V01',
                'getDisplayedValue' : 'X01',
                'getPeakValue' : 'X02',
                'getValleyValue' : 'X03',
                'getCommunicationParameters' : 'R10',
                'getSetpoint1' : 'R01',
                'getSetpoint2' : 'R02',
                'getAlarm1High' : 'R13',
                'getAlarm2High' : 'R16',
                'getAlarm1Low' : 'R12',
                'getAlarm2Low' : 'R15',
                }
        super().__init__(opts, self.logger)

    def checkController(self):
        info = self.SendRecv(self.commands['getAddress'])
        if info['retcode']:
            self.logger.warning('Not answering correctly...')
            self._connected = False
            return False
        if self.device_id in info['data']:
            self.logger.info('Connected to %s correctly' % self.name)
            return True
        else:
            self.logger.warning('Controller ID not correct! Expected %s, got %s' % self.device_id, info['data'])
            self._connected = False
            return False
        return False

    def Readout(self):
        val = self.SendRecv(self.commands['getDisplayedValue'])
        cmd_len = len(self.commands['getDisplayedValue']) + len(self._msg_start)
        val['data'] = float(val['data'][cmd_len:])
        return val


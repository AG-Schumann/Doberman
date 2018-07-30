from ControllerBase import SerialController
import logging


class iseries(SerialController):
    """
    iseries controller connection
    """

    def __init__(self, opts):
        self.logger = logging.getLogger(opts['name'])
        self._msg_start = '*'
        self._msg_end = '\r\n'
        self.commands = {
                'hardReset' : 'Z02',  # give the device a minute after this
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

    def isThisMe(self, dev):
        info = self.SendRecv(self.commands['getAddress'], dev)
        if info['retcode']:
            self.logger.warning('Not answering correctly...')
            return False
        if not info['data']:
            return False
        if self.serialID in info['data']:
            return True
        else:
            return False
        return False

    def Readout(self):
        val = self.SendRecv(self.commands['getDisplayedValue'])
        if not val['data']:
            self.logger.error('No data??')
            return val
        if self.commands['getDisplayedValue'] not in val['data']:
            self.logger.error('Device didn\'t echo correct command')
            val['data'] = -1
            return val
        val['data'] = float(val['data'].split(self.commands['getDisplayedValue'])[-1])
        return val

    def ExecuteCommand(self, command):
        return

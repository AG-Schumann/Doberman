from Doberman.Controller import SerialController


class iseries(SerialController):
    """
    iseries controller connection
    """

    def __init__(self, opts):
        self.__msg_start = '*'
        self.__msg_end = '\r\n'
        commands = {
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
        super().__init__(opts)

    def checkController(self):
        info = self.SendRecv(self.commands['getID'])
        if info['retcode']:
            self.logger.warning('Not answering correctly...')
            self.__connected = False
            return -1
        if info['data'] == self._ID:
            self.logger.info('Connected to %s correctly' % self.name)
            try:
                with open(self.ttypath, 'a+') as f:
                    f.write(" %i | %s" % (self.ttyUSB, self.name))
            except Exception as e:
                self.logger.warning('Could not add ttyusb to file! Error %s' % e)
            else:
                self.occupied_ttyUSB.append(self.ttyUSB)
            finally:
                return 0
        else:
            self.logger.warning('Controller ID not correct! Should be %s, not %s' % self._ID, info['data'])
            self.__connected = False
            return -2
        return -3

    def Readout(self):
        return self.SendRecv(self.commands['getDisplayedValue'])

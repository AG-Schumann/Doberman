from Doberman.Controller import SerialController
import logging


class caen_n1470(SerialController):
    """
    Connects to the CAEN N1470. Command syntax:
    '$BD:<board number>,CMD:<MON,SET>,CH<channel>,PAR:<parameter>[,VAL:<%.2f>]\\r\\n'
    Return syntax:
    error:
    '#BD:<board number>,<error type>:ERR'
    correct:
    '#BD:<board number>,CMD:OK[,VAL:<value>[,<value>...]]'
    """

    def __init__(self, opts):
        self.logger = logging.getLogger(__name__)
        self.__msg_start = '$'
        self.__msg_end = '\r\n'
        self.channels = opts.channels
        self._bd = opts.board
        self.SN = opts.SN
        self.commands = {'read' : 'BD:{},CMD:MON,CH{},PAR:{}',
                        'write' : 'BD:{},CMD:SET,CH{},PAR:{},VAL:{:06.2f}',
                        'name' : 'BD:{},CMD:MON,PAR:BDNAME',
                        'snum' : 'BD:{},CMD:MON,PAR:BDSNUM'}
        super().__init__(opts)

    def checkController(self):
        val = self.SendRecv(self.commands['name'].format(self._bd))
        if val['retcode']:
            self.logger.error('Could not confirm device')
            self.__connected = False
            return -1
        if 'N1470' not in val['data']:
            self.logger.error('Connected to %s instead of N1470?' % val['data'].split(',')[2].split(':')[1])
            self.__connected = False
            return -2
        val = self.SendRecv(self.commands['snum'].format(self._bd))
        if val['retcode']:
            self.logger.error('Could not check serial number')
            self.__connected = False
            return -3
        sn = val['data'].split(',')[2].split(':')[1]
        if sn != self.SN:
            self.logger.error('Serial number doesn\'t check out, expected %s got %s' % (self.SN, sn))
            self.__connected = False
            return -4
        else:
            self.logger.debug('Successfully connected')
            self.add_ttyusb(self.ttyUSB)
            return 0
        return -3

    def Readout(self):
        """
        We need to read voltage and current from all channels
        """
        readings = []
        status = []
        for com in ['VMON','IMON']:
            for ch in self.channels:
                res = SendRecv(self.commands['read'].format(BD=self._bd,ch,com))
                if res['retcode'] or 'ERR' in res['data']:
                    readings.append[-1]
                    status.append[-1]
                    self.logger.error('Error reading ch %i: %s' % (ch,res['data'].split(',')[1]))
                else:
                    status.append[0]
                    val = res['data'].split(',')[2]
                    readings.append(float(val))
        return {'retcode' : status, 'data' : readings}

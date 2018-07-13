from ControllerBase import SerialController
import logging
import re  # EVERYBODY STAND BACK (xkcd.com/208)


class MKS_MFC(SerialController):
    """
    MKS flow controller
    """

    def __init__(self, opts):
        self.logger = logging.getLogger(opts.name)
        self._msg_start = f"@@@{self.serialID}"
        self._msg_end = ";FF" # ignores checksum
        self.commands = {'Address' : 'CA',
                         'Units' : 'U',
                         'FlowRate' : 'FX',
                         'FlowRatePercent' : 'F',
                         'Status' : 'T',
                         'InternalTemperature' : 'TA',
                         'DeviceType' : 'DT',
                         'SetpointValue' : 'SX',
                         'SetpointPercent' : 'S',
                         'ValvePosition' : 'VO',
                         'SoftStartRate' : 'SS',
                         }
        self.errorcodes = {
                '01' : 'Checksum error',
                '10' : 'Syntax error',
                '11' : 'Data length error',
                '12' : 'Invalid data',
                '13' : 'Invalid operating mode',
                '14' : 'Invalid action',
                '15' : 'Invalid gas',
                '16' : 'Invalid control mode',
                '17' : 'Invalid command',
                '24' : 'Calibration error',
                '25' : 'Flow too large',
                '27' : 'Too many gases in gas table',
                '28' : 'Flow cal error; valve not open',
                '98' : 'Internal device error',
                '99' : 'Internal device error',
                }
        self.getCommand = f'{self.commands[com]}?'
        self.setCommand = f'{self.commands[com]}!{value}'
        self._ACK == 'ACK'
        self._NAK == 'NAK'
        super().__init__(opts, self.logger)
        self.nak_pattern = re.compile(f'{self._NAK}(?P<errcode>[^;]+);')
        self.ack_pattern = re.compile(f'{self._ACK}(?P<value>[^;]+);')

    def isThisMe(self, dev):
        com = 'Address'
        resp = self.SendRecv(self.getCommand, dev)
        if not resp['data'] or resp['retcode']:
            return False
        if resp['data'] == self.serialID:
            return True
        return False

    def Checksum(self, message):
        checksum = 0
        checksum += sum(map(ord, message))
        checksum += sum(map(ord, self.serialID))
        checksum += sum(map(ord, self._msg_start[-1] + self._msg_end[0]))
        return checksum

    def Readout(self):
        values = []
        status = []
        for com in ['FlowRate','FlowRatePercent','InternalTemperature']:
            resp = self.SendRecv(self.getCommand)
            if resp['retcode']:
                values.append(-1)
                status.append(resp['retcode'])
            else:
                try:
                    values.append(float(resp['data']))
                except:
                    values.append(-1)
                    status.append(-4)
                else:
                    status.append(0)
        return {'retcode' : status, 'data' : values}

    def SendRecv(self, message, dev=None):
        """
        Message format: @@@<device address><command>;<checksum>
        Checksum = FF -> ignore
        Command = FX? (or something else)
        Returned info format: @@@<masterID><response>;<checksum>
        response is 'ACK<value>' or 'NAK<error code>'
        """
        resp = super().SendRecv(message, dev)
        if not resp['data'] or resp['retcode']:
            return resp
        if self._NAK in resp['data']:
            m = self.nak_pattern.search(resp['data'])
            resp['retcode'] = -3
            if m:
                resp['data'] = self.errorcodes[m.group('errcode')]
            else:
                resp['data'] = None
            return resp
        m = ack_pattern.search(resp['data'])
        if not m:
            return {'retcode' : 0, 'data' : None}
        else:
            return {'retcode' : 0, 'data' : m.group('value')}
        output = resp['data'].lstrip(self._msg_start[0]).lstrip(self.masterID)
        output = output.split(';')[0]
        return {'retcode' : 0, 'data' : output[3:-3]}


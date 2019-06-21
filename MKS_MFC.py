from SensorBase import SerialSensor
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex


class MKS_MFC(SerialSensor):
    """
    MKS flow sensor
    """
    accepted_commands = [
            'setpoint <value>: change the setpoint',
            'valve <auto|close|purge>: change valve status',
        ]
    def SetParameters(self):
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
        self.getCommand = '{cmd}?'
        self.setCommand = '{cmd}!{value}'
        self._ACK = 'ACK'
        self._NAK = 'NAK'
        self.nak_pattern = re.compile((f'{self._NAK}(?P<errcode>[^;]+);').encode())
        self.ack_pattern = re.compile((f'{self._ACK}(?P<value>[^;]+);').encode())
        self.reading_commands = {
                'flow' : self.getCommand.format(cmd=self.commands['FlowRate']),
                'flow_pct' : self.getCommand.format(cmd=self.commands['FlowRatePercent']),
                'temp' : self.getCommand.format(cmd=self.commands['InternalTemperature'])}
        self.setpoint_map = {'auto' : 'NORMAL', 'purge' : 'PURGE', 'close' : 'FLOW_OFF'}
        self.command_patterns = [
                (re.compile(r'setpoint (?P<value>%s)' % number_regex),
                    lambda x : self.setCommand.format(cmd=self.commands['SetpointValue'],
                        **x.groupdict())),
                (re.compile(r'valve (?P<value>auto|close|purge)'),
                    lambda x : self.setCommand.format(cmd=self.commands['ValvePosition'],
                        value=self.setpoint_map[x.group('value')]))
                ]

    def isThisMe(self, dev):
        resp = self.SendRecv(self.getCommand.format(cmd=self.commands['Address']), dev)
        if not resp['data'] or resp['retcode']:
            return False
        if resp['data'] == self.serialID:
            return True
        return False

    def ProcessOneReading(self, name, data):
        m = self.nak_pattern.search(data)
        if m:
            return -1*int(m.group('value'))
        m = self.ack_pattern.search(data)
        if not m:
            return -2
        return float(m.group('value'))


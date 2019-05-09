from SensorBase import SerialSensor
import time
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex


class isegNHQ(SerialSensor):
    """
    iseg NHQ sensor
    """
    accepted_commands = [
            'Vset <value>: voltage setpoint',
            'Ilim <value>: current limit',
            'Vramp <value>: voltage ramp speed',
            'Vstart: start voltage ramp after inhibit',
        ]

    def SetParameters(self):
        self._msg_end = '\r\n'
        self._msg_start = ''
        self.basecommand = '{cmd}'
        self.setcommand = self.basecommand + '={value}'
        self.getcommand = self.basecommand
        self.commands = {'open'     : '',
                         'identify' : '#',
                         'Delay'    : 'W',
                         'Voltage'  : f'U{self.channel}',
                         'Current'  : f'I{self.channel}',
                         'Vlim'     : f'M{self.channel}',
                         'Ilim'     : f'N{self.channel}',
                         'Vset'     : f'D{self.channel}',
                         'Vramp'    : f'V{self.channel}',
                         'Vstart'   : f'G{self.channel}',
                         'Itrip'    : f'L{self.channel}',
                         'Status'   : f'S{self.channel}',
                         'Auto'     : f'A{self.channel}',
                         }
        statuses = ['ON','OFF','MAN','ERR','INH','QUA','L2H','H2L','LAS','TRP']
        self.state = dict(zip(statuses,range(len(statuses))))
        self.reading_commands = {s.lower:self.commands[s] for s in ['Current','Voltage','Vset','Status']}

        self.command_patterns = [
                (re.compile('(?P<cmd>Vset|Itrip|Vramp) +(?P<value>%s)' % number_regex),
                    lambda m : self.setcommand.format(cmd=self.commands[m.group('cmd')],
                        value=m.group('value'))),
                (re.compile('(?P<cmd>Vstart)', lambda m : self.commands['Vstart'])
                ]

    def Setup(self):
        self.SendRecv(self.basecommand.format(cmd=self.commands['open']))

    def isThisMe(self, dev):
        resp = self.SendRecv(self.commands['open'], dev)
        if resp['retcode']:
            return False
        resp = self.SendRecv(self.commands['identify'], dev)
        if resp['retcode'] or not resp['data']:
            return False
        return resp['data'].decode().rstrip().split(';')[0] == self.serialID

    def ProcessOneReading(self, name, data):
        data = data.splitlines()[1]
        if name == 'current':
            data = data.decode()
            return float(f'{data[:3]}E{data[4:]}')
        elif name in ['voltage', 'vset']:
            return float(data)
        elif name == 'status':  # state
            data = data.split(b'=')[1].strip()
            return self.state.get(data.decode(), -1)

    def Readout(self):
        """
        Keeping this around for reference sake
        """
        vals = []
        status = []
        coms = ['Current','Voltage','Vset','Status']
        funcs = [lambda x : float(f'{x[:3]}E{x[4:]}'), float,
                float, lambda x : self.state.get(x.split('=')[1].strip(),-1)]
        for com,func in zip(coms,funcs):
            cmd = self.getcommand.format(cmd=self.commands[com])
            resp = self.SendRecv(cmd)
            status.append(resp['retcode'])
            if status[-1]:
                vals.append(-1)
            else:
                data = resp['data'].split(bytes(cmd, 'utf-8'))[-1]
                vals.append(func(data.decode()))
        return {'retcode' : status, 'data' : vals}

    def SendRecv(self, message, dev=None):
        """
        The iseg does things char by char, not string by string
        This handles that
        """
        device = dev if dev else self._device
        msg = self._msg_start + message + self._msg_end
        response = ''
        ret = {'retcode' : 0, 'data' : None}
        for c in msg:
            device.write(c.encode())
            time.sleep(1)
            echo = device.read(1).decode()
            if c != echo:
                pass
            time.sleep(1)
        if '=' in message:  # 'set' command, nothing left other than CR/LF
            device.read(device.in_waiting)
            return ret

        time.sleep(1)  # 'send' bit finished, now to receive the reply
        ret['data'] = device.read(device.in_waiting).decode().rstrip()
        time.sleep(0.5)
        return ret


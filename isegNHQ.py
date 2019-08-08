from SensorBase import SerialSensor
import time
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex
import serial


class isegNHQ(SerialSensor):
    """
    iseg NHQ sensor
    """
    accepted_commands = [
            "arm ramp <up|down>: prepare to ramp the voltage",
            "confirm ramp <up|down>: confirm the voltage ramp",
        ]

    def SetParameters(self):
        self._msg_end = '\r\n'
        self._msg_start = ''
        self.basecommand = '{cmd}'
        self.last_ramp_request = None
        self.setcommand = self.basecommand + '={value}'
        self.getcommand = self.basecommand
        self.channel = int(self.channel)
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
        self.reading_commands = {s.lower():self.commands[s]
                for s in ['Current', 'Voltage', 'Vset', 'Status']}

        self.command_patterns = [
                (re.compile("^(arm|confirm) ramp (up|down)$"), self.Ramp),
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
        data = data.splitlines()[1].rstrip()
        if name == 'current':
            data = data.decode()
            return float(f'{data[:4]}E{data[4:]}')
        if name in ['voltage', 'vset']:
            return float(data)
        if name == 'status':  # state
            data = data.split(b'=')[1].strip()
            return self.state.get(data.decode(), -1)

    def Ramp(self, m):
        """
        Normally this would return a string that gets added to
        the readout schedule, but we have several things to queue,
        so we call AddToSchedule here and return None
        """
        if m.group(1) == 'arm':
            if self.last_ramp_request is not None:
                self.logger.error('Ramp already armed')
                return
            self.last_ramp_request = time.time()
            self.logger.info('Please confirm ramp command')
            return
        elif m.group(1) == 'confirm':
            if self.last_ramp_request is None:
                self.logger.error('Ramp not armed')
                return
            if time.time() - self.last_ramp_request < 10:
                self.logger.info('Acknowledged, begging ramp sequence')
                self.last_ramp_request = None
            else:
                self.logger.error('Ramp request denied')
                self.last_ramp_request = None
                return
        else:
            self.logger.info('Whaa...?')
        if m.group(2) == 'up':
            target = int(self.setpoint)
        elif m.group(2) == 'down':
            target = 0
        else:
            self.logger.error('I don\'t know how to ramp "%s"' % m.group(2))
            return
        ramp_commands = [
                ("Status", None),  # reading status word clears inhibit
                ("Vramp", int(self.ramp_rate)),
                ("Vset", target),
                ("Vstart", None),
                ]
        for cmd, val in ramp_commands:
            if val is not None:
                self.AddToSchedule(command=self.setcommand.format(cmd=self.commands[cmd],
                                                           value=val))
            else:
                self.AddToSchedule(command=self.commands[cmd])

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
        response = b''
        ret = {'retcode' : 0, 'data' : None}
        try:
            for c in msg:
                device.write(c.encode())
                for _ in range(10):
                    time.sleep(0.2)
                    echo = device.read(1)
                    if echo is not None:
                        response += echo
                        break
                time.sleep(0.2)
            time.sleep(2)
            blank_counter = 0
            while blank_counter < 5 and device.in_waiting > 0:
                time.sleep(0.2)
                byte = device.read(1)
                if not byte:
                    blank_counter += 1
                    continue
                blank_counter = 0
                response += byte
        except serial.SerialException as e:
            self.logger.error('Serial exception: %s' % e)
            ret['retcode'] = -2
        except Exception as e:
            self.logger.error('Error sending message: %s' % e)
            ret['retcode'] = -3

        ret['data'] = response
        time.sleep(0.1)
        return ret

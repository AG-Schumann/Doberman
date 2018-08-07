from ControllerBase import SerialController
import time
import re  # EVERYBODY STAND BACK xkcd.com/208


class isegNHQ(SerialController):
    """
    iseg NHQ controller
    """
    def __init__(self, opts):
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
        super().__init__(opts)

        self.command_patterns = [
                (re.compile(f'{cmd} (?P<value>-?[0-9]+(?:\\.[0-9]+)?)'),
                    lambda x : self.setcommand.format(cmd=self.commands[f'{cmd}'],
                        value=x.group('value'))) for cmd in ['Vset','Itrip','Vramp']
                ]


    def _getControl(self):
        super()._getControl()
        self.SendRecv(self.basecommand.format(cmd=self.commands['open']))
        self.SendRecv(self.setcommand.format(cmd=self.commands['Delay'],
            value=self.delay))

    def isThisMe(self, dev):
        resp = self.SendRecv(self.commands['open'], dev)
        if resp['retval']:
            return False
        resp = self.SendRecv(self.commands['identify'], dev)
        if resp['retval'] or not resp['data']:
            return False
        if resp['data'].split(';')[0] == self.serialID:
            return True
        return False

    def Readout(self):
        vals = []
        status = []
        coms = ['Status','Voltage','Current','Vset']
        funcs = [lambda x : self.state.get(x,-1), float,
                lambda x: float(f'{x[:3]}E{x[4:]}'), float]
        for com,func in zip(coms,funcs):
            cmd = self.getcommand.format(cmd=self.commands[com])
            resp = self.SendRecv(cmd)
            status.append(resp['retval'])
            if status[-1]:
                vals.append[-1]
            else:
                data = resp['data'].split(cmd)[-1]
                #data = resp['data']
                vals.append(func(data))
        return {'retcode' : status, 'data' : vals}

    def SendRecv(self, message, dev=None):
        """
        The iseg does things char by char, not string by string
        This handles that, checks for the echo, and strips the \\r\\n
        """
        return super().SendRecv(message,dev)
        device = dev if dev else self._device
        msg = self._msg_start + message + self._msg_end
        response = ''
        ret = {'retcode' : 0, 'data' : None}
        for c in msg.encode():
            device.write(c)
            time.sleep(self.delay)
            echo = device.read(1)
            if c != echo:
                self.logger.error(f'Command {message} not echoed!')
                ret['retcode'] = -1
                return ret
            time.sleep(self.delay)
        if '=' in message: # 'set' command, nothing left other than CR/LF
            device.read(2)
            return ret

        time.sleep(0.5) # 'send' bit finished, now to receive the reply
        blank_bytes = 0
        for _ in range(64):
            byte = device.read(1).decode()
            if not byte:
                blank_bytes += 1
            else:
                response += byte
                blank_bytes = 0
            if blank_bytes >= 5 or response[-2:] == self._msg_end:
                break
            time.sleep(self.delay)
        ret['data'] = response.rstrip()
        return ret


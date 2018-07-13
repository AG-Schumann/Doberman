from ControllerBase import SerialController
import logging
import time


class isegNHQ(SerialController):
    """
    iseg NHQ controller
    """
    def __init__(self, opts):
        self.logger = logging.getLogger(opts.name)
        self._msg_end = '\r\n'
        self._msg_start = ''
        self.commands = {'open' : '',
                         'identify' : '#',
                         'getDelay' : 'W',
                         'setDelay' : f'W={self.delay:03d}',
                         'getVoltage' : f'U{self.channel}',
                         'getCurrent' : f'I{self.channel}',
                         'getVlim' : f'M{self.channel}',
                         'getIlim' : f'N{self.channel}',
                         'getVset' : f'D{self.channel}',
                         'setVset' : f'D{self.channel}={self.vset:04d}',
                         'getVramp' : f'V{self.channel}',
                         'setVramp' : f'V{self.channel}={self.vramp:03d}',
                         'getVstart' : f'G{self.channel}',
                         'getItrip' : f'L{self.channel}',
                         'setItrip' : f'L{self.channel}={self.itrip}',
                         'getStatus' : f'S{self.channel}',
                         'getAuto' : f'A{self.channel}',
                         'setAuto' : f'A{self.channel}={self.isauto}',
                         }
        statuses = ['ON','OFF','MAN','ERR','INH','QUA','L2H','H2L','LAS','TRP']
        self.state = dict(zip(statuses,range(len(statuses))))
        super().__init__(opts, logger)

    def _getControl(self):
        super()._getControl()
        self.SendRecv(self.commands['open'])
        self.SendRecv(self.commands['setDelay'])

    def isThisMe(self, dev):
        resp = self.SendRecv(self.commands['open', dev])
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
        coms = ['getStatus','getVoltage','getCurrent','getVset']
        funcs = [lambda x : self.state.get(x,-1), float,
                lambda x: float(f'{x[:3]}E{x[4:]}'), float]
        for com,func in zip(coms,funcs):
            resp = self.SendRecv(self.commands[com])
            status.append(resp['retval'])
            if status[-1]:
                vals.append[-1]
            else:
                vals.append(func(resp['data']))
        return {'retcode' : status, 'data' : vals}

    def SendRecv(self, message, dev=None):
        """
        The iseg does things char by char, not string by string
        This handles that, checks for the echo, and strips the \\r\\n
        """
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


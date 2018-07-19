from ControllerBase import LANController
import logging
import re  # EVERYBODY STAND BACK xckd.com/208


class cryocon_22c(LANController):
    """
    Cryogenic controller
    """
    def __init__(self, opts):
        self.logger = logging.getLogger(opts.name)
        self._msg_end = ';\n'
        self.commands = { # these are not case sensitive
                'identify' : '*idn?',
                'getTempA' : 'input? a:units k',
                'getTempB' : 'input? b:units k',
                'getSP1' : 'loop 1:setpt?',
                'getSP2' : 'loop 2:setpt?',
                'getLp1Pwr' : 'loop 1:htread?',
                'getLp2Pwr' : 'loop 2:htread?',
                'setTempAUnits' : 'input a:units k',
                'settempBUnits' : 'input b:units k',
                'setSP' : f'loop {channel}:setpt {value}',
                'shitshitfirezemissiles' : 'stop',
                'stop' : 'stop',
                }
        super().__init__(opts, self.logger)
        self.read_pattern = re.compile(r'(?P<value>[0-9]+(\.[0-9]+)?)')
        self.set_pattern = re.compile(r'setpoint (?P<channel>1|2) (?P<value>[0-9]+(\.[0-9]+)?)')

    def isThisMe(self, dev):
        return True  # don't have the same problems with LAN controllers

    def Readout(self):
        resp = []
        stats = []
        for com in ['getTempA','getTempB','getSP1','getSP2','getLp1Pwr','getLp2Pwr']:
            val = self.SendRecv(self.commands[com])
            if val['retcode']:
                resp.append(-1)
                stats.append(val['retcode'])
            else:
                try:
                    m = self.read_pattern.search(val['data'])
                    if m:
                        resp.append(float(m.group('value')))
                        stats.append(0)
                    else:
                        resp.append(-1)
                        stats.append(-2)
                except Exception as e:
                    self.logger.error('Could not read device! Error: %s' % e)
                    return {'retcode' : -2, 'data' : None}
        return {'retcode' : stats, 'data' : resp}

    def ExecuteCommand(self, command):
        """
        Accepted commands:
        setpoint <1|2> <value>
        stop
        """
        if command in self.commands:  # handles 'stop' commands
            self.SendRecv(self.commands[command])
            self.logger.info('Send command %s' % command)
            return
        m = self.set_pattern.search(command)
        if not m:
            self.logger.error('Could not understand command: %s' % command)
            return
        val = self.SendRecv(self.commands['setSP'].format(**m.groupdict())
        if val['retcode']:
            self.logger.error('Could not send command: %s' % command)
        else:
            self.logger.info('Successfully sent command: %s' % command)
        return


from ControllerBase import LANController
import re  # EVERYBODY STAND BACK xkcd.com/208


class cryocon_22c(LANController):
    """
    Cryogenic controller
    """
    def __init__(self, opts):
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
                'setSP' : 'loop {ch}:setpt {value}',
                }
        super().__init__(opts)
        self.read_pattern = re.compile(r'(?P<value>[0-9]+(?:\.[0-9]+)?)')
        self.command_patterns = [
                (re.compile(r'setpoint (?P<ch>1|2) (?P<value>[0-9]+(?:\.[0-9]+)?)'),
                    lambda x : self.commands['setSP'].format(**x.groupdict())),
                (re.compile('(shitshitfirezemissiles)|(loop stop)'),
                    lambda x : 'stop'),
                ]

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


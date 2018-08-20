from ControllerBase import LANController
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex


class cryocon_22c(LANController):
    """
    Cryogenic controller
    """
    accepted_commands = [
            'setpoint <channel> <value>: change the setpoint for the given channel',
            'loop stop: shut down both heaters'
        ]
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
        self.read_pattern = re.compile(r'(?P<value>%s)' % number_regex)
        self.command_patterns = [
                (re.compile(r'setpoint (?P<ch>1|2) (?P<value>%s)' % number_regex),
                    lambda x : self.commands['setSP'].format(**x.groupdict())),
                (re.compile('(shitshitfirezemissiles)|(loop stop)'),
                    self.FireMissiles),
                ]

    def isThisMe(self, dev):
        return True  # don't have the same problems with LAN controllers

    def FireMissiles(self, m):  # worth it for an entire function? Totally
        if 'missiles' in m.group(0):
            self.logger.warning('But I am leh tired...')
        return 'stop'

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
                        stats.append(-4)
                except Exception as e:
                    self.logger.error('Could not read device! Error: %s' % e)
                    return {'retcode' : -4, 'data' : None}
        return {'retcode' : stats, 'data' : resp}


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
                'getLp1Pwr' : 'loop 1:htrread?',
                'getLp2Pwr' : 'loop 2:htrread?',
                'setTempAUnits' : 'input a:units k',
                'settempBUnits' : 'input b:units k',
                'setSP' : 'loop {ch}:setpt {value}',
                }
        super().__init__(opts)
        self.read_pattern = re.compile(b'(?P<value>%s)' % bytes(number_regex, 'utf-8'))
        self.read_commands = [self.commands[x] for x in ['getTempA','getTempB','getSP1','getSP2','getLp1Pwr','getLp2Pwr']]
        self.command_patterns = [
                (re.compile(r'setpoint (?P<ch>1|2) (?P<value>%s)' % number_regex),
                    lambda x : self.commands['setSP'].format(**x.groupdict())),
                (re.compile('(shitshitfirezemissiles)|(loop stop)'),
                    self.FireMissiles),
                ]

    def FireMissiles(self, m):  # worth it for an entire function? Totally
        if 'missiles' in m.group(0):
            self.logger.warning('But I am leh tired...')
        return 'stop'

    def ProcessOneReading(self, index, data):
        return float(self.read_pattern.search(data).group('value'))


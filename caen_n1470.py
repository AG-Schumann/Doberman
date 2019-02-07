from BaseController import SerialController
import logging
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex


class caen_n1470(SerialController):
    """
    Connects to the CAEN N1470. Command syntax:
    '$BD:<board number>,CMD:<MON,SET>,CH<channel>,PAR:<parameter>[,VAL:<%.2f>]\\r\\n'
    Return syntax:
    error:
    '#BD:<board number>,<error type>:ERR'
    correct:
    '#BD:<board number>,CMD:OK[,VAL:<value>[,<value>...]]'
    """
    accepted_commands = [
        '<anode|cathode> <on|off>',
        '<anode|cathode> vset <value>',
    ]

    def __init__(self, opts):
        super().__init__(opts)
        self._msg_start = '$'
        self._msg_end = '\r\n'
        self.commands = {'read' : f'BD:{self.board},' + 'CMD:MON,CH:{ch},PAR:{par}',
                        'name' : f'BD:{self.board},CMD:MON,PAR:BDNAME',
                        'snum' : f'BD:{self.board},CMD:MON,PAR:BDSNUM'}
        self.setcommand = f'BD:{self.board},CMD:SET,' + 'CH:{ch},PAR:{par},VAL:{val}'
        self.powercommand = f'BD:{self.board},CMD:SET,' + 'CH:{ch},PAR:{par}'
        self.error_pattern = re.compile(b',[A-Z]{2,3}:ERR')
        s = 'VAL:%s' % ';'.join(['(?P<val%i>%s)' % (i, number_regex) for i in range(4)])
        self.read_pattern = re.compile(bytes(s, 'utf-8'))
        self.command_patterns = [
                (re.compile('(?P<ch>anode|cathode) (?P<par>on|off)'),
                    lambda x : self.powercommand.format(
                        ch=self.channel_map[x.group('ch')],par=x.group('par').upper())),
                (re.compile('(?P<ch>anode|cathode) vset (?P<val>%s)' % number_regex),
                    lambda x : self.setcommand.format(ch=self.channel_map[x.group('ch')],
                        par='VSET', val=x.group('val'))),
                ]

    def isThisMe(self, dev):
        val = self.SendRecv(self.commands['name'], dev)
        if not val['data'] or val['retcode']:
            return False
        if b'N1470' not in val['data']:
            return False
        val = self.SendRecv(self.commands['snum'])
        if not val['data'] or val['retcode']:
            return False
        sn = val['data'].decode().rstrip().split('VAL:')[1]
        if sn != self.serialID:
            return False
        else:
            return True

    def Readout(self):
        """
        We need to read voltage and current from all channels
        """
        readings = []
        status = []
        ch = 4  # reads all channels in one command
        for com in ['VMON','VSET','IMON','STAT']:
            res = self.SendRecv(self.commands['read'].format(ch=ch,par=com))
            if not res['data'] or res['retcode']:
                readings += [-1] * len(self.channel_map)
                status += [res['retcode']] * len(self.channel_map)
                self.logger.error("No data for %s" % com)
                continue
            m = self.error_pattern.search(res['data'])
            if m:
                readings += [-1] * len(self.channel_map)
                status += [-3] * len(self.channel_map)
                self.logger.error('Error reading %s: %s' % (com,m.group(0)))
                continue
            m = self.read_pattern.search(res['data'])
            if m:
                status += [0] * len(self.channel_map)
                readings += map(float, [m.group('val%i' % i) for _,i in self.channel_map.items()])
            else:
                status += [-4] * len(self.channel_map)
                readings += [-1] * len(self.channel_map)
        return {'retcode' : status, 'data' : readings}


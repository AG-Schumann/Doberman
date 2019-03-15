from SensorBase import SerialSensor
import re  # EVERYBODY STAND BACK xkcd.com/208
from utils import number_regex
from itertools import product


class caen_n1470(SerialSensor):
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

    def SetParameters(self):
        self._msg_start = '$'
        self._msg_end = '\r\n'
        self.commands = {'read' : f'BD:{self.board},' + 'CMD:MON,CH:{ch},PAR:{par}',
                        'name' : f'BD:{self.board},CMD:MON,PAR:BDNAME',
                        'snum' : f'BD:{self.board},CMD:MON,PAR:BDSNUM'}
        self.setcommand = f'BD:{self.board},CMD:SET,' + 'CH:{ch},PAR:{par},VAL:{val}'
        self.powercommand = f'BD:{self.board},CMD:SET,' + 'CH:{ch},PAR:{par}'
        self.error_pattern = re.compile(r',[A-Z]{2,3}:ERR'.encode())
        self.reading_commands = {}
        cmds = [('VMON','voltage'), ('VSET','setpt'), ('IMON','i'), ('STAT','status')]
        for (cmd, cmd_n),(ch,ch_i) in product(cmds, self.channel_map.items()):
            key = '%s_%s' % (ch, cmd_n)
            self.reading_commands[key] = self.commands['read'].format(ch=ch_i,par=cmd))
        self.reading_pattern = re.compile(('OK,VAL:(?P<value>%s)' % number_regex).encode())
        self.command_patterns = [
                (re.compile('(?P<ch>anode|cathode|screen) (?P<par>on|off)'),
                    lambda x : self.powercommand.format(
                        ch=self.channel_map[x.group('ch')],par=x.group('par').upper())),
                (re.compile('(?P<ch>anode|cathode|screen) vset (?P<val>%s)' % number_regex),
                    lambda x : self.setcommand.format(ch=self.channel_map[x.group('ch')],
                        par='VSET', val=x.group('val'))),
                ]

    def isThisMe(self, dev):
        val = self.SendRecv(self.commands['name'], dev)
        if not val['data'] or val['retcode']:
            return False
        if b'N1470' not in val['data']:
            return False
        val = self.SendRecv(self.commands['snum'], dev)
        if not val['data'] or val['retcode']:
            return False
        sn = val['data'].decode().rstrip().split('VAL:')[1]
        if sn != self.serialID:
            return False
        else:
            return True


from ControllerBase import SerialController
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

    def __init__(self, opts):
        super().__init__(opts)
        self._msg_start = '$'
        self._msg_end = '\r\n'
        self.commands = {'read' : f'BD:{self.board},' + 'CMD:MON,CH{ch},PAR:{par}',
                        'write' : f'BD:{self.board},' + 'CMD:SET,CH{ch},PAR:{par},VAL:{val}',
                        'name' : f'BD:{self.board},CMD:MON,PAR:BDNAME',
                        'snum' : f'BD:{self.board},CMD:MON,PAR:BDSNUM'}
        self.setcommand = f'BD:{self.board},CMD:SET,' + 'CH:{ch},PAR:{par},VAL:{val}'
        self.powercommand = f'BD:{self.board},CMD:SET,' + 'CH:{ch},PAR:{par}'
        self.error_pattern = re.compile(',[A-Z]{2,3}:ERR')
        self.read_pattern = re.compile('VAL:(?P<val>%s)' % number_regex)
        self.command_patterns = [
                (re.compile('channel (?P<ch>anode|cathode) (?P<par>on|off)'),
                    lambda x : self.powercommand.format(
                        ch=self.channel_map[x.group('ch')],par=x.group('par'))),
                (re.compile('channel (?P<ch>anode|cathode) (?P<par>vset|rup|rdw) (?P<val>%s' % number_regex),
                    lambda x : self.setcommand.format(ch=self.channel_map[x.group('ch')],
                        par=x.group('par').upper(), val=x.group('val'))),
                ]

    def isThisMe(self, dev):
        val = self.SendRecv(self.commands['name'], dev)
        if not val['data'] or val['retcode']:
            return False
        if 'N1470' not in val['data']:
            return False
        val = self.SendRecv(self.commands['snum'])
        if not val['data'] or val['retcode']:
            return False
        sn = val['data'].split('VAL:')[1]
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
        for com in ['VMON','IMON','STAT']:
            for ch in self.channels:
                res = SendRecv(self.commands['read'].format(ch=ch,par=com))
                if res['retcode'] or 'ERR' in res['data']:
                    readings.append[-1]
                    status.append[-1]
                    self.logger.error('Error reading ch %i: %s' % (ch,res['data'].split(',')[1]))
                else:
                    status.append[0]
                    val = res['data'].split(',')[2]
                    readings.append(float(val))
        return {'retcode' : status, 'data' : readings}


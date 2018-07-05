from ControllerBase import LANController
import logging


class cryocon_22c(LANController):
    """
    Cryogenic controller
    """
    def __init__(self, opts):
        self.logger = logging.getLogger(opts.name)
        self._msg_end = '\n'
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
                }
        super().__init__(opts, self.logger)

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
                    if 'SP' in com:
                        resp.append(float(val['data'][:-1])) # strips units
                    elif 'Pwr' in com:
                        resp.append(float(val['data'].replace('%','')))
                    else:
                        resp.append(float(val['data']))
                    stats.append(0)
                except ValueError:
                    resp.append(-1.0)
                    stats.append(-2)
                except Exception as e:
                    self.logger.error('Could not read device! Error: %s' % e)
                    return {'retcode' : -2, 'data' : None}
        return {'retcode' : stats, 'data' : resp}


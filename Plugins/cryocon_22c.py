from Doberman.Controller import LANController
import logging


class cryocon_22c(LANController):
    """
    Cryogenic controller
    """
    def __init__(self, opts):
        self.logger = logging.getLogger(__name__)
        self.__msg_end = '\n'
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
        super().__init__(opts)

    def checkController(self):
        val = self.SendRecv(self.commands['identify'])
        if val['retcode']:
            self.logger.error('Could not check controller identity')
            return -1
        self.logger.debug('Device answered %s' % val['data'])
        try:
            mfg, model, srl, fw = val['data'].split(',')
        except ValueError:
            self.logger.error('Controller didn\'t send expected response: %s' % val['data'])
            return -2
        if mfg != 'Cryo-con' and model != '22C':
            self.logger.error('Didn\'t connect to the correct device? Mfg %s, model %s' % (mfg, model))
            return -2
        else:
            self.SendRecv(self.commands['SetTempAUnits'])
            self.SendRecv(self.commands['SetTempBUnits'])
            self.logger.info('Connected to controller successfully')
            return 0

    def Readout(self):
        vals = []
        stats = []
        for com in ['getTempA','getTempB','getSP1','getSP2','getLp1Pwr','getLp2Pwr']:
            val = self.SendRecv(self.commands[com])
            if val['retcode']:
                resp.append(-1)
                stats.append(-1)
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
        return {'retcode' : stats, 'data' : vals}


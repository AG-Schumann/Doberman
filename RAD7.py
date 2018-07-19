from ControllerBase import SerialController
import logging


class RAD7(SerialController):
    """
    RAD7
    """
    def __init__(self, opts):
        self.logger = logging.getLogger(opts.name)
        self._msg_end = '\r\n'
        self._msg_start = ''
        self.commands = {'read' : 'SPECIAL STATUS',
                }
        super().__init__(opts, logger)

    def isThisMe(self, dev):
        return False

    def Readout(self):
        """
        I hate this so much
        """
        resp = self.SendRecv(self.commands['read'])
        if not resp['data'] or resp['retcode']:
            return resp
        pieces = resp['data'].split()
        i = 0
        j = 0
        cycle = int(pieces[2])

        if pieces[3] == 'Idle':
            status = 1
        elif pieces[3] == 'Live':
            status = 0
        else:
            status = -1

        if pieces[4] == 'Sniff':
            mode = 0
            i = 1
        elif pieces[4][:-8] == 'Normal':
            mode = 1
        else:
            mode = -1

        counts = int(pieces[5+i])
        activity, activity_err = map(float,pieces[9+i].split('+-'))

        temperature = float(pieces[11+i][:-2])
        humidity_str = pieces[12+i]
        try:
            humidity = int(humidity[3:5])
        except ValueError:
            j = 1
            humidity = int(pieces[13+i][:-1])
        battery = float(pieces[13+i+j][2:6])
        pump = int(pieces[15+i+j][:-2])
        HV = int(pieces[16+i+j][3:7])
        dutycycle = int(pieces[17+i+j][:-1])
        leakage = int(pieces[19+i+j])
        signal = float(pieces[20+i+j][2:6])

        data = [cycle, status, mode, counts, activity, activity_err, temperature,
                humidity, battery, pump, HV, dutycycle, leakage, signal]
        return {'retcode' : [0]*len(data), 'data' : data}

    def ExecuteCommand(self, command):
        return


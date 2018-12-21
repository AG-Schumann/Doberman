from ControllerBase import SerialController
import re  # EVERYBODY STAND BACK xkcd.com/207


class dg1022(SerialController):
    """
    Pulser for the LED calibration
    """
    accepted_commands = [
            'start led: starts the pulser for the calibration',
            'stop led: stops the pulser'
            ]

    def __init__(self, opts):
        super().__init__(opts)

    def isThisMe(self, dev):
        cmd = '*idn?'
        info = self.SendRecv(cmd, dev)
        try:
            if info['data'].decode().split(',')[1] == 'DG1022':
                return True
            return False
        except:
            return False

    def start(self):
        commands = [
                'output off',
                'system:rwlock',
                'system:clksrc int',
                'frequency %f' % self.frequency,
                'function:square:dcycle %f' % self.width*self.frequency,
                'voltage:unit vpp',
                'voltage:high %f' % self.amplitude,
                'voltage:low 0',
                'phase 0',
                'output:polarity norm',
                'output:sync on',
                'output on'
        ]
        for command in commands:
            if self.SendRecv(command)['retcode']:
                self.logger.error('Error sending command \'%s\'' % command)
                self.stop()
                return
        return

    def stop(self):
        commands = [
                'output off',
                'system:local'
        ]
        for command in commands:
            self.SendRecv(command)

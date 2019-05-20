from SensorBase import SerialSensor
import re  # EVERYBODY STAND BACK xkcd.com/207


class pulser(SerialSensor):
    """
    Pulser for the LED calibration
    """
    accepted_commands = [
            'start led: starts the pulser for the calibration',
            'stop led: stops the pulser'
            ]

    def SetParameters(self):
        self.reading_patterns = {}
        self.command_patterns = {
                'start led' : self.start,
                'stop led' : self.stop
                }
        return

    def isThisMe(self, dev):
        cmd = '*idn?'
        info = self.SendRecv(cmd, dev)
        try:
            return info['data'].decode().split(',')[1] == 'DG1022'
        except:
            return False

    def start(self, *args):
        for command in self.led_start_commands:
            if self.SendRecv(command)['retcode']:
                self.logger.error('Error sending command \'%s\'' % command)
                self.stop()
                return
        return

    def stop(self, *args):

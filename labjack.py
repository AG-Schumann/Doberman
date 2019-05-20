from SensorBase import Sensor
import u12
import time


class labjack(Sensor):
    """
    Labjack U12. Has a very different interface, so we don't inherit from more
    than Sensor
    """
    def SetParameters(self):
        self.analog_channels = list(map(int, self.analog_channels))
        self.digital_channels = list(map(int, self.digital_channels))

        self.then = 0
        self.read_args = {'idNum' : None, 'demo' : 0}

    def OpenDevice(self):
        self._device = u12.U12()
        return True

    def Setup(self):
        self.then = self._device.eCount(resetCounter=1)['ms']

    def NTCtoTemp(self, val):
        resistance = self.rc[0]*val/(self.rc[1] + self.rc[2]*val)
        temp = sum([v*resistance**i for i,v in enumerate(self.tc)])
        return temp

    def AddToSchedule(self, reading_name=None, command=None, callback=None):
        """
        The labjack doesn't have a SendRecv interface, so we can't
        rely on the framework for other sensors here. As the labjack
        doesn't accept external commands, we can combine the functionality of
        `ReadoutScheduler`, `AddToSchedule` (the only thing actually called from
        the owning Plugin), `_ProcessReading`, and `ProcessOneReading`
        """
        value = None
        retcode = 0
        if reading_name == 'vbias':  # bias voltage
            v = self._device.eAnalogIn(channel=2, gain=0, **self.read_args)
            value = v['voltage']
        elif reading_name == 'box_temp':  # glovebox temperature
            v = self._device.eAnalogIn(channel=0, gain=0, **self.read_args)
            value = self.NTCtoTemp(v['voltage'])
        elif reading_name == 'mv_freq':  # MV frequency
            count = self._device.eCount(resetCounter=1)
            counts = count['count']
            now = count['ms']
            if now == self.then:
                value = -1
                retcode = -1
            else:
                value = counts/(now - self.then)*1000
                self.then = now
        elif reading_name == 'valve_sens':  # valve sensors
            v = self._device.eDigitalIn(channel=0, readD=0, **self.read_args)
            value = v['state']
        elif reading_name == 'valve_state':  # nitrogen valve state
            v = self._device.eDigitalIn(channel=1, readD=0, **self.read_args)
            value = v['state']
        elif reading_name == 'levelmeter':
            v = self._device.eAnalogIn(channel=6, gain=0, **self.read_args)
            value = v['voltage']
        callback(reading_name, value, retcode)

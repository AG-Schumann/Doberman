from ControllerBase import Controller
import u12
import logging
import time


class labjack(Controller):
    """
    Labjack U12. Has a very different interface, so we don't inherit from more
    than Controller
    """
    def __init__(self, opts):
        self.name = opts['name']
        for k, v in opts.items():
            setattr(self, k, v)
        self.analog_channels = list(map(int, self.analog_channels))
        self.digital_channels = list(map(int, self.digital_channels))
        self.logger = logging.getLogger(opts['name'])
        self._device = u12.U12()

        self.then = 0
        self.read_args = {'idNum' : None, 'demo' : 0}
        self._getControl()

    def NTCtoTemp(self, val):
        # rc (old) = [5 10e3 8.181e-6 11.67e-6 1000]
        # rc (simplified) = [10 5.1167 -1.08181]
        # tc = [77.69 -9.562 0.545 -0.1183]
        resistance = self.rc[0]*val/(self.rc[1] + self.rc[2]*val)
        #resistance = val/(((self.rc[0]-val)/self.rc[1])-\
        #        (self.rc[2]*val)+self.rc[3])/self.rc[4]
        temp = sum([v*resistance**i for i,v in enumerate(self.tc)])
        return temp

    def _getControl(self):
        self.then = self._device.eCount(resetCounter=1)['ms']
        return

    def AddToSchedule(self, reading_index=None, command=None, callback=None):
        """
        The labjack doesn't have a SendRecv interface, so we can't
        rely on the framework for other controllers here. As the labjack
        doesn't accept external commands, we can combine the functionality of
        `ReadoutScheduler`, `AddToSchedule` (the only thing actually called from
        the owning Plugin), `_ProcessReading`, and `ProcessOneReading`
        """
        if index == 0:  # bias volate
            v = self._device.eAnalogIn(channel=2, gain=0, **self.read_args)
            value = v['voltage']
            retcode = 0
        elif index == 1:  # glovebox temperature
            v = self._devide.eAnalogIn(channel=0, gain=0, **self.read_args)
            value = self.NTCtoTemp(v['voltage'])
            retcode = 0
        elif index == 2:  # MV frequency
            count = self._device.eCount(resetCounter=1)
            counts = count['count']
            now = count['ms']
            if now == self.then:
                value = -1
                retcode = -1
            else:
                value = counts/(now - self.then)*1000
                self.then = now
                retcode = 0
        elif index == 3:  # valve sensors
            v = self._device.eDigitalIn(channel=0, readD=0, **self.read_args)
            value = v['state']
            retcode = 0
        elif index == 4:  # nitrogen valve state
            v = self._device.eDigitalIn(channel=1, readD=0, **self.read_args)
            value = v['state']
            retcode = 0
        callback((index, time.time(), value, retcode))

    def Readout(self):
        voltage = [None]*len(self.analog_channels)
        overvolt = [None]*len(self.analog_channels)
        state = [None]*len(self.digital_channels)

        for ch in self.analog_channels:
            v = self._device.eAnalogIn(channel=ch, gain=0, **self.read_args)
            voltage[ch] = v['voltage']
            overvolt[ch] = v['overVoltage']
        for ch in self.digital_channels:
            v = self._device.eDigitalIn(channel=ch, readD=0, **self.read_args)
            state[ch] = v['state']

        count = self._device.eCount(resetCounter=1)
        counts = count['count']
        now = count['ms']
        status = [0,0,0,0,0]
        if now == self.then:
            freq = -1
            status[2] = -1
        else:
            freq = counts/(now - self.then)*1000
            self.then = now
        data = [voltage[2], self.NTCtoTemp(voltage[0]), freq, state[0], state[1]]

        return {'retcode' : status, 'data' : data}


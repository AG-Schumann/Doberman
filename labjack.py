from SensorBase import Sensor
import u12
from functools import partial


class labjack(Sensor):
    """
    Labjack U12. Has a very different interface, so we don't inherit from more
    than Sensor
    """
    def SetParameters(self):
        self.then = 0
        self.read_args = {'idNum' : None, 'demo' : 0}
        self.reading_commands = dict(zip(self.reading_names,
                                         self.reading_names))

    def OpenDevice(self):
        self._device = u12.U12()
        self.generic_read = {
                'analog' : self.AnalogRead,
                'digital' : self.DigitalRead,
                'counter' : self.CounterRead,
                }
        return True

    def Setup(self):
        self.then = self._device.eCount(resetCounter=1)['ms']

    def AnalogRead(self, channel):
        return self._device.eAnalogIn(channel=channel, gain=0,
                **self.read_args)['voltage']

    def DigitalRead(self, channel):
        return self._device.eDigitalIn(channel=channel, readD=0,
                **self.read_args)['state']

    def CounterRead(self, *args):
        count = self._device.eCount(resetCounter=1)
        return count['counts'], count['ms']

    def NTCtoTemp(self, val):
        resistance = self.rc[0]*val/(self.rc[1] + self.rc[2]*val)
        temp = sum([v*resistance**i for i,v in enumerate(self.tc)])
        return temp

    def ProcessOneReading(self, name, data):
        if name == 'mv_freq':  # bias voltage
            counts, now = data
            if now == self.then:
                return -1
            val = counts/(now - self.then)*1000
            self.then = now
            return val
        if name == 'box_temp':
            return self.NTCtoTemp(data)
        return data

    def SendRecv(self, message, dev):
        """
        We use "message" here to mean the reading name
        """
        ret = {'retcode' : 0, 'data' : None}
        try:
            temp = self.reading_templates[message]
            ret['data'] = self.generic_read[temp['type']](temp['channel'])
        except Exception as e:
            self.logger.error(f'Caught a {type(e)}: {e}')
            ret['retcode'] = -2
        return ret

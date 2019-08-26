import Doberman
import numpy as np


class FeedbackController(Doberman.Reading):
    """
    Class to handle feedback and control
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dtype = [('timestamp', np.float64), ('value', np.float64)]
        self.buffer = np.zeros(0, dtype=self.dtype)

    def UpdateConfig(self):
        doc = self.db.GetReadingSetting(self.sensor_name, self.name)
        self.status = doc['status']
        self.readout_interval = doc['readout_interval']
        gains = doc['pid_settings']
        self.Kp = gains['Kp']
        self.Ki = gains['Ki']
        self.Kd = gains['Kd']
        self.Ti = gains['Ti']
        self.Td = gains['Td']
        self.n_filter = gains['n_filter']
        self.filter_percent = gains['filter_percentiles']
        self.sp = gains['setpoint']
        self.pid_status = gains['status']
        self.target = gains['target_output']
        self.command = gains['command']

    def ResetIntegral(self):
        self.buffer = np.zeros(0, dtype=self.dtype)

    def Process(self, value):  # TODO finish
        value = super().Process(value)
        if self.pid_status == 'offline':
            return value
        if value is not None:
            newbit = np.array([(time.time(), self.sp-value)], dtype=self.dtype)
            self.buffer = np.append(self.buffer, newbit)

        self.logger.debug('Buffer length %i' % len(self.buffer))
        self.logger.debug('Buffer time %.1f' % np.ptp(self.buffer['time']))
        keep_mask = self.buffer['time'][-1] - self.buffer['time'] < self.Ti
        self.buffer = self.buffer[keep_mask]

        if self.n_filter > 0 and len(self.buffer) >= self.n_filter:
            qs = np.nanpercentile(self.buffer['value'], self.filter_percentiles)
            mask = (qs[0] < self.buffer['value']) & (self.buffer['value'] < qs[1])
            b = self.buffer[mask]
        else:
            b = self.buffer

        P = Kp * b[-1]['value']
        self.logger.debug('Proportional term %.2g' % P)
        I = Ki * np.trapz(b['value'], x=b['time'])
        self.logger.debug('Integral term %.2g' % I)
        m = self.buffer['time'][-1] - self.buffer['time'] < self.Td
        if m.sum() > 0:
            D = Kd * np.median(np.gradient(b[m]['value'], b[m]['time']))
        else:
            D = 0
        self.logger.debug('Differential term %.2g' % D)

        if self.status == 'active':
            self.db.LogCommand({'name' : self.target,
                            'by' : 'feedback',
                            'command' : self.command.format(value=P+I+D)})

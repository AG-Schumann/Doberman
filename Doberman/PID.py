import Doberman
import numpy as np
import time

__all__ = 'PIDReading'.split()


class PIDReading(Doberman.Reading):
    """
    Class to handle feedback and control
    """

    def child_setup(self, doc):
        self.dtype = [('timestamp', np.float64), ('value', np.float64)]
        self.buffer = np.zeros(0, dtype=self.dtype)

    def update_child_config(self, doc):
        for k, v in doc['pid'].items():
            setattr(self, k, v)

    def reset_integral(self):
        self.buffer = np.zeros(0, dtype=self.dtype)

    def more_processing(self, value):  # TODO deal with input delay
        super().more_processing(value)
        if self.pid_status == 'offline':
            return
        newbit = np.array([(time.time(), self.sp - value)], dtype=self.dtype)
        self.buffer = np.append(self.buffer, newbit)

        self.logger.debug('Buffer length %i' % len(self.buffer))
        self.logger.debug('Buffer time %.1f' % np.ptp(self.buffer['time']))
        keep_mask = self.buffer['time'][-1] - self.buffer['time'] < self.Ti + self.input_delay
        self.buffer = self.buffer[keep_mask]

        if 0 < self.n_filter <= len(self.buffer):
            qs = np.nanpercentile(self.buffer['value'], self.filter_percentiles)
            mask = (qs[0] < self.buffer['value']) & (self.buffer['value'] < qs[1])
            b = self.buffer[mask]
        else:
            b = self.buffer
        b = b['time'] > self.input_delay  # FIXME

        P = Kp * b[-1]['value']
        self.logger.debug('Proportional term %.2g' % P)
        I = Ki * np.trapz(b['value'], x=b['time'])
        self.logger.debug('Integral term %.2g' % I)
        m = b['time'][-1] - b['time'] < self.Td
        if m.sum() > 0:
            D = Kd * np.median(np.gradient(b[m]['value'], b[m]['time']))
        else:
            D = 0
        self.logger.debug('Differential term %.2g' % D)

        if self.status == 'active':
            self.db.log_command({'name': self.target,
                                 'by': 'feedback',
                                 'command': self.command.format(value=P + I + D)})

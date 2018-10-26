import numpy as np
import logging


class FeedbackController(Plugin):
    """
    Class to handle feedback and control
    """
    def __init__(self, db, name, plugin_paths):
        super().__init__(self, db, name, plugin_paths)

        self.dtype = [('timestamp', np.float64), ('value', np.float64)]
        self.buffer = np.array([], dtype=self.dtype)

    def control(self, setpoint, pid):
        """
        The main PID control function.

        :param pid: a tuple containing the gains (Kp, Ti, Td)

        Trims the buffer to contain the appropriate number of values.

        Returns the control variable
        """
        Kp, Ti, Td = pid
        times = self.buffer['timestamp']
        self.logger.debug('Gains: %2.g %.2g %.2g' % pid)
        self.logger.debug('Buffer length %i' % len(self.buffer))
        self.logger.debug('Buffer time %.1f' % np.ptp(times))
        keep_mask = np.nonzero(times[-1] - times <= Ti)[0]
        if keep_mask[0] == 0:
            self.logger.debug('Buffer not long enough for %.2g worth of data!' % Ti)
        self.buffer = self.buffer[keep_mask]

        Ki = Kp/Ti if Ti != 0 else 0
        Kd = Kp*Td
        e = setpoint - self.buffer['value']
        P = Kp * e[-1]
        self.logger.debug('Proportional term %.2g' % P)
        I = Ki * np.trapz(e, x=self.buffer['timestamp'])
        self.logger.debug('Integral term %.2g' % I)
        if len(e) > 2:
            D = Kd*(np.diff(e,n=1)[-1])/(np.diff(self.buffer['timestamp'],n=1)[-1])
            self.logger.debug('Differential term %.2g' % D)
        else:
            D = 0

        return P + I + D

    def KillTime(self, rundoc):
        feedback = rundoc['feedback']
        if feedback['status'] == 'ON':
            timestamp, value, status = self.controller.FeedbackReadout()
            if status != 0 or value is None:
                pass
            else:
                newbit = np.array((timestamp, value), dtype=self.dtype)
                self.buffer = np.append(self.buffer, newbit)
                try:
                    u = self.control(feedback['setpoint'], feeback['gains'])
                except:
                    pass
                else:
                    do_something_with(u)
            time.sleep(feedback['frequency'])
        self.HandleCommands()


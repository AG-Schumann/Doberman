from BasePlugin import Plugin
import numpy as np
from datetime import datetime


class FeedbackController(Plugin):
    """
    Class to handle feedback and control
    """
    def __init__(self, db, name, plugin_paths):
        super().__init__(self, db, name, plugin_paths)

        self.dtype = [('timestamp', np.float64), ('value', np.float64)]
        self.buffer = np.array([], dtype=self.dtype)

    def control(self, doc):
        """
        The main PID control function.

        :param doc: the feedback field from the config document

        Trims the buffer to contain the appropriate number of values, and
        might low-pass filter it

        Returns the control variable
        """
        Kp, Ti, Td = doc['gains']
        times = self.buffer['timestamp']
        self.logger.debug('Gains: %2.g %.2g %.2g' % doc['gains'])
        self.logger.debug('Buffer length %i' % len(self.buffer))
        self.logger.debug('Buffer time %.1f' % np.ptp(times))
        t_start = times[-1] - Ti
        keep_mask = np.nonzero(times[-1] - times <= Ti)[0]
        if keep_mask[0] == 0:
            self.logger.debug('Buffer not long enough for %.2g sec worth of data!' % Ti)
            # pull enough data to fill in what we don't have
            # (plus a bit extra so we can interpolate)
            start_time = datetime.fromtimestamp(t_start - 60)
            end_time = datetime.fromtimestamp(times[0])

            b = self.db.GetData(self.name, start_time=start_time,
                    data_index=doc['data_index'], end_time=end_time)
            b = np.array(b, dtype=self.dtype)
            self.buffer = np.append(b, self.buffer)
            if b[0]['timestamp'] > t_start:
                self.logger.debug('Database doesn\'t have enough data either')
                # still not enough data, just take what we have
            else:
                # more than we need, interpolate to find the last point we actually want
                v = np.interp(t_start, self.buffer['timestamp'], self.buffer['value'])
                first_point = np.array([(t_start, v)], dtype=self.dtype)
                keep_mask = t_start < self.buffer['timestamp']
                self.buffer = np.append(first_point, self.buffer[keep_mask])
        else:
            self.buffer = self.buffer[keep_mask]

        if doc['n_filter'] > 0 and len(self.buffer) >= doc['n_filter']:
            qs = np.nanpercentile(self.buffer['value'], doc['filter_percentiles'])
            mask = (qs[0] < self.buffer['value']) & (self.buffer['value'] < qs[1])
            b = self.buffer[mask]
        else:
            b = self.buffer

        Ki = Kp/Ti if Ti != 0 else 0
        Kd = Kp*Td
        e = doc['setpoint'] - b['value']
        P = Kp * e[-1]
        self.logger.debug('Proportional term %.2g' % P)
        I = Ki * np.trapz(e, x=b['timestamp'])
        self.logger.debug('Integral term %.2g' % I)
        if len(e) > 1:
            D = Kd * np.gradient(e, b['timestamp'])[-1]
            self.logger.debug('Differential term %.2g' % D)
        else:
            D = 0

        return P + I + D

    def KillTime(self, configdoc):
        feedback = configdoc['feedback']
        if feedback['status'] == 'ON':
            timestamp, value, status = self.controller.FeedbackReadout()
            if status != 0 or value is None:
                pass
            else:
                newbit = np.array([(timestamp, value)], dtype=self.dtype)
                self.buffer = np.append(self.buffer, newbit)
                try:
                    u = self.control(feedback)
                except:
                    pass
                else:
                    doc = {'name' : feedback['controller'], 'by' : 'feedback',
                           'logged' : datetime.now(),
                           'command' : feedback['command'].format(value=u)}
                    self.db.InsertIntoDatabase('logging','commands', doc)
            time.sleep(feedback['frequency'])
        self.HandleCommands()


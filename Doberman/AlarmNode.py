import Doberman
import time


class AlarmNode(Doberman.Node):
    """
    An empty base class to handle database access
    """

    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.set_sensor_setting = kwargs['set_sensor_setting']
        self.description = kwargs['description']
        self.device = kwargs['device']
        self._log_alarm = kwargs['log_alarm']
        self.max_reading_delay = kwargs['max_reading_delay']
        self.escalation_config = kwargs['escalation_config']
        self.escalation_level = 0
        self.auto_silence_duration = kwargs['silence_duration']
        self.silence_duration_cant_send = kwargs['silence_duration_cant_send']
        self.messages_this_level = 0
        self.hash = None
        self.sensor_config_needed = ['readout_interval']

    def escalate(self):
        """
        Do we escalate? This function decides this
        """
        if self.hash is None:
            self.logger.error('How are you escalating if there is no active alarm?')
            return
        base_level = self.config['alarm_level']
        total_level = base_level + self.escalation_level
        if self.messages_this_level >= self.escalation_config[total_level]:
            self.logger.warning((f'{self.name} at level {base_level}+{self.escalation_level} '
                                 f'for {self.messages_this_level} messages, time to escalate (hash {self.hash})'))
            max_total_level = len(self.escalation_config) - 1
            self.escalation_level = min(max_total_level - base_level, self.escalation_level + 1)
            self.messages_this_level = 0  # reset count so we don't escalate again immediately
        else:
            self.logger.warning((f'{self.name} at level {base_level}+{self.escalation_level} '
                                 f'for {self.messages_this_level} messages, need {self.escalation_config[total_level]} '
                                 f'to escalate'))
    def reset_alarm(self):
        """
        Resets the cached alarm state
        """
        self.set_sensor_setting(self.input_var, 'alarm_is_triggered', False)
        if self.hash is not None:
            self.logger.info(f'{self.name} resetting alarm (hash {self.hash})')
            self.hash = None
            self.messages_this_level = 0
        self.escalation_level = 0

    def log_alarm(self, msg, ts=None):
        """
        Let the outside world know that something is going on
        """
        self.set_sensor_setting(self.input_var, 'alarm_is_triggered', True)
        # Only send message if pipeline is silenced at base_level or above, 
        # or if it is silenced at level -1 (universal)
        if not self.is_silent or -1 < self.pipeline.silenced_at_level < self.config['alarm_level']:
            self.logger.warning(msg)
            if self.hash is None:
                self.hash = Doberman.utils.make_hash(ts or time.time(), self.pipeline.name)
                self.alarm_start = ts or time.time()
                self.logger.warning(f'{self.pipeline.name} beginning alarm with hash {self.hash}')
            self.escalate()
            level = self.config['alarm_level'] + self.escalation_level
            try:
                self._log_alarm(level=level,
                                message=msg,
                                pipeline=self.pipeline.name,
                                _hash=self.hash)
                # self-silence if the message was successfully sent
                self.pipeline.silence_for(self.auto_silence_duration[level], self.config['alarm_level'])
                self.messages_this_level += 1
            except Exception as e:
                self.logger.error(f"Exception sending alarm: {type(e)}, {e}.")
                self.pipeline.silence_for(self.silence_duration_cant_send, self.config['alarm_level'])
        else:
            self.logger.debug(msg)
           
    def shutdown(self):
        self.set_sensor_setting(self.input_var, 'alarm_is_triggered', False)

        
class CheckRemoteHeartbeatNode(Doberman.Node):
    """
    A node that checks if a remote heartbeat has been updated recently and otherwise sends alarms.
    """

    def setup(self, **kwargs):
        super().setup(**kwargs)
        self._log_alarm = kwargs['log_alarm']

    def log_alarm(self, msg, prd):
        """
        Let the outside world know that something is going on
        """
        if not self.is_silent:
            self.logger.warning(msg)
            try:
                self._log_alarm(message=msg,
                                pipeline=self.pipeline.name,
                                prot_rec_dict=prd, )
                # self-silence if the message was successfully sent
                self.pipeline.silence_for(int(self.config.get('silence_duration', 300)), -1)
            except Exception as e:
                self.logger.error(f"Exception sending alarm: {type(e)}, {e}.")
                self.pipeline.silence_for(int(self.config.get('silence_duration', 300)), -1)
        else:
            self.logger.debug(msg)

    def process(self, package):
        directory = self.config.get('directory', '/scratch')
        experiment_name = self.config.get('experiment_name')
        with open(f'{directory}/remote_hb_{experiment_name}', 'r') as f:
            timestamp, numbers_string = f.read().split('\n', maxsplit=1)
            numbers = numbers_string.strip().split(',')
            dt = time.time() - int(timestamp)
            if dt > int(self.config.get('max_delay_sms', 3 * 60)):  # default 3 minutes for sms
                msg = f"The hypervisor of {experiment_name} hasn't had a heartbeat for {round(dt / 60)} minutes."
                prd = {'sms': numbers}
                if dt > int(self.config.get('max_delay_phone', 10 * 60)):  # and 10 minutes for phone + sms
                    prd['phone'] = numbers
                self.log_alarm(msg, prd)
            else:
                self.logger.debug(f'Last remote heartbeat from {experiment_name} was {int(dt)} seconds ago.')


class TriggeredAlarmsNode(Doberman.Node):

    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.get_sensor_setting = kwargs['get_sensor_setting']
        self.distinct = kwargs['distinct']

    def process(self, package):
        sensors_to_check = self.config.get('sensors_to_check', 'any')
        if sensors_to_check == 'any':
            sensor_list = self.distinct('sensors', 'name')
        elif isinstance(sensors_to_check, list):
            sensor_list = sensors_to_check
        else:
            self.logger.error('invalid option sensors_to_check: must be "any" or a list of sensor names.')
            return 0
        for sensor in sensor_list:
            if status := self.get_sensor_setting(sensor, 'alarm_is_triggered'):
                if not isinstance(status, dict):  # get_sensor_setting returns whole doc if field doesn't exist
                    self.logger.debug(f'{sensor} in alarm state')
                    return 1
        return 0


class DeviceRespondingBase(AlarmNode):
    """
    A base class to check if sensors are returning data
    """

    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.accept_old = True
        self.sensor_config_needed += ['alarm_level']

    def process(self, package):
        if (dt := ((now := time.time()) - package['time'])) > self.config['readout_interval'] + self.max_reading_delay:
            self.log_alarm(
                (f'Is {self.device} responding correctly? No new value for '
                 f'{self.description} has been seen in {int(dt)} seconds'),
                now)
        else:
            self.reset_alarm()
        return None


class DeviceRespondingInfluxNode(DeviceRespondingBase, Doberman.InfluxSourceNode):
    pass


class DeviceRespondingSyncNode(DeviceRespondingBase, Doberman.SensorSourceNode):
    pass


class SimpleAlarmNode(Doberman.BufferNode, AlarmNode):
    """
    A simple alarm. Checks a value against the thresholds stored in its sensor document.
    Then endpoints of the interval are assumed to represent acceptable values, only
    values outside are considered 'alarm'.
    """

    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.strict = True
        self.sensor_config_needed += ['alarm_thresholds', 'alarm_recurrence', 'alarm_level']

    def load_config(self, doc):
        doc.update(length=doc['alarm_recurrence'])
        super().load_config(doc)

    def process(self, packages):
        values = [p[self.input_var] for p in packages]
        low, high = self.config['alarm_thresholds']
        is_ok = [low <= v <= high for v in values]
        if all(is_ok):
            # we're no longer in an alarmed state so reset the hash
            self.reset_alarm()
        elif any(is_ok):
            # at least one value is in an acceptable range
            pass
        else:
            msg = f'Alarm for {self.description}. '
            try:
                toohigh = values[-1] >= high  # (Or low)
                msgval = Doberman.utils.sensible_sig_figs(values[-1], low, high)
                msgthreshold = Doberman.utils.sensible_sig_figs(high if toohigh else low, low, high)
                msg += f'{msgval} is {"above" if toohigh else "below"} '
                msg += f'the threshold {msgthreshold}.'
            except ValueError:
                # Sometimes hit a corner case (eg low=high)
                msg += f'{values[-1]:.3g} is outside allowed range of'
                msg += f' {low:.3g} to {high:.3g}.'
            self.log_alarm(msg, packages[-1]['time'])


class IntegerAlarmNode(Doberman.BufferNode, AlarmNode):
    """
    Integer status quantities are a fundamentally different thing from physical values.
    It makes sense to process them differently. The thresholds should be stored as [value, message] pairs.
    """

    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.strict = True
        self.sensor_config_needed += ['alarm_values', 'alarm_level', 'alarm_recurrence']

    def load_config(self, doc):
        doc.update(length=doc['alarm_recurrence'])
        super().load_config(doc)

    def process(self, packages):
        values = [int(p[self.input_var]) for p in packages]
        bad_values = [int(bv) for bv in list(self.config['alarm_values'].keys())]
        is_ok = [v not in bad_values for v in values]
        if all(is_ok):
            # we're no longer in an alarmed state so reset the hash
            self.reset_alarm()
        elif any(is_ok):
            # at least one value is in an acceptable range
            pass
        else:
            for v in set(values):
                self.log_alarm(f'Alarm for {self.description}: {self.config["alarm_values"][str(v)]}')
                break


class BitmaskIntegerAlarmNode(AlarmNode):
    """
    Sometimes the integer represents a bitmask. The threshold config for this
    looks different:
    [
        (bitmask, value, msg),
        (0x3, 1, "msg"),
    }
    This means you look at bits[0] and [1], and if they equal 1 then you send "msg"
    (meaning bit[0]=1 and bit[1]=0). Both bitmask and value are assumed to be in **hex**
    and will be integer-cast before use (mask = int(mask, base=16))
    """

    def process(self, package):
        value = int(package[self.input_var])
        alarm_msg = []
        for mask, target, msg in self.config['alarm_thresholds']:
            mask = int(mask, base=16)
            target = int(target, base=16)
            if value & mask == target:
                alarm_msg.append(msg)
        if len(alarm_msg):
            self.log_alarm(f'Alarm for {self.description}: {",".join(alarm_msg)}')

            
class TimeSinceAlarmNode(AlarmNode):
    """
    Checks whether a measurement was at the alarm_value for more than the max_duration.
    Useful to answer questions like 'Has this valve been open for too long?'

    Setup params:
    None

    Runtime params:
    :param alarm_value: value that should trigger the alarm
    :param max_duration: maximal duration for which the value is allowed to be at alarm_value before logging an alarm
    :param alarm_level: base level of the alarm (note we don't take the one from the sensor since this is reserved for
                        the IntegerAlarmNode (SimpleAlarmNode)).
    """

    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.time_since = 0
        self.last_checked = time.time()

    def process(self, package):
        value = int(package[self.input_var])
        alarm_value = int(self.config.get('alarm_value'))
        tmax = int(self.config.get('max_duration'))
        if value == alarm_value:
            now = time.time()
            self.time_since += (now - self.last_checked)
            self.last_checked = now
        else:
            self.time_since = 0
            self.last_checked = time.time()
        if self.time_since > tmax:
            self.config['alarm_level'] = int(self.config['alarm_level'])
            self.log_alarm(f'Alarm for {self.description}: value is at {alarm_value} for more than '
                           f'{int(self.time_since)} seconds.')

import Doberman


class AlarmNode(Doberman.Node):
    """
    An empty base class to handle database access
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.description = kwargs['description']
        self.sensor = kwargs['sensor']
        self._log_alarm = kwargs['log_alarm']
        self.escalation_config = kwargs['escalation_config']
        self.escalation_level = 0
        self.base_level = kwargs['base_level']
        self.auto_silence_duration = kwargs.get('silence_duration', 5*60)
        self.alarm_start = None
        self.hash = None

    def escalate(self):
        """
        Do we escalate? This function decides this
        """
        if self.alarm_start is None:
            # not sure how we got here, but there's nothing to escalate
            return
        time_since_start = time.time() - self.alarm_start
        if time_since_start > self.escalation_config[max(self.base_level + self.escalation_level, len(self.escalation_config)-1)]:
            self.logger.warning((f'{self.name} at level {self.base_level}/{self.escalation_level} '
                f'since {time_since_start//60} minutes, time to escalate (hash {self.hash})'))
            self.escalation_level += 1
            self.escalation_level = min(len(self.escalation_config) - self.base_level - 1, self.escalation_level)
            self.alarm_start = time.time()

    def reset_alarm(self):
        """
        Resets the cached alarm state
        """
        if self.hash is not None:
            self.logger.info(f'{self.name} resetting alarm f{self.hash}')
            self.hash = None
        self.escalation_level = 0

    def log_alarm(self, msg, ts=None):
        """
        Let the outside world know that something is going on
        """
        if not self.is_silent:
            self.logger.debug(msg)
            if self.hash is None:
                self.hash = Doberman.utils.make_hash(bytes(str(ts or time.time())), bytes(self.pipeline.name))
                self.alarm_start = ts or time.time()
                self.logger.warning(f'{self.name} beginning alarm with hash {self.hash}')
            self.escalate()
            self._log_alarm(msg, self.pipeline.name, self.hash, self.escalation_level)
            self.pipeline.silence_for(self.auto_silence_duration)
        else:
            self.logger.error(msg)

class SensorRespondingAlarm(Doberman.InfluxSourceNode, AlarmNode):
    """
    A simple alarm that makes sure the spice is flowing
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.late_counter = 0
        self.late_threshold = 3

    def get_package(self):
        try:
            ret = super().get_package()
            self.late_counter = 0
            self.reset_alarm()
            return ret
        except ValueError as e:
            self.late_counter += 1
            if self.late_counter >= self.late_threshold:
                self.log_alarm(f"Is {self.sensor} responding correctly? We haven't gotten a new value recently")
            raise

    def process(self, package):
        if (now := time.time()) - package['time'] > 2*self.config['readout_interval']:
            self.late_counter += 1
            if self.late_counter > self.late_threshold:
                self.log_alarm(
                    (f'Is {self.sensor} responding correctly? Time to the last value for {self.input_var} is '
                         f'{now-package["time"]:.1f}s rather than {self.config["readout_interval"]}'),
                    package['time'])
                self.late_counter = 0
        else:
            self.late_counter = 0
            self.reset_alarm()

class SimpleAlarmNode(Doberman.BufferNode, AlarmNode):
    """
    A simple alarm
    """
    def process(self, packages):
        values = [p[self.input_var] for p in packages]
        low, high = self.config['alarm_thresholds']
        is_ok = [low <= v <= high for v in values]
        if any(is_ok):
            # at least one value is in an acceptable range
            pass
        elif all(is_ok):
            # we're no longer in an alarmed state so reset the hash
            self.reset_alarm()
        else:
            msg = (f'Alarm for {self.description} ({self.input_var}) - {values[-1]} '
                   f'is outside the allowed range ({low},{high})')
            self.log_alarm(msg, packages[-1]['time'])


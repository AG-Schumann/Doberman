import Doberman
import time


class AlarmNode(Doberman.Node):
    """
    An empty base class to handle database access
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.description = kwargs['description']
        self.device = kwargs['device']
        self._log_alarm = kwargs['log_alarm']
        self.escalation_config = kwargs['escalation_config']
        self.escalation_level = 0
        self.base_level = kwargs['alarm_level']
        self.auto_silence_duration = kwargs['silence_duration']
        self.messages_this_level = 0
        self.hash = None

    def escalate(self):
        """
        Do we escalate? This function decides this
        """
        if self.hash is None:
            self.logger.debug('How are you escalating if there is no active alarm?')
            return
        total_level = self.base_level + self.escalation_level
        if self.messages_this_level > self.escalation_config[total_level]:
            self.logger.warning((f'{self.name} at level {self.base_level}/{self.escalation_level} '
                f'for {self.messages_this_level} messages, time to escalate (hash {self.hash})'))
            max_total_level = len(self.escalation_config)-1
            self.escalation_level = min(max_total_level - self.base_level, self.escalation_level + 1)
            self.messages_this_level = 0  # reset count so we don't escalate again immediately
        else:
            self.logger.info((f'{self.name} at level {self.base_level}/{self.escalation_level} '
                    f'for {self.messages_this_level} messages, need {self.escalation_config[total_level]} to escalate'))

    def reset_alarm(self):
        """
        Resets the cached alarm state
        """
        if self.hash is not None:
            self.logger.info(f'{self.name} resetting alarm {self.hash}')
            self.hash = None
            self.messages_this_level = 0
        self.escalation_level = 0

    def log_alarm(self, msg, ts=None):
        """
        Let the outside world know that something is going on
        """
        if not self.is_silent or self.pipeline.silenced_at_level < self.base_level:
            self.logger.debug(msg)
            if self.hash is None:
                self.hash = Doberman.utils.make_hash(ts or time.time(), self.pipeline.name)
                self.alarm_start = ts or time.time()
                self.logger.warning(f'{self.name} beginning alarm with hash {self.hash}')
            self.escalate()
            level = self.base_level + self.escalation_level
            self._log_alarm(level=level,
                            message=msg,
                            pipeline=self.pipeline.name,
                            _hash=self.hash)
            self.pipeline.silence_for(self.auto_silence_duration[level], self.base_level)
            self.messages_this_level += 1
        else:
            self.logger.error(msg)

class DeviceRespondingAlarm(Doberman.InfluxSourceNode, AlarmNode):
    """
    A simple alarm that makes sure the spice is flowing
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.late_counter = 0
        self.late_threshold = 3 # TODO config-ize
        self.accept_old = False

    def reset_alarm(self):
        super().reset_alarm()
        self.late_counter = 0

    def get_package(self):
        try:
            ret = super().get_package()
            self.reset_alarm()
            return ret
        except ValueError as e:
            self.late_counter += 1
            if self.late_counter > self.late_threshold:
                self.log_alarm(f"Is {self.device} responding correctly? {self.late_counter} values are either missing or late")
                self.late_counter = 0
            raise

    def process(self, package):
        if (now := time.time()) - package['time'] > 2*self.config['readout_interval']:
            self.late_counter += 1
            if self.late_counter > self.late_threshold:
                self.log_alarm(
                    (f'Is {self.device} responding correctly? Time to the last value for {self.input_var} is '
                         f'{now-package["time"]:.1f}s rather than {self.config["readout_interval"]}'),
                    package['time'])
                self.late_counter = 0 # not an actual reset, just delaying the next message
        else:
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


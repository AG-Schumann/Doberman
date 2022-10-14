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
            if self._log_alarm(level=level,
                               message=msg,
                               pipeline=self.pipeline.name,
                               _hash=self.hash):
                # only self-silence if the message was successfully sent
                self.pipeline.silence_for(self.auto_silence_duration[level], self.base_level)
                self.messages_this_level += 1
        else:
            self.logger.error(msg)

class DeviceRespondingBase(AlarmNode):
    """
    A base class to check if sensors are returning data
    """
    def setup(self, **kwargs):
        super().setup(**kwargs)
        self.accept_old = True

    def process(self, package):
        # the 2 is a fudge factor
        dt_max = (2 + self.config['alarm_recurrence']) * self.config['readout_interval']
        if (dt := ((now := time.time()) - package['time'])) > dt_max:
            self.log_alarm(
                (f'Is {self.device} responding correctly? No new value for '
                 f'{self.input_var} has been seen in {int(dt)} seconds'),
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


class IntegerAlarmNode(AlarmNode):
    """
    Integer status quantities are a fundamentally different thing from physical values.
    It makes sense to process them differently. The thresholds should be stored as [value, message] pairs.
    """
    def process(self, package):
        value = int(package[self.input_var])
        for v, msg in self.config['alarm_values'].items():
            if value == int(v):
                self.log_alarm(f'Alarm for {self.description}: {msg}')
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


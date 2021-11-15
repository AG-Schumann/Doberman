import threading
import time

__all__ = 'Reading MultiReading'.split()


class Reading(threading.Thread):
    """
    A thread responsible for scheduling readouts and processing the returned data.
    """

    def __init__(self, **kwargs):
        threading.Thread.__init__(self)
        self.db = kwargs['db']
        self.event = kwargs['event']
        self.name = kwargs['reading_name']
        self.logger = kwargs.pop('logger')
        self.cv = threading.Condition()
        self.sensor_process = kwargs['sensor'].process_one_reading
        self.schedule = kwargs['sensor'].add_to_schedule
        self.setup(self.db.get_reading_setting(name=self.name))

    def run(self):
        self.logger.debug(f'{self.name} Starting')
        while not self.event.is_set():
            loop_top = time.time()
            doc = self.db.get_reading_setting(name=self.name)
            self.update_config(doc)
            if doc['status'] == 'online':
                self.do_one_measurement()
            self.event.wait(loop_top + self.readout_interval - time.time())
        self.logger.debug(f'{self.name} Returning')

    def setup(self, config_doc):
        self.is_int = 'is_int' in config_doc
        self.topic = config_doc['topic']
        self.subsystem = config_doc['subsystem']

    def update_config(self, doc):
        self.readout_interval = doc['readout_interval']
        if 'alarm_thresholds' in doc and len(doc['alarm_thresholds']) == 2:
            self.alarms = doc['alarm_thresholds']
        else:
            self.alarms = (None, None)

    def do_one_measurement(self):
        """
        Asks the sensor for data, unpacks it, and sends it to the database
        """
        func_start = time.time()
        pkg = {}
        failed = False
        self.schedule(reading_name=self.name, retq = (pkg, self.cv))
        with self.cv:
            if self.cv.wait_for(lambda: (len(pkg) > 0 or self.event.is_set()), self.readout_timeout):
                failed = False
            else:
                # timeout expired
                failed = len(pkg) == 0
        if len(pkg) == 0 or failed:
            self.logger.info('Didn\'t get anything from the sensor!')
            return
        try:
            value = self.sensor_process(name=self.name, data=pkg['data'])
        except (ValueError, TypeError, ZeroDivisionError, UnicodeDecodeError, AttributeError) as e:
            self.logger.debug(f'{self.name} got a {type(e)} while processing \'{pkg["data"]}\': {e}')
            value = None
        self.logger.debug(f'{self.name} measured {value}')
        if value is not None:
            value = self.more_processing(value)
            self.send_upstream(value, pkg['time'])
        return

    def more_processing(self, value):
        """
        Does something interesting with the value. Should return a value
        """
        if self.is_int:
            value = int(value)
        return value

    def send_upstream(self, value, timestamp):
        """
        This function sends data upstream to wherever it should end up
        """
        low, high = self.alarms
        self.db.write_to_influx(topic=self.topic, tags={'reading': self.name, 'subsystem': self.subsystem},
                fields={'value': value, 'alarm_low': low, 'alarm_high': high}, timestamp=timestamp)


class MultiReading(Reading):
    """
    A special class to handle sensors that return multiple values for each
    readout cycle (smartec_uti, caen mainframe, etc). This works this way:
    one reading is designated the "primary" and the others are "secondaries".
    Only the primary is actually read out, but the assumption is that the reading
    of the primary also brings the values of the secondary with it. The secondaries
    must have entries in the database but these are "shadow" entries and most of the
    fields will be ignored, the only one mattering is any alarm values. Things like
    "status" and "readout_interval" only use the value of the primary.
    The extra database fields should look like this:
    primary:
    { ..., name: name0, is_multi: [name0, name1, name2, ...]}
    secondaries:
    {..., name: name[^0], is_multi: name0}
    """

    def setup(self, doc):
        super().setup(doc)
        self.all_names = doc['multi']

    def update_config(self, doc):
        super().update_config(doc)
        self.alarms = {}
        for n in self.all_names:
            vals = self.db.get_reading_setting(name=n, field='alarm_thresholds')
            if vals is not None and isinstance(vals, (list, tuple)) and len(vals) == 2:
                self.alarms[n] = vals
            else:
                self.alarms[n] = (None, None)

    def more_processing(self, values):
        if self.is_int:
            values = list(map(int, values))
        return values

    def send_upstream(self, values, timestamp):
        for n, v in zip(self.all_names, values):
            low, high = self.alarms[n]
            self.db.write_to_influx(topic=self.topic, tags={'reading': n, 'subsystem': self.subsystem},
                    fields={'value': v, 'alarm_low': low, 'alarm_high': high}, timestamp=timestamp)

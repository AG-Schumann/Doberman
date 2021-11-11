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
        self.name = kwargs['name']
        self.logger = kwargs.pop('logger')
        self.sensor_process = kwargs['sensor'].process_one_reading
        self.sensor_schedule = kwargs['sensor'].add_to_schedule
        doc = self.db.get_reading_setting(name=self.name)
        self.is_int = 'is_int' in doc
        self.topic = doc['topic']
        self.subsystem = doc.get('subsystem', 'unknown')
        self.child_setup(doc)
        self.update_config()

    def run(self):
        self.logger.debug(f'{self.name} Starting')
        while not self.event.is_set():
            loop_top = time.time()
            self.update_config()
            if self.status == 'online':
                self.do_one_measurement()
            self.event.wait(loop_top + self.readout_interval - time.time())
        self.logger.debug(f'{self.name} Returning')

    def update_config(self):
        doc = self.db.get_reading_setting(name=self.name)
        self.status = doc['status']
        self.readout_interval = doc['readout_interval']
        self.alarm = doc.get('alarm_thresholds', [])
        self.logger.debug(f'{self.name} returning')

    def update_config(self, doc=None):
        if doc is None:
            doc = self.db.get_reading_setting(sensor=self.sensor_name, name=self.name)
        self.status = doc['status']
        self.readout_interval = doc['readout_interval']
        self.update_child_config(doc)

    def child_setup(self, config_doc):
        pass

    def update_child_config(self, config_doc):
        pass

    def do_one_measurement(self):
        """
        One measurement cycle
        """
        pkg = {} # we use a dict because that passes by reference
        failed = False
        with self.cv:
            self.schedule(reading_name=self.name, retq=(pkg, self.cv))
            if self.cv.wait_for(lambda: (len(pkg) > 0 or self.event.is_set()), timeout=self.readout_interval):
                # wait_for returns True unless the timeout expired
                failed = len(pkg) == 0
            else:
                # the timeout expired, do something?
                failed = True
        if failed:
            self.logger.info('Didn\'t get anything from the sensor!')
            return
        try:
            value = self.sensor_process(name=self.name, data=pkg['data'])
        except (ValueError, TypeError, ZeroDivisionError, UnicodeDecodeError, AttributeError) as e:
            self.logger.debug(f'Got a {type(e)} while processing \'{ret["data"]}\': {e}')
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
        low, high = self.alarm if len(self.alarm) == 2 else (None, None)
        self.db.write_to_influx(topic=self.topic, tags={'reading': self.name, 'subsystem': self.subsystem},
                                fields={'value': value, 'alarm_low': low, 'alarm_high': high},
                                timestamp=timestamp)

    def send_upstream(self, value):
        """
        This function sends data upstream to wherever it should end up
        """
        if self.db.has_kafka:
            try:
                self.kafka(value=f'{self.name},{value:.6g}')
            except Exception as e:
                self.kafka(value=f'{self.name},{value}')
            return
        self.db.write_to_influx(topic=self.topic, tags={'sensor': self.sensor_name, 'reading': self.name},
                                fields={'value': value})

class MultiReading(Reading):
    """
    A special class to handle sensors that return multiple values for each
    readout cycle (smartec_uti, caen mainframe, etc)
    """

    def child_setup(self, doc):
        super().child_setup(doc)
        self.all_names = doc['multi']

    def update_child_config(self, doc):
        super().update_child_config(doc)
        self.alarms = {n: self.db.get_reading_setting(name=n, field='alarm_thresholds') for n in self.all_names}

    def more_processing(self, values):
        if self.is_int:
            values = list(map(int, values))
        return values

    def send_upstream(self, values, timestamp):
        for n, v in zip(self.all_names, values):
            low, high = self.alarms[n] if n in self.alarms and len(self.alarms[n]) == 2 else (None, None)
            self.db.write_to_influx(topic=self.topic, tags={'reading': n, 'subsystem': self.subsystem},
                    fields={'value': v, 'alarm_low': low, 'alarm_high': high},
                    timestamp=timestamp)

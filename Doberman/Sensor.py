import threading
import time

__all__ = 'Sensor MultiSensor'.split()

class Sensor(threading.Thread):
    """
    A thread responsible for scheduling readouts and processing the returned data.
    """

    def __init__(self, **kwargs):
        threading.Thread.__init__(self)
        self.db = kwargs['db']
        self.event = kwargs['event']
        self.name = kwargs['sensor_name']
        self.logger = kwargs.pop('logger')
        self.cv = threading.Condition()
        self.device_name = kwargs['device_name']
        self.device_process = kwargs['device'].process_one_value
        self.schedule = kwargs['device'].add_to_schedule
        doc = self.db.get_sensor_setting(name=self.name)
        self.setup(doc)
        self.update_config(doc)

    def run(self):
        self.logger.debug(f'{self.name} Starting')
        while not self.event.is_set():
            loop_top = time.time()
            doc = self.db.get_sensor_setting(name=self.name)
            self.update_config(doc)
            if doc['status'] == 'online':
                self.do_one_measurement()
            self.event.wait(loop_top + self.readout_interval - time.time())
        self.logger.debug(f'{self.name} Returning')

    def setup(self, config_doc):
        """
        Initial setup using whatever parameters are in the config doc
        :param config_doc: the sensor document from the database
        """
        self.is_int = 'is_int' in config_doc
        self.topic = config_doc['topic']
        self.subsystem = config_doc['subsystem']

    def update_config(self, doc):
        """
        Updates runtime configs. This is called at the start of a measurement cycle.
        :param doc: the sensor document from the database
        """
        self.readout_interval = doc['readout_interval']
        if 'alarm_thresholds' in doc and len(doc['alarm_thresholds']) == 2:
            self.alarms = doc['alarm_thresholds']
        else:
            self.alarms = (None, None)
        self.xform = doc.get('value_xform', [0, 1])

    def do_one_measurement(self):
        """
        Asks the device for data, unpacks it, and sends it to the database
        """
        pkg = {}
        self.schedule(command=self.name, ret=(pkg, self.cv))
        with self.cv:
            if self.cv.wait_for(lambda: (len(pkg) > 0 or self.event.is_set()), self.readout_interval):
                failed = False
            else:
                # timeout expired
                failed = len(pkg) == 0
        if len(pkg) == 0 or failed:
            self.logger.info('{self.name} didn\'t get anything from the device!')
            return
        try:
            value = self.device_process(name=self.name, data=pkg['data'])
        except (ValueError, TypeError, ZeroDivisionError, UnicodeDecodeError, AttributeError) as e:
            self.logger.debug(f'{self.name} got a {type(e)} while processing \'{pkg["data"]}\': {e}')
            value = None
        if value is not None:
            value = self.more_processing(value)
            self.logger.debug(f'{self.name} measured {value}')
            self.send_upstream(value, pkg['time'])
        else:
            self.logger.debug(f'{self.name} got None')
        return

    def more_processing(self, value):
        """
        Does something interesting with the value. Should return a value
        """
        value = sum(a*value**i for i, a in enumerate(self.xform))
        if self.is_int:
            value = int(value)
        return value

    def send_upstream(self, value, timestamp):
        """
        This function sends data upstream to wherever it should end up
        """
        low, high = self.alarms
        tags = {'subsystem': self.subsystem, 'device': self.device_name, 'sensor': self.name}
        fields = {'value': value}
        if low is not None:
            fields['alarm_low'] = low
        if high is not None:
            fields['alarm_high'] = high
        self.db.write_to_influx(topic=self.topic, tags=tags, fields=fields)


class MultiSensor(Sensor):
    """
    A special class to handle devices that return multiple values for each
    readout cycle (smartec_uti, caen mainframe, etc). This works this way:
    one sensor is designated the "primary" and the others are "secondaries".
    Only the primary is actually read out, but the assumption is that the sensor
    of the primary also brings the values of the secondary with it. The secondaries
    must have entries in the database but these are "shadow" entries and most of the
    fields will be ignored, the only ones mattering are any alarm values or transform values.
    Things like "status" and "readout_interval" only use the value of the primary.
    The extra database fields should look like this:
    primary:
    { ..., name: name0, multi_sensor: [name0, name1, name2, ...]}
    secondaries:
    {..., name: name[^0], multi_sensor: name0}
    """

    def setup(self, doc):
        super().setup(doc)
        self.all_names = doc['multi_sensor']

    def update_config(self, doc):
        super().update_config(doc)
        self.alarms = {}
        self.xform = {}
        for n in self.all_names:
            rdoc = self.db.get_sensor_setting(name=n)
            vals = rdoc.get('alarm_thresholds')
            if vals is not None and isinstance(vals, (list, tuple)) and len(vals) == 2:
                self.alarms[n] = vals
            else:
                self.alarms[n] = (None, None)
            self.xform[n] = rdoc.get('value_xform', [0, 1])

    def more_processing(self, values):
        for i, (n, v) in enumerate(zip(self.all_names, values)):
            values[i] = sum(a*v**j for j, a in enumerate(self.xform[n]))
        if self.is_int:
            values = list(map(int, values))
        return values

    def send_upstream(self, values, timestamp):
        for n, v in zip(self.all_names, values):
            tags = {'sensor': n, 'subsystem': self.subsystem}
            low, high = self.alarms[n]
            fields = {'value': v}
            if low is not None:
                fields['alarm_low'] = low
            if high is not None:
                fields['alarm_high'] = high
            self.db.write_to_influx(topic=self.topic, tags=tags, fields=fields)


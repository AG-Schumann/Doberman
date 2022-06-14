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
        self.event = threading.Event()
        self.name = kwargs['sensor_name']
        self.logger = kwargs['logger']
        self.device_name = kwargs['device_name']
        self.device_process = kwargs['device'].process_one_value
        self.schedule = kwargs['device'].add_to_schedule
        self.cv = threading.Condition()
        doc = self.db.get_sensor_setting(name=self.name)
        self.setup(doc)
        self.update_config(doc)

    def run(self):
        self.logger.debug(f'Starting')
        while not self.event.is_set():
            loop_top = time.time()
            doc = self.db.get_sensor_setting(name=self.name)
            self.update_config(doc)
            if doc['status'] == 'online':
                self.do_one_measurement()
            self.event.wait(loop_top + self.readout_interval - time.time())
        self.logger.debug(f'Returning')

    def setup(self, config_doc):
        """
        Initial setup using whatever parameters are in the config doc
        :param config_doc: the sensor document from the database
        """
        self.is_int = 'is_int' in config_doc
        self.topic = config_doc['topic']
        self.subsystem = config_doc['subsystem']
        self.readout_command = config_doc['readout_command']

    def update_config(self, doc):
        """
        Updates runtime configs. This is called at the start of a measurement cycle.
        :param doc: the sensor document from the database
        """
        self.readout_interval = doc['readout_interval']
        self.xform = doc.get('value_xform', [0, 1])

    def do_one_measurement(self):
        """
        Asks the device for data, unpacks it, and sends it to the database
        """
        pkg = {}
        self.schedule(self.readout_command, ret=(pkg, self.cv))
        with self.cv:
            if self.cv.wait_for(lambda: (len(pkg) > 0 or self.event.is_set()), self.readout_interval):
                failed = False
            else:
                # timeout expired
                failed = len(pkg) == 0
        if len(pkg) == 0 or failed:
            self.logger.info(f'Didn\'t get anything from the device!')
            return
        try:
            value = self.device_process(name=self.name, data=pkg['data'])
        except (ValueError, TypeError, ZeroDivisionError, UnicodeDecodeError, AttributeError) as e:
            self.logger.debug(f'Got a {type(e)} while processing \'{pkg["data"]}\': {e}')
            value = None
        if value is not None:
            value = self.more_processing(value)
            #self.logger.debug(f'{self.name} measured {value}')
            self.send_downstream(value, pkg['time'])
        else:
            self.logger.debug(f'Got None')
        return

    def more_processing(self, value):
        """
        Does something interesting with the value. Should return a value

        """
        value = sum(a*value**i for i, a in enumerate(self.xform))
        value = int(value) if self.is_int else float(value)
        return value

    def send_downstream(self, value, timestamp):
        """
        This function sends data downstream to wherever it should end up
        """
        tags = {'subsystem': self.subsystem, 'device': self.device_name, 'sensor': self.name}
        fields = {'value': value}
        self.db.write_to_influx(topic=self.topic, tags=tags, fields=fields, timestamp=timestamp)
        self.db.send_value_to_pipelines(self.name, value, timestamp)


class MultiSensor(Sensor):
    """
    A special class to handle devices that return multiple values for each
    readout cycle (smartec_uti, caen mainframe, etc). This works this way:
    one sensor is designated the "primary" and the others are "secondaries".
    Only the primary is actually read out, but the assumption is that the sensor
    of the primary also brings the values of the secondary with it. The secondaries
    must have entries in the database but the "status" and "readout_interval" of the primary
    will used over whatever the secondaries have.
    The extra database fields should look like this:
    primary:
    { ..., name: name0, multi_sensor: [name0, name1, name2, ...]}
    secondaries:
    {..., name: name[^0], multi_sensor: name0}
    """

    def setup(self, doc):
        super().setup(doc)
        self.all_names = doc['multi_sensor']
        self.topics = {}
        self.is_int = {}
        self.subsystem = {}
        for n in self.all_names:
            doc = self.db.get_sensor_setting(name=n)
            self.topics[n] = doc['topic']
            self.is_int[n] = doc.get('is_int', False)
            self.subsystem[n] = doc['subsystem']

    def update_config(self, doc):
        super().update_config(doc)
        self.xform = {}
        for n in self.all_names:
            rdoc = self.db.get_sensor_setting(name=n)
            self.xform[n] = rdoc.get('value_xform', [0, 1])

    def more_processing(self, values):
        """
        Convert from a list to a dict here
        """
        _values = {}
        for name, value in zip(self.all_names, values):
            if value is None:
                continue
            value = sum(a*value**j for j, a in enumerate(self.xform[name]))
            _values[name] = int(value) if self.is_int[name] else float(value)
        return _values

    def send_downstream(self, values, timestamp):
        """
        values is the dict we produce in more_processing
        """
        for n, v in values.items():
            tags = {'sensor': n, 'subsystem': self.subsystem[n], 'device': self.device_name}
            fields = {'value': v}
            self.db.write_to_influx(topic=self.topics[n], tags=tags, fields=fields, timestamp=timestamp)
            self.db.send_value_to_pipelines(n, v, timestamp)


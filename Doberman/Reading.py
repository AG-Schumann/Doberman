import Doberman
import time
import queue
from functools import partial
import threading
import influxdb

__all__ = 'Reading MultiReading'.split()


class Reading(threading.Thread):
    """
    A thread responsible for scheduling readouts and processing the returned data.
    """

    def __init__(self, **kwargs):
        threading.Thread.__init__(self)
        self.db = kwargs['db']
        self.last_measurement_time = time.time()
        self.late_counter = 0
        self.recurrence_counter = 0
        self.process_queue = queue.Queue()
        self.sensor_name = kwargs['sensor_name']
        self.event = kwargs['event']
        self.name = kwargs['reading_name']
        self.runmode = self.db.get_reading_setting(sensor=self.sensor_name, name=self.name, field='runmode')
        self.kafka = self.db.get_kafka(self.db.get_reading_setting(sensor=self.sensor_name,
                                                                   name=self.name, field='topic'))
        self.key = '%s__%s' % (self.sensor_name, self.name)
        self.logger = Doberman.utils.logger(db=self.db, name=self.key,
                                            loglevel=kwargs['loglevel'])
        self.sensor_process = partial(kwargs['sensor'].process_one_reading, name=self.name)
        self.Schedule = partial(kwargs['sensor'].add_to_schedule, reading_name=self.name,
                                retq=self.process_queue)
        self.child_setup(self.db.get_sensor_setting(name=self.sensor_name))
        self.update_config()
        if not self.db.has_kafka:
            influx = self.db.read_from_db('settings', 'experiment_config', cuts={'name': 'influx'},
                                          onlyone=True)
            self.client = influxdb.InfluxDBClient(host=influx['host'], port=influx['port'])

    def run(self):
        self.logger.debug('Starting')
        while not self.event.is_set():
            loop_top = time.time()
            self.update_config()
            if self.status == 'online':
                self.Schedule()
                self.process()
            self.event.wait(loop_top + self.readout_interval - time.time())
        self.logger.debug('Returning')

    def update_config(self):
        doc = self.db.get_reading_setting(sensor=self.sensor_name, name=self.name)
        self.status = doc['status']
        self.readout_interval = doc['readout_interval']
        self.is_int = 'is_int' in doc
        self.update_child_config(doc)

    def child_setup(self, config_doc):
        pass

    def update_child_config(self, config_doc):
        pass

    def do_one_measurement(self):
        """
        One measurement cycle
        """
        ret = [] # we use a list because that passes by reference
        func_start = time.time()
        with self.cv:
            self.schedule(reading_name=self.name, retq=(ret, self.cv))
            self.cv.wait_for(lambda: len(ret) > 0 or self.event.is_set())
        # TODO add a checkout about how long the above bits took
        if len(ret) == 0:
            self.logger.info('Didn\'t get anything from the sensor!')
            return
        try:
            value = self.sensor_process(data=ret[0]['data'])
        except (ValueError, TypeError, ZeroDivisionError, UnicodeDecodeError, AttributeError) as e:
            self.logger.debug(f'Got a {type(e)} while processing \'{ret[0]["data"]}\': {e}')
            value = None
        if ((func_start - self.last_measurement_time) > 1.5 * self.readout_interval or
                value is None):
            self.late_counter += 1
            if self.late_counter > 2:
                msg = f'Sensor {self.sensor_name} responding slowly? {self.late_counter} measurements are late or missing'
                if self.runmode == 'default':
                    self.db.log_alarm({'msg': msg, 'name': self.key, 'howbad': 1})
                else:
                    self.logger.info(msg)
                self.late_counter = 0
        else:
            self.late_counter = max(0, self.late_counter - 1)
        self.last_measurement_time = func_start
        self.logger.debug(f'Measured {value}')
        if value is not None:
            self.more_processing(value)
        return

    def more_processing(self, value):
        """
        Does anything interesting with the value. This function is responsible for
        pushing data upstream
        """
        if self.is_int:
            value = int(value)
        if self.db.has_kafka:
            try:
                self.kafka(value=f'{self.name},{value:.6g}')
            except Exception as e:
                self.kafka(value=f'{self.name},{value}')
            return
        reading = self.db.get_reading_setting(self.sensor_name, self.name)
        data = [{'measurement': reading['topic'],
                 'time': int(time.time() * 1000000000),
                 'fields': {reading['name']: value}
                 }]
        self.client.write_points(data, database=self.db.experiment_name)
        self.check_for_alarm(value)

    def check_for_alarm(self, value):
        """
        If Kafka is not used this checks the reading for alarms and logs it to the database
        """
        reading = self.db.get_reading_setting(self.sensor_name, self.name)
        if reading['runmode'] == 'default':
            alarms = reading['alarms']
            try:
                simple_alarm = list(filter(lambda alarm: alarm['type'] == 'simple', alarms))[0]
                if simple_alarm['enabled'] == 'true':
                    setpoint = simple_alarm['setpoint']
                    recurrence = simple_alarm['recurrence']
                    levels = simple_alarm['levels']
                    for i, level in reversed(list(enumerate(levels))):
                        lo, hi = level
                        if lo <= value - setpoint <= hi:
                            self.recurrence_counter = 0
                        else:
                            self.recurrence_counter += 1
                            if self.recurrence_counter >= recurrence:
                                msg = f'Alarm for {reading["topic"]} measurement {self.name}: {value} is outside ' \
                                      + f'alarm range ({setpoint + lo}, {setpoint + hi})'
                                self.logger.warning(msg)
                                self.db.log_alarm({'msg': msg, 'name': self.key, 'howbad': i})
                                self.recurrence_counter = 0
                            break
            except Exception as e:
                self.logger.debug(f'Alarms not properly configured for {self.reading_name}: {e}')


class MultiReading(Reading):
    """
    A special class to handle sensors that return multiple values for each
    readout cycle (smartec_uti, caen mainframe, etc)
    """

    def child_setup(self, doc):
        self.all_names = doc['multi']

    def more_processing(self, value_arr):
        try:
            for n, v in zip(self.all_names, value_arr):
                if self.is_int:
                    v = int(v)
                self.kafka(value=f'{n},{v:.6g}')
            return
        except Exception as e:
            self.logger.info(f'{type(e)}: {e}')
            return

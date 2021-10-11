import Doberman
import time
import queue
from functools import partial
import threading

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
        self.logger = kwargs.pop('logger')
        self.runmode = self.db.get_reading_setting(sensor=self.sensor_name, name=self.name, field='runmode')
        self.key = f'{self.sensor_name}__{self.name}'
        self.sensor_process = partial(kwargs['sensor'].process_one_reading, name=self.name)
        self.Schedule = partial(kwargs['sensor'].add_to_schedule, reading_name=self.name,
                                retq=self.process_queue)
        self.child_setup(self.db.get_sensor_setting(name=self.sensor_name))
        self.update_config()

    def run(self):
        self.logger.debug(f'{self.key} Starting')
        while not self.event.is_set():
            loop_top = time.time()
            self.update_config()
            if self.status == 'online':
                self.Schedule()
                self.process()
            self.event.wait(loop_top + self.readout_interval - time.time())
        self.logger.debug(f'{self.key} Returning')

    def update_config(self):
        doc = self.db.get_reading_setting(sensor=self.sensor_name, name=self.name)
        self.status = doc['status']
        self.readout_interval = doc['readout_interval']
        self.is_int = 'is_int' in doc
        self.topic = doc['topic']
        self.update_child_config(doc)

    def child_setup(self, config_doc):
        pass

    def update_child_config(self, config_doc):
        pass

    def process(self):
        """
        Receives the value from the sensor and makes sure that there actually is
        something coming back
        """
        func_start = time.time()
        pkg = None
        while time.time() - func_start < self.readout_interval:
            try:
                pkg = self.process_queue.get(timeout=0.01)
            except queue.Empty:
                pass
            else:
                self.process_queue.task_done()
                break
        if pkg is None:
            self.logger.info('Didn\'t get anything from the sensor!')
            return
        try:
            value = self.sensor_process(data=pkg['data'])
        except (ValueError, TypeError, ZeroDivisionError, UnicodeDecodeError, AttributeError) as e:
            self.logger.debug(f'Got a {type(e)} while processing \'{pkg["data"]}\': {e}')
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
            value = self.more_processing(value)
            self.check_for_alarm(value)
            self.send_upstream(value)
        return

    def more_processing(self, value):
        """
        Does something interesting with the value. Should return a value
        """
        if self.is_int:
            value = int(value)
        return value

    def send_upstream(self, value):
        """
        This function sends data upstream to wherever it should end up
        """
        doc = self.db.find_alarms(self.name)
        self.db.write_to_influx(topic=self.topic, tags={'sensor': self.sensor_name, 'reading': self.name},
                fields={'value': value, 'alarm_low': low, 'alarm_high': high})


class MultiReading(Reading):
    """
    A special class to handle sensors that return multiple values for each
    readout cycle (smartec_uti, caen mainframe, etc)
    """

    def child_setup(self, doc):
        self.all_names = doc['multi']

    def more_processing(self, values):
        if self.is_int:
            return list(map(int, values))
        return values

    def send_upstream(self, values):
        for n, v in zip(self.all_names, values):
            self.db.write_to_influx(topic=self.topic, tags={'sensor': self.sensor_name, 'reading': n},
                                    fields={'value': v})

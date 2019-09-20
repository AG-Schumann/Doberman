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
        self.kafka = self.db.GetKafka()
        self.process_queue = queue.Queue()
        self.sensor_name = kwargs['sensor_name']
        self.event = kwargs['event']
        self.name = kwargs['reading_name']
        self.key = '%s__%s' % (self.sensor_name, self.name)
        self.logger = Doberman.utils.Logger(db=self.db, name=self.key,
                loglevel=kwargs['loglevel'])
        self.sensor_process = partial(kwargs['sensor'].ProcessOneReading, name=self.name)
        self.Schedule = partial(kwargs['sensor'].AddToSchedule, reading_name=self.name,
                retq=self.process_queue)
        self.ChildSetup(self.db.GetSensorSetting(name=self.sensor_name))
        self.UpdateConfig()

    def run(self):
        self.logger.debug('Starting')
        while not self.event.is_set():
            loop_top = time.time()
            self.UpdateConfig()
            if self.status == 'online':
                self.Schedule()
                self.Process()
            self.event.wait(loop_top + self.readout_interval - time.time())
        self.logger.debug('Returning')
        return

    def UpdateConfig(self):
        doc = self.db.GetReadingSetting(sensor=self.sensor_name, name=self.name)
        self.status = doc['status']
        self.readout_interval = doc['readout_interval']
        self.is_int = 'is_int' in doc
        self.UpdateChildConfig(doc)
        return

    def ChildSetup(self, config_doc):
        pass

    def UpdateChildConfig(self, config_doc):
        pass

    def Process(self):
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
            self.logger.info('Got a %s while processing \'%s\': %s' % (type(e), pkg['data'], e))
            value = None
        if ((func_start - self.last_measurement_time) > 1.5*self.readout_interval or
                value is None):
            self.late_counter += 1
            if self.late_counter > 2:
                #self.db.LogAlarm({'msg' : ('Sensor responding slowly? %i measurements '
                #    'are late or missing' % self.late_counter), 'name' : self.key})
                self.late_counter = 0
        else:
            self.late_counter = max(0, self.late_counter-1)
        self.last_measurement_time = func_start
        self.logger.debug('Measured %s' % (value))
        if value is not None:
            self.MoreProcessing(value)
        return

    def MoreProcessing(self, value):
        """
        Does anything interesting with the value. This function is responsible for
        pushing data upstream
        """
        if self.is_int:
            value = int(value)
        self.kafka.send(f'{self.name},{value:.6g}')
        return


class MultiReading(Reading):
    """
    A special class to handle sensors that return multiple values for each
    readout cycle (smartec_uti, caen mainframe, etc)
    """
    def ChildSetup(self, doc):
        self.all_names = doc['multi']

    def MoreProcessing(self, value_arr):
        for n,v in zip(self.all_names, value_arr):
            if self.is_int:
                v = int(v)
            self.kafka.send(f'{n},{v:.6g}')
        return

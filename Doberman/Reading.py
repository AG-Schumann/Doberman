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
    def __init__(self, sensor_name, reading_name, db=None, sensor=None, loglevel='INFO', queue=None):
        threading.Thread.__init__()
        self.db = db
        self.last_measurement_time = time.time()
        self.late_counter = 0
        self.kafka = db.GetKafka()
        self.dump_queue = queue
        self.process_queue = queue.SimpleQueue()
        self.sensor_name = sensor_name
        self.event = threading.Event()
        self.SetName(reading_name)
        self.key = '%s__%s' % (self.sensor_name, self.name)
        self.logger = Doberman.utils.Logger(db=db, name=self.key, loglevel=loglevel)
        self.sensor_process = partial(sensor.ProcessOneReading, name=self.name)
        self.Schedule = partial(sensor.AddToSchedule, reading_name=self.name,
                retq=self.process_queue)
        self.UpdateConfig()

    def SetName(self, reading_name):
        self.name = reading_name

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
                pkg = self.process_queue.get(timeout=0.001)
                now = time.time()
            except queue.Empty:
                pass
            else:
                self.process_queue.task_done()
                break
        if pkg is None:
            self.logger.info('Didn\'t get anything from the sensor!')
            return
        try:
            value = self.sensor_process(pkg['data'])
        except (ValueError, TypeError, ZeroDivisionError, UnicodeDecodeError, AttributeError) as e:
            self.logger.info('Got a %s while processing \'%s\': %s' % (type(e), pkg['data'], e))
            value = None
        if ((now - self.last_measurement_time) > 1.5*self.readout_interval or
                value is None):
            self.late_counter += 1
            if self.late_counter > 2:
                #self.db.LogAlarm({'msg' : ('Sensor responding slowly? %i measurements '
                #    'are late or missing' % self.late_counter), 'name' : self.key})
                self.late_counter = 0
        else:
            self.late_counter = max(0, self.late_counter-1)
        self.last_measurement_time = now
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
        #self.kafka.send(f'{self.name},{value:.6g'})
        self.queue.put((self.name, value))
        return


class MultiReading(Reading):
    """
    A special class to handle sensors that return multiple values for each
    readout cycle (smartec_uti, caen mainframe, etc)
    """
    def SetName(self, reading_name):
        self.all_names = reading_name
        self.name = reading_name[0]
        return

    def MoreProcessing(self, value_arr):
        for n,v in zip(self.all_names, value_arr):
            self.kafka.send(f'{n},{v:.6g}')
        return

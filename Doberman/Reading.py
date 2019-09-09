import Doberman
import time

__all__ = 'Reading'.split()

class Reading(object):
    """
    A class to handle specific readings. Exists mainly so the PID subclass
    works properly
    """
    def __init__(self, sensor_name, reading_name, db, loglevel='INFO'):
        self.db = db
        self.sensor_name = sensor_name
        self.name = reading_name
        self.last_measurement_time = time.time()
        self.late_counter = 0
        self.key = '%s__%s' % (sensor_name, reading_name)
        self.logger = Doberman.utils.Logger(db=db, name=self.key, loglevel=loglevel)
        self.UpdateConfig()

    def UpdateConfig(self):
        doc = self.db.GetReadingSetting(sensor=self.sensor_name, name=self.name)
        self.status = doc['status']
        self.readout_interval = doc['readout_interval']

    def Process(self, value):
        now = time.time()
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
        return value

class MultiReading(Reading):
    """
    A special class to handle sensors that return multiple values for each
    readout cycle (looking at you, smartec_uit)
    """
    def __init__(self):
        pass

    def Process(self, value_arr):
        now = time.time()
        if ((now - self.last_measurement_time) > 1.5*self.readout_interval or
                None in value_arr):
            self.late_counter += 1
            if self.late_counter > 2:
                self.db.LogAlarm()
                self.late_counter = 0
        else:
            self.late_counter = max(0, self.late_counter-1)
        self.last_measurement_time = now

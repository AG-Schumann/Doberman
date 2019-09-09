import Doberman
import threading
from functools import partial

__all__ = 'SensorMonitor'.split()


class SensorMonitor(Doberman.Monitor):
    """
    A subclass to monitor an active sensor
    """

    def Setup(self):
        self.logger.debug('Setup starting')
        plugin_dir = self.db.GetHostSetting(field='plugin_dir')
        self.logger.debug('Got dir, finding ctor')
        self.sensor_ctor = Doberman.utils.FindPlugin(self.name, plugin_dir)
        self.sensor = None
        self.buffer_lock = threading.RLock()
        cfg_doc = self.db.GetSensorSetting(self.name)
        self.logger.debug('Got cfg doc, setting readings')
        self.readings = {reading_name : Doberman.Reading(self.name, reading_name, self.db)
            for reading_name in cfg_doc['readings'].keys()}
        self.buffer = []
        self.OpenSensor()
        self.Register(func=self.ClearBuffer, period=cfg_doc['buffer_timer'],
                name='bufferer')
        for r in self.readings.values():
            self.Register(func=self.ScheduleReading, period=r.readout_interval,
                    reading=r, name=r.name)
        self.Register(self.Heartbeat, name='heartbeat',
                period=self.db.GetHostSetting(field='heartbeat_timer'))

    def Shutdown(self):
        self.logger.info('Stopping sensor')
        self.sensor.running = False
        self.sensor.close()

    def OpenSensor(self, reopen=False):
        self.logger.debug('Connecting to sensor')
        if self.sensor is not None and not reopen:
            self.logger.debug('Already connected!')
            return
        if reopen:
            self.logger.debug('Attempting reconnect')
            self.sensor.running = False
            self.sensor.close()
        try:
            self.sensor = self.sensor_ctor(self.db.GetSensorSetting(self.name), self.logger)
            self.sensor.BaseSetup()
        except Exception as e:
            self.logger.error('Could not open sensor. Error: %s' % e)
            self.sensor = None
            raise

    def ClearBuffer(self):
        with self.buffer_lock:
            if len(self.buffer):
                doc = dict(self.buffer)
                self.logger.debug('%i readings, %i values' % (len(doc), len(self.buffer)))
                self.db.PushDataUpstream(self.name, doc)
                self.buffer = []
            else:
                self.logger.debug('No data in buffer')
        return self.db.GetSensorSetting(name=self.name, field='buffer_timer')

    def ScheduleReading(self, reading):
        reading.UpdateConfig()
        self.logger.debug('Scheduling %s' % reading.name)
        if reading.status == 'online' and reading.readout_interval > 0:
            self.sensor.AddToSchedule(reading_name=reading.name,
                    callback=partial(self.ProcessReading, reading_name=reading.name))
        return reading.readout_interval

    def Heartbeat(self):
        self.db.UpdateHeartbeat(sensor=self.name)
        return self.db.GetHostSetting(field='heartbeat_timer')

    def ProcessReading(self, value, reading_name):
        value = self.readings[reading_name].Process(value)
        if value is not None:
            with self.buffer_lock:
                if isinstance(value, (list, tuple)):
                    pass
                else:
                    self.buffer.append((reading_name, value))

    def HandleCommands(self):
        doc = self.db.FindCommand(self.name)
        while doc is not None:
            command = doc['command']
            self.logger.info(f"Found command '{command}'")
            if command.startswith('runmode'):
                try:
                    _, runmode, reading = command.split()
                except:
                    self.logger.error('Bad runmode command')
                else:
                    if reading == 'all':
                        for rd in self.reading_names:
                            self.db.SetReadingSetting(sensor=self.name, reading=rd,
                                    set={'runmode' : runmode})
                    else:
                        self.db.SetReadingSetting(sensor=self.name, reading=reading,
                                set={'runmode' : runmode})
            elif command == 'reload readings':
                self.sensor.setattr('readings',
                        self.db.GetSensorSetting(self.name, field='readings'))
                self.ReloadReadings()
            elif command == 'stop':
                self.sh.run = False
                self.sh.restart_me = False  # TODO handle
            elif self.sensor is not None:
                self.sensor.AddToSchedule(command=command)
            else:
                self.logger.error(f"Command '{command}' not accepted")
            doc = self.db.FindCommand(self.name)

    def ReloadReadings(self):
        readings_dict = self.db.GetSensorSetting(self.name, 'readings')
        for reading_name in readings_dict.values():
            if reading_name in self.threads.keys():
                self.StopThread(reading_name)
            self.readings[reading_name] = Doberman.Reading(self.name, reading_name,
                    self.db)
            self.Register(func=self.ScheduleReading, period=r.readout_interval,
                    reading=r, name=r.name)

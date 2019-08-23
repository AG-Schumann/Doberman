import Doberman
import threading

__all__ = 'SensorMonitor'.split()


class SensorMonitor(Doberman.Monitor):
    """
    A subclass to monitor an active sensor
    """

    def Setup(self):
        plugin_dir = self.GetHostSetting(field='plugin_dir')
        self.sensor_ctor = Doberman.utils.FindPlugin(self.name, plugin_dir)
        self.sensor = None
        self.buffer_lock = threading.RLock()
        self.processing_lock = threading.RLock()
        self.readings = [Doberman.Reading(self.name, reading_name)
            for reading_name in self.db.GetSensorSetting(self.name, field='readings')]
        self.buffer = []
        self.OpenSensor()
        self.Register(func=self.ClearBuffer, period=Doberman.buffer_timer)
        for r in self.readings:
            self.Register(func=self.ScheduleReading, period=None, reading=r)
        self.Register(self.Heartbeat, period=Doberman.heartbeat_timer)

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
            self.sensor = self.sensor_ctor(self.db.GetSensorSetting(self.name))
            self.sensor._Setup()
        except Exception as e:
            self.logger.error('Could not open sensor. Error: %s' % e)
            self.sensor = None
            raise

    def ClearBuffer(self):
        with self.buffer_lock:
            if len(self.buffer):
                doc = dict(self.buffer)
                self.logger.debug('%i readings, %i values' % (len(doc), len(self.buffer)))
                self.db.WriteDataToDatabase(self.name, doc)
                self.buffer = []
            else:
                self.logger.debug('No data in buffer')
        return self.db.GetSensorSetting(name=self.name, field='buffer_timer')

    def ScheduleReading(self, reading):
        reading.UpdateConfig()
        if reading.status == 'online' and reading.readout_interval > 0:
            self.sensor.AddToSchedule(reading_name=reading.name,
                    callback=partial(self.ProcessReading, reading=reading))
        return reading.readout_interval

    def Heartbeat(self):
        self.db.UpdateHeartbeat(sensor=self.name)
        return self.db.GetHostSetting(field='heartbeat_timer')

    def ProcessReading(self, value, reading):
        value = reading.Process(value)
        if value is not None:
            with self.buffer_lock:
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
            elif command == 'stop':
                self.sh.run = False
                self.sh.restart_me = False
            elif self.sensor is not None:
                self.sensor.AddToSchedule(command=command)
            else:
                self.logger.error(f"Command '{command}' not accepted")
            doc = self.db.FindCommand(self.name)

import Doberman
import threading
from functools import partial

__all__ = 'SensorMonitor'.split()


class SensorMonitor(Doberman.Monitor):
    """
    A subclass to monitor an active sensor
    """

    def Setup(self):
        plugin_dir = self.db.GetHostSetting(field='plugin_dir')
        self.sensor_ctor = Doberman.utils.FindPlugin(self.name, plugin_dir)
        self.sensor = None
        self.buffer_lock = threading.RLock()
        cfg_doc = self.db.GetSensorSetting(self.name)
        self.OpenSensor()
        for rd in cfg_doc['readings'].keys():
            t = self.PrepareReading(rd)
            self.RegisterThread(t, partial(self.PrepareReading, rd))
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

    def PrepareReading(self, reading_name):
        """
        Returns a configured (but not yet started) Reading thread
        """
        t = Doberman.Reading()
        t.Setup(self.name, reading_name, db=self.db, sensor=self.sensor)
        return t

    def Heartbeat(self):
        self.db.UpdateHeartbeat(sensor=self.name)
        return self.db.GetHostSetting(field='heartbeat_timer')

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

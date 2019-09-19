import Doberman
import threading
from functools import partial
import queue

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
        self.buffer = queue.Queue()
        for rd in cfg_doc['readings'].keys():
            self.Register(rd, Doberman.Reading(sensor_name=self.name, reading_name=rd,
                db=self.db, sensor=self.sensor, loglevel=self.loglevel, queue=self.buffer))
        self.Register(self.Heartbeat, name='heartbeat',
                period=self.db.GetHostSetting(field='heartbeat_timer'))
        self.Register(self.EmptyBuffer, name='Bufferer', period=5)

    def Shutdown(self):
        self.logger.info('Stopping sensor')
        self.sensor.event.set()
        self.sensor.close()
        return

    def OpenSensor(self, reopen=False):
        self.logger.debug('Connecting to sensor')
        if self.sensor is not None and not reopen:
            self.logger.debug('Already connected!')
            return
        if reopen:
            self.logger.debug('Attempting reconnect')
            self.sensor.event.set()
            self.sensor.close()
        try:
            self.sensor = self.sensor_ctor(self.db.GetSensorSetting(self.name),
                    self.logger)
        except Exception as e:
            self.logger.error('Could not open sensor. Error: %s' % e)
            self.sensor = None
            raise
        return

    def Heartbeat(self):
        self.db.UpdateHeartbeat(sensor=self.name)
        return self.db.GetHostSetting(field='heartbeat_timer')

    def EmptyBuffer(self):
        data = {}
        while True:
            try:
                name, value = self.buffer.get()
                data[name] = value
                self.buffer.task_done()
            except queue.Empty:
                break
        if data:
            self.db.insertIntoDatabase('data', self.name, data)
        return

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
                self.event.set()
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

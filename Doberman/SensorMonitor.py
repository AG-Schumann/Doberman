import Doberman

__all__ = 'SensorMonitor'.split()


class SensorMonitor(Doberman.Monitor):
    """
    A subclass to monitor an active sensor
    """

    def setup(self):
        plugin_dir = self.db.get_host_setting(field='plugin_dir')
        self.sensor_ctor = Doberman.utils.find_plugin(self.name, plugin_dir)
        self.sensor = None
        cfg_doc = self.db.get_sensor_setting(self.name)
        self.open_sensor()
        for rd in cfg_doc['readings'].keys():
            self.logger.debug('Constructing ' + rd)
            reading_doc = self.db.get_reading_setting(self.name, rd)
            kwargs = {'sensor_name': self.name, 'reading_name': rd,
                      'event': self.event, 'db': self.db, 'sensor': self.sensor,
                      'loglevel': self.loglevel}
            if 'is_multi' in reading_doc:
                reading = Doberman.MultiReading(**kwargs)
            elif 'pid' in reading_doc:
                reading = Doberman.PIDReading(**kwargs)
            else:
                reading = Doberman.Reading(**kwargs)
            self.register(rd, reading)
        self.register(name='heartbeat', obj=self.heartbeat,
                      period=self.db.get_host_setting(field='heartbeat_timer'))
        self.db.set_host_setting(addToSet={'active': self.name})

    def shutdown(self):
        if self.sensor is None:
            return
        self.logger.info('Stopping sensor')
        self.sensor.event.set()
        self.sensor.close()
        self.sensor = None
        self.db.set_host_setting(pull={'active': self.name})
        return

    def open_sensor(self, reopen=False):
        self.logger.debug('Connecting to sensor')
        if self.sensor is not None and not reopen:
            self.logger.debug('Already connected!')
            return
        if reopen:
            self.logger.debug('Attempting reconnect')
            self.sensor.event.set()
            self.sensor.close()
        try:
            self.sensor = self.sensor_ctor(self.db.get_sensor_setting(self.name),
                                           self.logger)
        except Exception as e:
            self.logger.error('Could not open sensor. Error: %s' % e)
            self.sensor = None
            raise
        return

    def heartbeat(self):
        self.db.update_heartbeat(sensor=self.name)
        return self.db.get_host_setting(field='heartbeat_timer')

    def handle_commands(self):
        doc = self.db.find_command(self.name)
        while doc is not None:
            command = doc['command']
            self.logger.info(f"Found command '{command}'")
            if command.startswith('runmode'):
                try:
                    _, runmode, reading = command.split()
                except Exception as e:
                    self.logger.error(f'Bad runmode command: {e}')
                else:
                    if reading == 'all':
                        for rd in self.db.get_sensor_setting(self.name, 'readings'):
                            self.db.set_reading_setting(sensor=self.name, name=rd,
                                                        field='runmode', value=runmode)
                    else:
                        self.db.set_reading_setting(sensor=self.name, name=reading,
                                                    field='runmode', value=runmode)
            elif command == 'reload readings':
                self.sensor.setattr('readings',
                                    self.db.get_sensor_setting(self.name, field='readings'))
                self.reload_readings()
            elif command == 'stop':
                self.event.set()
                self.db.set_host_setting(pull={'default': self.name})
            elif self.sensor is not None:
                self.sensor.execute_command(command=command)
            else:
                self.logger.error(f"Command '{command}' not accepted")
            doc = self.db.find_command(self.name)

    def reload_readings(self):
        readings_dict = self.db.get_sensor_setting(self.name, 'readings')
        for reading_name in readings_dict.values():
            if reading_name in self.threads.keys():
                self.stop_thread(reading_name)
            self.readings[reading_name] = Doberman.Reading(self.name, reading_name,
                                                           self.db)
            self.register(func=self.ScheduleReading, period=r.readout_interval,
                          reading=r, name=r.name)

    def build_reading(self):
        pass

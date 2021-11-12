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
            self.start_reading(rd)
        self.register(name='heartbeat', obj=self.heartbeat,
                      period=self.db.get_experiment_config(name='hypervisor', field='period'))
        self.db.notify_hypervisor(active=self.name)

    def start_reading(self, rd):
        self.logger.debug('Constructing ' + rd)
        reading_doc = self.db.get_reading_setting(rd)
        kwargs = {'name': rd, 'logger': self.logger, db: self.db,
                  'event': self.event, 'sensor': self.sensor}
        if 'is_multi' in reading_doc:
            # TODO this is probably broken
            reading = Doberman.MultiReading(**kwargs)
        else:
            reading = Doberman.Reading(**kwargs)
        self.register(rd, reading)

    def shutdown(self):
        if self.sensor is None:
            return
        self.logger.info('Stopping sensor')
        self.sensor.event.set()
        self.sensor.close()
        self.sensor = None
        # we only unmanage if we receive a STOP command
        self.db.notify_hypervisor(inactive=self.name)
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
                                           self.logger, self.event)
        except Exception as e:
            self.logger.error(f'Could not open sensor. Error: {e} ({type(e)}')
            self.sensor = None
            raise
        return

    def heartbeat(self):
        self.db.update_heartbeat(sensor=self.name)
        return self.db.get_experiment_config(name='hypervisor', field='period')

    def handle_commands(self):
        while (doc := self.db.find_command(self.name)) is not None:
            command = doc['command']
            self.logger.info(f"Found command '{command}'")
            if command == 'reload readings':
                self.sensor.setattr('readings',
                                    self.db.get_sensor_setting(self.name, field='readings'))
                self.reload_readings()
            elif command == 'stop':
                self.event.set()
                # only unmanage from HV if asked to stop
                self.db.notify_hypervisor(unmanage=self.name)
            elif self.sensor is not None:
                self.sensor._execute_command(command=command)
            else:
                self.logger.error(f"Command '{command}' not accepted")

    def reload_readings(self):
        readings_dict = self.db.get_sensor_setting(self.name, 'readings')
        for reading_name in readings_dict.values():
            if reading_name in self.threads.keys():
                self.stop_thread(reading_name)
                self.start_reading(reading_name)


import Doberman

__all__ = 'DeviceMonitor'.split()


class DeviceMonitor(Doberman.Monitor):
    """
    A subclass to monitor an active device
    """

    def setup(self):
        plugin_dir = self.db.get_host_setting(field='plugin_dir')
        self.device_ctor = Doberman.utils.find_plugin(self.name, plugin_dir)
        self.device = None
        cfg_doc = self.db.get_device_setting(self.name)
        self.open_device()
        for rd in cfg_doc['sensors'].keys():
            self.start_sensor(rd)
        self.register(name='heartbeat', obj=self.heartbeat,
                      period=self.db.get_experiment_config(name='hypervisor', field='period'))
        self.db.notify_hypervisor(active=self.name)

    def start_sensor(self, rd):
        self.logger.debug('Constructing ' + rd)
        sensor_doc = self.db.get_sensor_setting(rd)
        kwargs = {'sensor_name': rd, 'logger': self.logger, 'db': self.db,
                  'device_name': self.name, 'event': self.event, 'device': self.device}
        if 'multi_sensor' in sensor_doc and isinstance(sensor_doc['multi_sensor'], list):
            # the "base" multisensor stores all the names in the list
            # the "secondary" multisensorss store the name of the base
            sensor = Doberman.MultiSensor(**kwargs)
        else:
            sensor = Doberman.Sensor(**kwargs)
        self.register(name=rd, obj=sensor, period=sensor.readout_interval)

    def shutdown(self):
        if self.device is None:
            return
        self.logger.info('Stopping device')
        self.device.event.set()
        self.device.close()
        self.device = None
        # we only unmanage if we receive a STOP command
        self.db.notify_hypervisor(inactive=self.name)
        return

    def open_device(self, reopen=False):
        self.logger.debug('Connecting to device')
        if self.device is not None and not reopen:
            self.logger.debug('Already connected!')
            return
        if reopen:
            self.logger.debug('Attempting reconnect')
            self.device.event.set()
            self.device.close()
        try:
            self.device = self.device_ctor(self.db.get_device_setting(self.name),
                                           self.logger, self.event)
        except Exception as e:
            self.logger.error(f'Could not open device. Error: {e} ({type(e)}')
            self.device = None
            raise
        return

    def heartbeat(self):
        self.db.update_heartbeat(device=self.name)
        return self.db.get_experiment_config(name='hypervisor', field='period')

<<<<<<< HEAD
    def process_command(self, command):
        self.logger.info(f"Found command '{command}'")
        if command == 'reload sensors':
            self.device.setattr('sensors',
                                self.db.get_device_setting(self.name, field='sensors'))
            self.reload_sensors()
        elif command == 'stop':
            self.event.set()
            # only unmanage from HV if asked to stop
            self.db.notify_hypervisor(unmanage=self.name)
        elif command[:3] == 'set':
            # this one is for the device
            quantity, value = command[4:].rsplit(' ', maxsplit=1)
            self.device._execute_command(quantity, value)
        else:
            self.logger.error(f"Command '{command}' not accepted")
=======
    def handle_commands(self):
        while (doc := self.db.find_command(self.name)) is not None:
            command = doc['command']
            self.logger.info(f"Found command '{command}'")
            if command == 'reload sensors':
                self.device.setattr('sensors',
                                    self.db.get_device_setting(self.name, field='sensors'))
                self.reload_sensors()
            elif command == 'stop':
                self.event.set()
                # only unmanage from HV if asked to stop
                self.db.notify_hypervisor(unmanage=self.name)
            elif self.device is not None:
                self.device._execute_command(command=command)
            else:
                self.logger.error(f"Command '{command}' not accepted")
>>>>>>> experimental

    def reload_sensors(self):
        sensors_doc = self.db.get_device_setting(self.name, 'sensors')
        for sensor_name in sensors_doc.values():
<<<<<<< HEAD
            if sensor_name in list(self.threads.keys()):
                self.stop_thread(sensor_name)
                self.start_sensor(sensor_name)

=======
            if sensor_name in self.threads.keys():
                self.stop_thread(sensor_name)
                self.start_sensor(sensor_name)
>>>>>>> experimental

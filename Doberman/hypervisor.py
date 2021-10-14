import Doberman
import subprocess


def Hypervisor(Doberman.Monitor):
    """
    A tool to monitor and restart processes when necessary
    """
    def setup(self):
        self.sh = Doberman.utils.SignalHandler(self.logger, self.event)
        self.register(obj=self.hypervise, period=val, name='hypervise')

    def hypervise(self):
        self.logger.debug('Hypervising')
        host_config = self.db.get_host_setting()
        for sensor in host_config['default']:
            last_hb = self.db.get_heartbeat(sensor=sensor)
            if sensor not in host_config['active']:
                # sensor isn't running and it's supposed to be
                if self.start_sensor(sensor):
                    pass
            else:
                if (dt := (now()-last_hb).total_seconds()) > val:
                    # host hasn't heartbeated recently
                    self.logger.warning(f'{sensor} hasn\'t heartbeated in {int(dt)} seconds, it\'s getting restarted')
                    if self.start_sensor(sensor):
                        # nonzero return code, probably something didn't work
                        self.logger.error(f'Problem starting {sensor}, check the debug logs')
                else:
                    # has heartbeated recently

        return host_config['heartbeat_timer']

    def run_over_ssh(self, address, command):
        """
        Runs a command over ssh, stdout/err will go to the debug logs
        :param address: user@host
        :param command: the command to run. Will be wrapped in double-quotes, a la ssh user@host "command"
        :returns: return code of ssh
        """
        cp = subprocess.run(['ssh', address, f'"{command}"'], capture_output=True)
        if cp.stdout:
            self.logger.debug(f'Stdout: {cp.stdout.decode()}')
        if cp.stderr:
            self.logger.debug(f'Stderr: {cp.stderr.decode()}')
        return cp.returncode

    def start_sensor(self, sensor):
        doc = self.db.get_sensor_setting(sensor=sensor)
        host = doc['host']
        self.db.set_host_setting(addToSet={'active': sensor})
        return self.run_over_ssh(f'doberman@{host}', f"cd {path} && ./start_sensor.sh {sensor}")

    def start_pipeline(self, pipeline):
        host = 'localhost'
        return self.run_over_ssh(f'doberman@localhost', f'cd {path} && ./start_pipeline.sh {pipeline}')

    def handle_commands(self):
        while (doc := self.db.find_command("hypervisor")) is not None:
            cmd = doc['command']
            if cmd.startswith('start'):
                _, target = cmd.split(' ', maxsplit=1)
                if target[:2] == 'pl': # this is a pipeline
                    self.start_pipeline(target)
                else:
                    self.start_sensor(sensor)
            elif cmd.startswith('manage'):
                _, sensor = cmd.split(' ', maxsplit=1)
                self.log.info(f'Hypervisor now managing {sensor}')
                self.db.set_host_setting(addToSet={'default': sensor})
            elif cmd.startswith('unmanage'):
                _, sensor = cmd.split(' ', maxsplit=1)
                self.log.info(f'Hypervisor relinquishing control of {sensor}')
                self.db.set_host_setting(pull={'default': sensor})
            else:
                pass


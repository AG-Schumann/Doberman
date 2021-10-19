import Doberman
import subprocess


def Hypervisor(Doberman.Monitor):
    """
    A tool to monitor and restart processes when necessary
    """
    def setup(self):
        self.config = self.db.read_from_db('settings', 'experiment_config', {'name': 'hypervisor'}, onlyone=True)
        self.register(obj=self.hypervise, period=self.config['period'], name='hypervise')
        self.register(obj=self.heartbeat, period=60, name='remote_heartbeat')

    def hypervise(self):
        self.logger.debug('Hypervising')
        self.config = self.db.read_from_db('settings', 'experiment_config', {'name': 'hypervisor'}, onlyone=True)
        for sensor in self.config['processes']['managed']:
            last_hb = self.db.get_heartbeat(sensor=sensor)
            if sensor not in self.config['processes']['active']:
                # sensor isn't running and it's supposed to be
                if self.start_sensor(sensor):
                    pass
            else:
                if (dt := (Doberman.utils.dtnow()-last_hb).total_seconds()) > val:
                    # host hasn't heartbeated recently
                    self.logger.warning(f'{sensor} hasn\'t heartbeated in {int(dt)} seconds, it\'s getting restarted')
                    if self.start_sensor(sensor):
                        # nonzero return code, probably something didn't work
                        self.logger.error(f'Problem starting {sensor}, check the debug logs')
                else:
                    # has heartbeated recently

        return host_config['heartbeat_timer']

    def heartbeat(self):
        self.heartbeat
        address, port = self.config['remote_heartbeat']
        self.run_over_ssh(self.config['remote_heartbeat_address'], r'date +%s > /scratch/remote_hb', port=self.config.get('remote_heartbeat_port', 22))

    def run_over_ssh(self, address, command, port=22):
        """
        Runs a command over ssh, stdout/err will go to the debug logs
        :param address: user@host
        :param command: the command to run. Will be wrapped in double-quotes, a la ssh user@host "command"
        :returns: return code of ssh
        """
        cmd = ['ssh', address, f'"{command}"']
        if port != 22:
            cmd.insert(1, '-p')
            cmd.insert(2, f'{port}')
        cp = subprocess.run(cmd, capture_output=True)
        if cp.stdout:
            self.logger.debug(f'Stdout: {cp.stdout.decode()}')
        if cp.stderr:
            self.logger.debug(f'Stderr: {cp.stderr.decode()}')
        return cp.returncode

    def start_sensor(self, sensor):
        doc = self.db.get_sensor_setting(sensor=sensor)
        host = doc['host']
        self.db.set_host_setting(addToSet={'active': sensor})
        return self.run_over_ssh(f'doberman@{host}', f"cd {path} && ./start_process.sh sensor {sensor}")

    def start_pipeline(self, pipeline):
        host = 'localhost'
        return self.run_over_ssh(f'doberman@localhost', f'cd {path} && ./start_process.sh pipeline {pipeline}')

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


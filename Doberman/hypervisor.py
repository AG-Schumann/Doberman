import Doberman
import subprocess


def Hypervisor(Doberman.Monitor):
    """
    A tool to monitor and restart processes when necessary
    """
    def setup(self):
        self.update_config(status='online')
        self.config = self.db.get_experiment_config('hypervisor')
        self.register(obj=self.hypervise, period=self.config['period'], name='hypervise')
        self.register(obj=self.heartbeat, period=60, name='remote_heartbeat')
        self.last_restart = {}

    def shutdown(self):
        self.update_config(status='offline')

    def update_config(self, unmanage=None, manage=None, active=None, heartbeat=None, status=None):
        updates = {}
        if unmanage:
            updates['$pull'] = {'processes.managed': unmanage}
        if manage:
            updates['$addToSet'] = {'processes.managed': manage}
        if active:
            updates['$addToSet'] = {'processes.active': active}
        if heartbeat:
            updates['$set']: {'heartbeat': heartbeat}
        if status:
            updates['$set'] = {'status': status}
        self.db.update_db('settings', 'experiment_config', {'name': 'hypervisor'}, updates)

    def hypervise(self):
        self.logger.debug('Hypervising')
        self.config = self.db.get_experiment_config('hypervisor')
        for sensor in self.config['processes']['managed']:
            if sensor not in self.config['processes']['active']:
                # sensor isn't running and it's supposed to be
                if self.start_sensor(sensor):
                    pass
            elif (dt := ((now := Doberman.utils.dtnow())-self.db.get_heartbeat(sensor=sensor)).total_seconds()) > 2*self.config['period']:
                # sensor claims to be active but hasn't heartbeated recently
                self.logger.warning(f'{sensor} hasn\'t heartbeated in {int(dt)} seconds, it\'s getting restarted')
                if sensor in self.last_restart and (now - self.last_restart[sensor]).total_seconds < self.config['restart_timeout']:
                    self.logger.warning(f'Can\'t restart {sensor}, did so too recently')
                elif self.start_sensor(sensor):
                    # nonzero return code, probably something didn't work
                    self.logger.error(f'Problem starting {sensor}, check the debug logs')
            else:
                # claims to be active and has heartbeated recently
                self.logger.debug(f'{sensor} last heartbeat {int(dt)} seconds ago')
        self.update_config(heartbeat=Doberman.utils.dtnow())
        return self.config['period']

    def heartbeat(self):
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
        self.update_config(active=sensor)
        self.last_restart[sensor] = now
        return self.run_over_ssh(f'doberman@{host}', f"cd {path} && ./start_process.sh sensor {sensor}")

    def start_pipeline(self, pipeline):
        host = 'localhost'
        return self.run_over_ssh(f'doberman@localhost', f'cd {path} && ./start_process.sh pipeline {pipeline}')

    def handle_commands(self):
        while (doc := self.db.find_command("hypervisor")) is not None:
            cmd = doc['command']
            if cmd.startswith('start'):
                _, target = cmd.split(' ', maxsplit=1)
                if target[:3] == 'pl_': # this is a pipeline
                    self.start_pipeline(target)
                else:
                    self.start_sensor(sensor)
            elif cmd.startswith('manage'):
                _, sensor = cmd.split(' ', maxsplit=1)
                self.log.info(f'Hypervisor now managing {sensor}')
                self.update_config(manage=sensor)
            elif cmd.startswith('unmanage'):
                _, sensor = cmd.split(' ', maxsplit=1)
                self.log.info(f'Hypervisor relinquishing control of {sensor}')
                self.update_config(unmanage=sensor)
            else:
                pass


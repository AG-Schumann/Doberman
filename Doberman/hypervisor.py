import Doberman
import subprocess
import typing as ty
import time
import os.path

dtnow = Doberman.utils.dtnow

def Hypervisor(Doberman.Monitor):
    """
    A tool to monitor and restart processes when necessary
    """
    def setup(self) -> None:
        self.update_config(status='online')
        self.config = self.db.get_experiment_config('hypervisor')
        self.register(obj=self.hypervise, period=self.config['period'], name='hypervise')
        if (rhb := self.config.get('remote_heartbeat', {}).get('status', '')) == 'send':
            self.register(obj=self.send_remote_heartbeat, period=60, name='remote_heartbeat')
        elif rhb == 'receive':
            self.register(obj=self.check_remote_heartbeat, period=60, name='remote_heartbeat')
        self.last_restart = {}

    def shutdown(self) -> None:
        self.update_config(status='offline')

    def update_config(self, unmanage=None, manage=None, active=None, heartbeat=None, status=None) -> None:
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
        if updates:
            self.db.update_db('settings', 'experiment_config', {'name': 'hypervisor'}, updates)

    def hypervise(self) -> None:
        self.logger.debug('Hypervising')
        self.config = self.db.get_experiment_config('hypervisor')
        # cache these here because they might change during iteration
        managed = self.config['processes']['managed']
        active = self.config['processes']['active']
        for sensor in managed:
            if sensor not in active:
                # sensor isn't running and it's supposed to be
                if self.start_sensor(sensor):
                    self.logger.error(f'Problem starting {sensor}, check the debug logs')
            elif (dt := ((now := dtnow())-self.db.get_heartbeat(sensor=sensor)).total_seconds()) > 2*self.config['period']:
                # sensor claims to be active but hasn't heartbeated recently
                self.logger.warning(f'{sensor} hasn\'t heartbeated in {int(dt)} seconds, it\'s getting restarted')
                if sensor in self.last_restart and (now - self.last_restart[sensor]).total_seconds() < self.config['restart_timeout']:
                    self.logger.warning(f'Can\'t restart {sensor}, did so too recently')
                elif self.start_sensor(sensor):
                    # nonzero return code, probably something didn't work
                    self.logger.error(f'Problem starting {sensor}, check the debug logs')
            else:
                # claims to be active and has heartbeated recently
                self.logger.debug(f'{sensor} last heartbeat {int(dt)} seconds ago')
        self.update_config(heartbeat=dtnow())
        return self.config['period']

    def send_remote_heartbeat(self) -> None:
        # touch a file on a remote server just so someone else knows we're still alive
        if (addr := self.config.get('remote_heartbeat', {}).get('address')) is not None:
            self.run_over_ssh(addr, r'date +%s > /scratch/remote_hb', port=self.config['remote_heartbeat'].get('port', 22))

    def check_remote_heartbeat(self):
        if os.path.exists('/scratch/remote_hb'):
            with open('/scratch/remote_hb', 'r') as f:
                time_str = f.read().strip()
            if time.time() - int(time_str) > 3*60:
                # timestamp is too old, the other server is having problems
                self.db.log_alarm(msg="The other server hasn't heartbeated recently, maybe let someone know?")

    def run_over_ssh(self, address: str, command: str, port=22) -> int:
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
        self.logger.debug(f'Running "{" ".join(cmd)}"')
        cp = subprocess.run(cmd, capture_output=True)
        if cp.stdout:
            self.logger.debug(f'Stdout: {cp.stdout.decode()}')
        if cp.stderr:
            self.logger.debug(f'Stderr: {cp.stderr.decode()}')
        return cp.returncode

    def start_sensor(self, sensor: str) -> int:
        path = self.config['path']
        doc = self.db.get_sensor_setting(sensor=sensor)
        host = doc['host']
        self.last_restart[sensor] = dtnow()
        self.update_config(manage=sensor)
        return self.run_over_ssh(f'doberman@{host}', f"cd {path} && ./start_process.sh sensor {sensor}")

    def start_pipeline(self, pipeline: str) -> int:
        path = self.config['path']
        return self.run_over_ssh(f'doberman@localhost', f'cd {path} && ./start_process.sh pipeline {pipeline}')

    def handle_commands(self) -> None:
        while (doc := self.db.find_command("hypervisor")) is not None:
            cmd = doc['command']
            if cmd.startswith('start'):
                _, target = cmd.split(' ', maxsplit=1)
                self.logger.info(f'Hypervisor starting {target}')
                if target[:3] == 'pl_': # this is a pipeline
                    self.start_pipeline(target)
                else:
                    self.start_sensor(sensor)
            elif cmd.startswith('manage'):
                _, sensor = cmd.split(' ', maxsplit=1)
                if sensor[:3] == 'pl_':
                    # unlikely but you can never trust users
                    self.logger.info('Management is for sensors, not pipelines')
                    continue
                self.logger.info(f'Hypervisor now managing {sensor}')
                self.update_config(manage=sensor)
            elif cmd.startswith('unmanage'):
                _, sensor = cmd.split(' ', maxsplit=1)
                if sensor[:3] == 'pl_':
                    # unlikely but you can never trust users
                    self.logger.info('Management is for sensors, not pipelines')
                    continue
                self.logger.info(f'Hypervisor relinquishing control of {sensor}')
                self.update_config(unmanage=sensor)
            else:
                self.logger.error(f'Command "{cmd}" not understood')


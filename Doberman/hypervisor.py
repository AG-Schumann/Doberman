import Doberman
import subprocess
import typing as ty
import time
import os.path
import os
import threading
import socket
import json
import datetime


dtnow = Doberman.utils.dtnow

class Hypervisor(Doberman.Monitor):
    """
    A tool to monitor and restart processes when necessary. It is assumed
    that this is the first thing started, and that nothing is already running.
    """
    def setup(self) -> None:
        self.update_config(status='online')
        self.config = self.db.get_experiment_config('hypervisor')
        self.localhost = self.config['host']
        self.username = self.config.get('username', os.environ['USER'])

        # do any startup sequences
        for host, activities in self.config.get('startup_sequence', {}).items():
            if host == self.localhost:
                map(self.run_locally, activities)
            else:
                for activity in activities:
                    self.run_over_ssh(f'{self.username}@{host}', activity)

        # cleanup port leases after a potential dirty shutdown
        hn, p = self.config['global_dispatch']['hypervisor']
        self.db.update_db('experiment_config', {'name': 'hypervisor'},
                {'$set': {'global_dispatch': {'hypervisor': [hn, p]}}})

        # start the three Pipeline monitors
        path = self.config['path']
        for thing in 'alarm control convert'.split():
            self.run_locally(f'cd {path} && ./start_process.sh --{thing}')
            time.sleep(0.1)

        # now start the rest of the things
        self.last_restart = {}
        self.known_devices = self.db.distinct('devices', 'name')
        self.cv = threading.Condition()
        self.dispatch_queue = Doberman.utils.SortedBuffer()
        self.dispatcher = threading.Thread(target=self.dispatch)
        self.dispatcher.start()
        self.register(obj=self.compress_logs, period=86400, name='log_compactor', _no_stop=True)
        if (rhb := self.config.get('remote_heartbeat', {}).get('status', '')) == 'send':
            self.register(obj=self.send_remote_heartbeat, period=60, name='remote_heartbeat', _no_stop=True)
        elif rhb == 'receive':
            self.register(obj=self.check_remote_heartbeat, period=60, name='remote_heartbeat', _no_stop=True)

        time.sleep(1)

        # start the fixed-frequency sync signals
        self.db.delete_documents('sensors', {'name': {'$regex': '^X_SYNC'}})
        for i in self.config.get('sync_periods', [5,10,15,30,60]):
            if self.db.get_sensor_setting(name=f'X_SYNC_{i}') is None:
                self.db.insert_into_db('sensors', {'name': f'X_SYNC_{i}', 'description': 'Sync signal', 'readout_interval': i, 'status': 'offline', 'topic': 'other',
                    'subsystem': 'sync', 'pipelines': [], 'device': 'hypervisor', 'units': '', 'readout_command': ''})
            self.register(obj=self.sync_signal, period=i, name=f'sync_{i}', _period=i)

        time.sleep(1)
        self.register(obj=self.hypervise, period=self.config['period'], name='hypervise', _no_stop=True)


    def shutdown(self) -> None:
        with self.cv:
            self.cv.notify()
        self.update_config(status='offline')
        self.dispatcher.join()

    def sync_signal(self, _period: int) -> None:
        self.db.send_value_to_pipelines(f'X_SYNC_{_period}', 0, time.time())

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
            self.db.update_db('experiment_config', {'name': 'hypervisor'}, updates)

    def hypervise(self) -> None:
        self.logger.debug('Hypervising')
        self.config = self.db.get_experiment_config('hypervisor')
        managed = self.config['processes']['managed']
        active = self.config['processes']['active']
        self.known_devices = self.db.distinct('devices', 'name')
        path = self.config['path']
        for pl in 'alarm control convert'.split():
            if self.ping(f'pl_{pl}'):
                self.run_locally(f'cd {path} && ./start_process.sh --{pl}')

        for device in managed:
            if device not in active:
                # device isn't running and it's supposed to be
                if self.start_device(device):
                    self.logger.error(f'Problem starting {device}, check the debug logs')
            elif (dt := ((now := dtnow())-self.db.get_heartbeat(device=device)).total_seconds()) > 2*self.config['period']:
                # device claims to be active but hasn't heartbeated recently
                self.logger.warning(f'{device} hasn\'t heartbeated in {int(dt)} seconds, it\'s getting restarted')
                if device in self.last_restart and (now - self.last_restart[device]).total_seconds() < self.config['restart_timeout']:
                    self.logger.warning(f'Can\'t restart {device}, did so too recently')
                elif self.start_device(device):
                    # nonzero return code, probably something didn't work
                    self.logger.error(f'Problem starting {device}, check the debug logs')
                else:
                    self.logger.debug(f'{device} restarted')
            elif self.ping(device):
                self.logger.error(f'Failed to ping {device}, restarting it')
                self.start_device(device)
            else:
                # claims to be active and has heartbeated recently
                self.logger.debug(f'{device} last heartbeat {int(dt)} seconds ago')
            time.sleep(0.1)
        self.update_config(heartbeat=dtnow())
        return self.config['period']

    def ping(self, thing: str) -> bool:
        """
        Ping a listener. Returns True if it isn't listening and should be restarted
        """
        try:
            hn, p = self.db.find_listener_address(thing)
            with socket.create_connection((hn, p), timeout=0.1) as sock:
                sock.sendall(b'ping')
                if sock.recv(1024) != b'pong':
                    return True
        except Exception as e:
            self.logger.debug(f'Caught a {type(e)} while pinging {thing}: {e}')
            return True
        return False

    def send_remote_heartbeat(self) -> None:
        # touch a file on a remote server just so someone else knows we're still alive
        if (addr := self.config.get('remote_heartbeat', {}).get('address')) is not None:
            self.run_over_ssh(addr, r'date +%s > /scratch/remote_hb_'+self.db.experiment_name, port=self.config['remote_heartbeat'].get('port', 22))

    def check_remote_heartbeat(self) -> None:
        for p in os.listdir('/scratch/remote_hb_*'):
            with open(f'/scratch/{p}', 'r') as f:
                time_str = f.read().strip()
            if time.time() - int(time_str) > 3*60:
                # timestamp is too old, the other server is having problems
                self.db.log_alarm(msg=f"{p.split('_',maxsplit=2)[3]} hasn't heartbeated recently, maybe let someone know?")

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
        try:
            cp = subprocess.run(' '.join(cmd), shell=True, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired as e:
            self.logger.error(f'Command to {address} timed out!')
            return
        if cp.stdout:
            self.logger.debug(f'Stdout: {cp.stdout.decode()}')
        if cp.stderr:
            self.logger.debug(f'Stderr: {cp.stderr.decode()}')
        return cp.returncode

    def run_locally(self, command: str) -> int:
        """
        Some commands don't want to run via ssh?
        """
        cp = subprocess.run(command, shell=True, capture_output=True)
        if cp.stdout:
            self.logger.debug(f'Stdout: {cp.stdout.decode()}')
        if cp.stderr:
            self.logger.debug(f'Stderr: {cp.stderr.decode()}')
        return cp.returncode

    def start_device(self, device: str) -> int:
        path = self.config['path']
        doc = self.db.get_device_setting(device)
        host = doc['host']
        self.last_restart[device] = dtnow()
        self.update_config(manage=device)
        command = f"cd {path} && ./start_process.sh -d {device}"
        if host == self.localhost:
            return self.run_locally(command)
        return self.run_over_ssh(f'{self.username}@{host}', command)

    def compress_logs(self) -> None:
        then = dtnow()-datetime.timedelta(days=7)
        self.logger.info(f'Compressing logs from {then.year}-{then.month:02d}-{then.day:02d}')
        p = self.logger.handlers[0].logdir(dtnow()-datetime.timedelta(days=7))
        self.run_locally(f'cd {p} && gzip --best *.log')

    def dispatch(self) -> None:
        # if there's nothing to do, wait this long
        dt_large = 1000
        # process commands if we're within this much of the desired time
        min_dt = 0.001
        dt = dt_large
        predicate = lambda: (len(self.dispatch_queue) > 0 or self.event.is_set())
        self.logger.debug('Dispatcher starting up')
        while not self.event.is_set():
            doc = None
            hn = None
            try:
                with self.cv:
                    self.cv.wait_for(predicate, timeout=dt)
                    if len(self.dispatch_queue) > 0:
                        doc = self.dispatch_queue.get_front()
                        if (dt := (doc['time'] - time.time())) < min_dt:
                            doc = self.dispatch_queue.pop_front()
                    else:
                        dt = dt_large
                if doc is not None and dt < min_dt:
                    if doc['to'] == 'hypervisor':
                        self.process_command(doc['command'])
                        continue
                    if doc['to'] in self.known_devices and doc['to'] not in self.config['processes']['active']:
                        self.logger.warning(f'Can\'t send "{doc["command"]}" to {doc["to"]} because it isn\'t online')
                        continue
                    hn, p = self.db.find_listener_address(doc['to'])
                    self.logger.debug(f'Sending "{doc["command"]}" to {doc["to"]} at {hn}:{p}')
                    with socket.create_connection((hn, p), timeout=0.1) as sock:
                        sock.sendall(doc['command'].encode())
            except Exception as e:
                self.logger.warning(f'Dispatcher caught a {type(e)} while messaging {hn}: {e}')
        self.logger.debug('Dispatcher shutting down')

    def process_command(self, command: str) -> None:
        self.logger.debug(f'Processing {command}')
        if command[0] == '{':
            # a json document, this is for the dispatcher
            with self.cv:
                self.dispatch_queue.add(json.loads(command))
                self.cv.notify()
            return

        if command.startswith('start'):
            _, target = command.split(' ', maxsplit=1)
            self.logger.info(f'Hypervisor starting {target}')
            if target in self.known_devices:
                self.start_device(target)
            else:
                self.logger.error(f'Don\'t know what "{target}" is, can\'t start it')

        elif command.startswith('manage'):
            _, device = command.split(' ', maxsplit=1)
            if device not in self.known_devices:
                # unlikely but you can never trust users
                self.logger.error(f'Hypervisor can\'t manage {device}')
                return
            self.logger.info(f'Hypervisor now managing {device}')
            self.update_config(manage=device)

        elif command.startswith('unmanage'):
            _, device = command.split(' ', maxsplit=1)
            if device not in self.known_devices:
                # unlikely but you can never trust users
                self.logger.error(f'Hypervisor can\'t unmanage {device}')
                return
            self.logger.info(f'Hypervisor relinquishing control of {device}')
            self.update_config(unmanage=device)

        elif command.startswith('kill'):
            # I'm sure this will be useful at some point
            _, thing = command.split(' ', maxsplit=1)
            if thing in self.known_devices:
                host = self.db.get_device_setting(thing, field='host')
                self.run_over_ssh(host, f"screen -S {thing} -X quit")
            else:
                # assume it's running on localhost?
                self.run_over_ssh('localhost', f"screen -S {thing} -X quit")

        else:
            self.logger.error(f'Command "{command}" not understood')


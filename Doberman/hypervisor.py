import Doberman
import subprocess
import time
import os.path
import os
import threading
import json
import datetime
import zmq
from heapq import heappush, heappop


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

        self.last_pong = {}
        # start the three Pipeline monitors
        path = self.config['path']
        for thing in 'alarm control convert'.split():
            self.run_locally(f'cd {path} && ./start_process.sh --{thing}')
            self.last_pong[f'pl_{thing}'] = time.time()
            time.sleep(0.1)
        # now start the rest of the things
        self.known_devices = self.db.distinct('devices', 'name')
        self.cv = threading.Condition()
        self.dispatcher = threading.Thread(target=self.dispatch)
        self.dispatcher.start()  # TODO get this registered somehow
        self.broker_context = zmq.Context.instance()
        self.broker = threading.Thread(target=self.data_broker, args=(self.broker_context,))
        self.broker.start()
        self.register(obj=self.compress_logs, period=86400, name='log_compactor', _no_stop=True)
        rhbs = self.config.get('remote_heartbeat', {})
        for doc in rhbs.get('send', []):
            self.register(obj=self.send_remote_heartbeat, period=60, name='remote_heartbeat', _no_stop=True, config=doc)
        time.sleep(1)

        # start the fixed-frequency sync signals
        self.db.delete_documents('sensors', {'name': {'$regex': '^X_SYNC'}})
        periods = self.config.get('sync_periods', [5, 10, 15, 30, 60])
        for i in periods:
            if self.db.get_sensor_setting(name=f'X_SYNC_{i}') is None:
                self.db.insert_into_db('sensors', {'name': f'X_SYNC_{i}', 'description': 'Sync signal', 'readout_interval': i, 'status': 'offline', 'topic': 'other',
                    'subsystem': 'sync', 'pipelines': [], 'device': 'hypervisor', 'units': '', 'readout_command': ''})
        self.sync = threading.Thread(target=self.sync_signals, args=(periods,))
        self.sync.start()

        time.sleep(1)
        self.register(obj=self.hypervise, period=self.config['period'], name='hypervise', _no_stop=True)

    def shutdown(self) -> None:
        self.event.set()
        self.update_config(status='offline')
        self.dispatcher.join()
        self.broker_context.term()
        self.broker.join()
        self.sync.join()
        # shut down the pipeline monitors
        for thing in 'alarm control convert'.split():
            self.run_locally(f"screen -S pl_{thing} -X quit")
            self.update_config(deactivate=f'pl_{thing}')
            time.sleep(0.1)
        managed = self.config['processes']['managed']
        for device in managed:
            self.stop_device(device)
            time.sleep(0.05)

    def sync_signals(self, periods: list) -> None:
        ctx = zmq.Context.instance()
        socket = ctx.socket(zmq.PUB)
        host, ports = self.db.get_comms_info('data')
        socket.connect(f'tcp://{host}:{ports["send"]}')
        now = time.time()
        q = [(now+p, p) for p in sorted(periods)]
        while not self.event.is_set():
            self.event.wait(q[0][0]-time.time())
            _, p = heappop(q)
            now = time.time()
            socket.send_string(f'X_SYNC_{p} {now:.3f} 0')
            heappush(q, (now+p, p))

    def update_config(self, unmanage=None, manage=None, activate=None, deactivate=None, heartbeat=None, status=None) -> None:
        updates = {}
        if unmanage:
            updates['$pull'] = {'processes.managed': unmanage}
        if manage:
            updates['$addToSet'] = {'processes.managed': manage}
        if activate:
            updates['$addToSet'] = {'processes.active': activate}
        if deactivate:
            updates['$pull'] = {'processes.active': deactivate}
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
            if time.time()-self.last_pong.get(f'pl_{pl}', 100) > 30:
                self.logger.debug(f'Failed to ping pl_{pl}, restarting it')
                self.run_locally(f'cd {path} && ./start_process.sh --{pl}')

        for device in managed:
            if device not in active:
                self.logger.debug(f'{device} is managed but not active. I will start it.')
                # device isn't running and it's supposed to be
                if self.start_device(device):
                    self.logger.error(f'Problem starting {device}, check the debug logs')
            elif (dt := ((now := dtnow())-self.db.get_heartbeat(device=device)).total_seconds()) > 2*self.config['period']:
                # device claims to be active but hasn't heartbeated recently
                self.logger.warning(f'{device} hasn\'t heartbeated in {int(dt)} seconds, it\'s getting restarted')
                if self.start_device(device):
                    # nonzero return code, probably something didn't work
                    self.logger.error(f'Problem starting {device}, check the debug logs')
                else:
                    self.logger.debug(f'{device} restarted')
            elif time.time() - self.last_pong.get(device, 100) > 30:
                self.logger.error(f'Failed to ping {device}, restarting it')
                self.start_device(device)
            else:
                # claims to be active and has heartbeated recently
                self.logger.debug(f'{device} last heartbeat {int(dt)} seconds ago')
            time.sleep(0.1)
        self.update_config(heartbeat=dtnow())
        return self.config['period']

    def send_remote_heartbeat(self, config) -> None:
        # touch a file on a remote server just so someone else knows we're still alive
        numbers = []
        for doc in self.db.read_from_db('contacts', {'on_shift': True}):
            numbers.append(doc['sms'])
        if (addr := config.get('address')) is not None:
            directory = config.get('directory', '/scratch')
            self.run_over_ssh(addr,
                              r'date +%s > ' + directory + '/remote_hb_' + self.db.experiment_name,
                              port=config.get('port', 22))
            self.run_over_ssh(addr,
                              r'echo "' + ','.join(numbers) + '" >> ' + directory + '/remote_hb_' + self.db.experiment_name,
                              port=self.config['remote_heartbeat'].get('port', 22))

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
        except subprocess.TimeoutExpired:
            self.logger.error(f'Command to {address} timed out!')
            return -1
        if cp.stdout:
            self.logger.debug(f'Stdout: {cp.stdout.decode()}')
        if cp.stderr:
            self.logger.debug(f'Stderr: {cp.stderr.decode()}')
        time.sleep(1)
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
        time.sleep(1)
        return cp.returncode

    def start_device(self, device: str) -> int:
        path = self.config['path']
        doc = self.db.get_device_setting(device)
        host = doc['host']
        self.update_config(manage=device)
        command = f"cd {path} && ./start_process.sh -d {device}"
        if host == self.localhost:
            return self.run_locally(command)
        return self.run_over_ssh(f'{self.username}@{host}', command)

    def stop_device(self, device: str) -> int:
        doc = self.db.get_device_setting(device)
        host = doc['host']
        self.update_config(deactivate=device)
        command = f"screen -S {device} -X quit"
        if host == self.localhost:
            return self.run_locally(command)
        return self.run_over_ssh(f'{self.username}@{host}', command)

    def compress_logs(self) -> None:
        then = dtnow()-datetime.timedelta(days=7)
        self.logger.info(f'Compressing logs from {then.year}-{then.month:02d}-{then.day:02d}')
        p = self.logger.handlers[0].oh.get_logdir(dtnow()-datetime.timedelta(days=7))
        self.run_locally(f'cd {p} && gzip --best *.log')

    def data_broker(self, ctx) -> None:
        """
        This functions sets up the middle-man for the data-passing subsystem
        """
        incoming = ctx.socket(zmq.XSUB)
        outgoing = ctx.socket(zmq.XPUB)

        _, ports = self.db.get_comms_info('data')

        # ports seem backwards because they should be here and only here
        incoming.bind(f'tcp://*:{ports["send"]}')
        outgoing.bind(f'tcp://*:{ports["recv"]}')
        
        try:
            zmq.proxy(incoming, outgoing)
        except zmq.ContextTerminated:
            incoming.close()
            outgoing.close()

    def dispatch(self, ping_period=5) -> None:
        """
        This function handles the command-passing communication subsystem
        :param ping_period: how often do pings happen? Default 5 (seconds)
        """
        ctx = zmq.Context.instance()

        incoming = ctx.socket(zmq.REP)
        outgoing = ctx.socket(zmq.PUB)

        _, ports = self.db.get_comms_info('command')
        # send/recv seems backwards because it is here. we "recv" on the
        # line everyone else 'sends' on
        incoming.bind(f'tcp://*:{ports["send"]}')
        outgoing.bind(f'tcp://*:{ports["recv"]}')
        poller = zmq.Poller()
        poller.register(incoming, zmq.POLLIN)
        last_ping = time.time()
        queue = []
        cmd_ack = {}

        while not self.event.is_set():
            next_ping = last_ping + ping_period - time.time()
            next_command = queue[0][0] - time.time() if len(queue) > 0 else ping_period
            timeout_ms = min(next_ping, next_command) * 1000
            socks = dict(poller.poll(timeout=int(timeout_ms)))

            if (now := time.time()) - last_ping > ping_period or not len(socks):
                # one ping only
                outgoing.send_string("ping ")  # I think the space is necessary
                last_ping = now
            if socks.get(incoming) == zmq.POLLIN:
                msg = incoming.recv_string()
                incoming.send_string("")  # must reply
                if msg.startswith('pong'):
                    _, name = msg.split(' ')
                    self.last_pong[name] = now
                elif msg.startswith('{'):  # incoming external command
                    try:
                        doc = json.loads(msg)
                        heappush(queue, (float(doc['time']), doc['to'], doc['command']))
                    except Exception as e:
                        self.logger.debug(f'Caught a {type(e)} while processing. {e}')
                        self.logger.debug(msg)
                elif msg.startswith('ack'):  # command acknowledgement
                    _, name, cmd_hash = msg.split(' ')
                    try:
                        del cmd_ack[cmd_hash]
                    except KeyError:
                        self.logger.debug(f'Unknown hash from {name}: {cmd_hash}')
                    except Exception as e:
                        self.logger.debug(f'Caught a {type(e)}: {e}')
                        self.logger.debug(msg)
                else:
                    # Probably an internal command from a pipeline?
                    self.process_command(msg)
            if len(queue) > 0 and queue[0][0]-now < 0.001:
                _, to, cmd = heappop(queue)
                if to == 'hypervisor':
                    self.process_command(cmd)
                else:
                    cmd_hash = Doberman.utils.make_hash(now, to, cmd, hash_length=6)
                    outgoing.send_string(f'{to} {cmd_hash} {cmd}')
                    cmd_ack[cmd_hash] = (to, dtnow())
            pop = []
            for h, (n, t) in cmd_ack.items():
                if (waiting := (dtnow() - t).total_seconds()) > 5:
                    self.logger.warning(f"Command to {n} hasn't been ack'd in {waiting:.1f} sec")
                    pop.append(h)
            map(cmd_ack.pop, pop)

    def process_command(self, command: str) -> None:
        self.logger.debug(f'Processing {command}')
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
                self.run_locally(f"screen -S {thing} -X quit")

        else:
            self.logger.error(f'Command "{command}" not understood')


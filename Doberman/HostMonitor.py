import Doberman
import psutil
import datetime
from socket import getfqdn
import threading

dtnow = datetime.datetime.utcnow

__all__ = 'HostMonitor'.split()


class HostMonitor(Doberman.Monitor):
    """
    A Monitor subclass to monitor a host. Makes sure a host's sensors are always
    running
    """

    def setup(self):
        self.hostname = getfqdn()
        self.kafka = self.db.get_kafka("sysmon")
        self.sh = Doberman.utils.SignalHandler(self.logger, self.event)
        cfg = self.db.get_host_setting()
        self.db.set_host_setting(self.hostname, set={'status': 'online'})
        self.last_restart_times = {}
        swap = psutil.swap_memory()
        self.last_swap_in = swap.sin
        self.last_swap_out = swap.sout
        self.sysmon_timer = int(cfg['sysmon_timer'])
        self.disks = cfg['disks']
        self.last_read = {}
        self.last_write = {}
        disk_io = psutil.disk_io_counters(True)
        for disk in self.disks:
            self.last_read[disk] = disk_io[disk].read_bytes
            self.last_write[disk] = disk_io[disk].write_bytes
        self.nics = cfg['nics']
        net_io = psutil.net_io_counters(True)
        self.last_recv = {}
        self.last_sent = {}
        for nic in self.nics:
            self.last_recv[nic] = net_io[nic].bytes_recv
            self.last_sent[nic] = net_io[nic].bytes_sent
        self.register(obj=self.system_status, period=cfg['sysmon_timer'], name='sysmon')
        self.register(obj=self.heartbeat, period=cfg['heartbeat_timer'], name='heartbeat')

    def system_status(self):
        n_cpus = psutil.cpu_count()
        host = self.db.hostname
        load_1, load_5, load_15 = psutil.getloadavg()
        self.kafka(value=f'{host},load_1,{load_1 / n_cpus:.3g}')
        self.kafka(value=f'{host},load_5,{load_5 / n_cpus:.3g}')
        self.kafka(value=f'{host},load_15,{load_15 / n_cpus:.3g}')
        mem = psutil.virtual_memory()
        self.kafka(value=f'{host},mem_avail,{mem.available / mem.total:.3g}')
        swap = psutil.swap_memory()
        self.kafka(value=f'{host},swap_avail,{swap.percent:.3g}')
        socket = '0'
        temp_dict = psutil.sensors_temperatures()
        if 'coretemp' in temp_dict.keys():
            for row in temp_dict['coretemp']:
                if 'Package' in row.label:  # Fujitsu Intel core servers
                    socket = row.label[-1]  # max 10 sockets per machine
                    self.kafka(value=f'{host},cpu_{socket}_temp,{row.current:.3g}')
                else:
                    core = int(row.label.split(' ')[-1])
                    self.kafka(value=f'{host},cpu_{socket}_{core:02d}_temp,{row.current:.3g}')
        elif 'bcm2835_thermal' in temp_dict.keys():  # Revolution Pi
            self.kafka(value=f'{host},cpu_temp,{temp_dict["bcm2835_thermal"]["current"]:3g}')
        else:
            self.logger.debug(f'Couldn\'t read out CPU temperatures for {host}.')
        for i, row in enumerate(psutil.cpu_freq(True)):
            self.kafka(value=f'{host},cpu_{i:02d}_freq,{row.current:.3g}')
        net_io = psutil.net_io_counters(True)
        for nic, name in self.nics.items():
            recv_mbytes = (net_io[nic].bytes_recv - self.last_recv[nic]) >> 20
            self.last_recv[nic] = net_io[nic].bytes_recv
            self.kafka(value=f'{host},{name}_recv,{recv_mbytes / self.sysmon_timer:.3g}')
            sent_mbytes = (net_io[nic].bytes_sent - self.last_sent[nic]) >> 20
            self.last_sent[nic] = net_io[nic].bytes_sent
            self.kafka(value=f'{host},{name}_sent,{sent_mbytes / self.sysmon_timer:.3g}')
        disk_io = psutil.disk_io_counters(True)
        for disk, name in self.disks.items():
            read_mbytes = (disk_io[disk].read_bytes - self.last_read[disk]) >> 20
            self.last_read[disk] = disk_io[disk].read_bytes
            self.kafka(value=f'{host},{name}_read,{read_mbytes / self.sysmon_timer:.3g}')
            write_mbytes = (disk_io[disk].write_bytes - self.last_write[disk]) >> 20
            self.last_write[disk] = disk_io[disk].write_bytes
            self.kafka(value=f'{host},{name}_write,{write_mbytes / self.sysmon_timer:.3g}')

    def heartbeat(self):
        self.logger.debug("Heartbeat")
        self.db.update_heartbeat(host=self.hostname)
        host_cfg = self.db.get_host_setting()
        default = host_cfg['default']
        active = host_cfg['active']
        in_error = host_cfg['in_error']
        now = datetime.datetime.utcnow()
        other_hosts = self.db.distinct('common', 'hosts', 'hostname', cuts={'status': 'online'})
        other_hosts.remove(self.hostname)
        other_default = []
        for host in other_hosts:
            other_default.extend(self.db.get_host_setting(host, 'default'))
        for sensor in active:
            if sensor not in default:
                self.db.log_command({"command": "stop", "name": sensor, "logged": dtnow()})
                self.db.set_host_setting(pull={"active": sensor})
        for sensor in default:
            if sensor in other_default:
                self.logger.info(f'{sensor} is already dealt with by another online host monitor')
                self.db.set_host_setting(pull={"default": sensor})
                continue
            # all sensors in 'default' should be online
            if sensor not in active:
                # sensor isn't online
                if sensor in in_error:
                    # it has some already-acknowledged issue
                    self.logger.debug('%s has an acknowledged error' % sensor)
                    continue
                # isn't running? Start it
                try:
                    self.start_sensor(sensor)
                    self.db.set_host_setting(push={"active": sensor})
                except Exception as e:
                    self.logger.debug(f'Couldn\'t start {sensor}. {type(e)}: {e}')
                    self.db.set_host_setting(pull={"default": sensor})
                    self.db.set_host_setting(addToSet={"in_error": sensor})

            else:
                # sensor claims to be online, is it really?
                hb = self.db.get_heartbeat(sensor=sensor)
                if (now - hb).total_seconds() > 1.5 * host_cfg['heartbeat_timer']:
                    # hasn't heartbeated recently
                    self.logger.info(('%s hasn\'t heartbeated recently, '
                                      'let me try to restart it' % sensor))
                    self.start_sensor(sensor)
                    if sensor not in self.last_restart_times:
                        self.last_restart_times[sensor] = now
                    else:
                        dt = (now - self.last_restart_times[sensor]).total_seconds()
                        if dt < 3 * host_cfg['heartbeat_timer']:
                            if self.runmode == 'default':
                                doc = dict(name=self.hostname, howbad=1,
                                        msg='{sensor} has needed restarting twice within the last {dt} seconds, is it working properly?')
                                self.db.log_alarm(doc)
                            self.db.set_host_setting(pull={'active': sensor},
                                                     addToSet={'in_error': sensor})
                else:
                    # sensor has heartbeated recently
                    if sensor in in_error:
                        # clear a previous error
                        self.db.set_host_setting(pull={'in_error': sensor})
                    if sensor not in active:
                        self.db.set_host_setting(addToSet={'active': sensor})
        return host_cfg['heartbeat_timer']

    def start_sensor(self, sensor):
        self.db.set_host_setting(addToSet={'default': sensor})
        self.logger.info(f'Host monitor starting {sensor}')
        threading.Thread(target=Doberman.SensorMonitor, kwargs=dict(_name=sensor, db=self.db),
                         daemon=True).start()

    def handle_commands(self):
        doc = self.db.find_command(self.hostname)
        while doc is not None:
            cmd = doc['command']
            if cmd.startswith('start'):
                _, sensor = cmd.split(' ', maxsplit=1)
                self.start_sensor(sensor)
            elif cmd.startswith('heartbeat'):
                _, hb = cmd.split(' ', maxsplit=1)
                self.db.set_host_setting(set={'heartbeat_timer': float(hb)})
            elif cmd.startswith('stop'):
                self.close()
            else:
                self.logger.error(f'Command "{cmd}" not understood')
            doc = self.db.find_command(self.hostname)

    def shutdown(self):
        self.sh.run = False
        self.db.set_host_setting(self.name, set={'active': []})
        self.db.set_host_setting(self.name, set={'in_error': []})
        self.db.set_host_setting(self.name, set={'status': 'offline'})

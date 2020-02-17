import Doberman
import psutil
import datetime
from functools import partial

__all__ = 'HostMonitor'.split()


class HostMonitor(Doberman.Monitor):
    """
    A Monitor subclass to monitor a host. Makes sure a host's sensors are always
    running
    """

    def Setup(self):
        self.kafka = self.db.GetKafka("sysmon")
        cfg = self.db.GetHostSetting()
        self.last_restart_time = {}
        swap = psutil.swap_memory()
        self.last_swap_in = swap.sin
        self.last_swap_out = swap.sout
        self.sysmon_timer = cfg['sysmon_timer']
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
        self.Register(func=self.SystemStatus, period=cfg['sysmon_timer'], name='sysmon')
        self.Register(func=self.Hearbeat, period=cfg['heartbeat_timer'], name='heartbeat')

    def SystemStatus(self):
        n_cpus = psutil.cpu_count()
        host = self.db.hostname
        load_1, load_5, load_15 = psutil.getloadavg()
        self.kafka(value=f'{host},load_1,{load_1/n_cpus:.3g}')
        self.kafka(value=f'{host},load_5,{load_5/n_cpus:.3g}')
        self.kafka(value=f'{host},load_15,{load_15/n_cpus:.3g}')
        mem = psutil.virtual_memory()
        self.kafka(value=f'{host},mem_avail,{mem.available/mem.total:.3g}')
        swap = psutil.swap_memory()
        self.kafka(value=f'{host},swap_avail,{swap.percent:.3g}')
        socket = '0'
        for row in psutil.sensors_temperatures()['coretemp']:
            if 'Package' in row.label:
                socket = row.label[-1]  # max 10 sockets per machine
                self.kafka(value=f'{host},cpu_{socket}_temp,{row.current:.3g}')
            else:
                core = int(row.label.split(' ')[-1])
                self.kafka(value=f'{host},cpu_{socket}_{core:02d}_temp,{row.current:.3g}')
        for i,row in enumerate(psutil.cpu_freq(True)):
            self.kafka(value=f'{host},cpu_{i:02d}_freq,{row.current:.3g}')
        net_io = psutil.net_io_counters(True)
        for nic, name in self.nics.items():
            recv_mbytes = (net_io[nic].bytes_recv - self.last_recv[nic])>>20
            self.last_recv[nic] = net_io[nic].bytes_recv
            self.kafka(value=f'{host},{name}_recv,{recv_mbytes/self.sysmon_timer:.3g}')
            sent_mbytes = (net_io[nic].bytes_sent - self.last_sent[nic])>>20
            self.last_sent[nic] = net_io[nic].bytes_sent
            self.kafka(value=f'{host},{name}_sent,{sent_mbytes/self.sysmon_timer:.3g}')
        disk_io = psutil.disk_io_counters(True)
        for disk, name in self.disks.items():
            read_mbytes = (disk_io[disk].read_bytes - self.last_read[disk])>>20
            self.last_read[disk] = disk_io[disk].read_bytes
            self.kafka(value=f'{host},{name}_read,{read_mbytes/self.sysmon_timer:.3g}')
            write_mbytes = (disk_io[disk].write_bytes - self.last_write[disk])>>20
            self.last_write[disk] = disk_io[disk].write_bytes
            self.kafka(value=f'{host},{name}_write,{write_mbytes/self.sysmon_timer:.3g}')
        return

    def Heartbeat(self):
        self.db.UpdateHeartbeat(host=self.hostname)
        host_cfg = self.db.GetHostSetting()
        default = host_cfg['default']
        active = host_cfg['active']
        in_error = host_cfg['in_error']
        now = datetime.datetime.utcnow()
        for sensor in default:
            # all sensors in 'default' should be online
            if sensor not in active:
                # sensor is isn't online
                if sensor in in_error:
                    # it has some already-acknowledged issue
                    self.logger.debug('%s has an acknowledged error' % sensor)
                    continue
                # isn't running? Start it
                self.StartSensor(sensor)
            else:
                # sensor claims to be online, is it really?
                hb = self.db.GetHeartbeat(sensor=sensor)
                if (now - hb).total_seconds() > 1.5*host_cfg['heartbeat_timer']:
                    # hasn't heartbeated recently
                    self.logger.info(('%s hasn\'t heartbeated recently, '
                                      'let me try to restart it' % sensor))
                    self.db.SetSensorSetting(sensor, field='status', value='offline')
                    self.StartSensor(sensor)
                    if sensor not in self.last_restart_times:
                        self.last_restart_times[sensor] = now
                    else:
                        dt = (self.last_restart_times[sensor] - now).total_seconds()
                        if dt < 3*host_cfg['heartbeat_timer']:
                            doc = dict(name=self.hostname, howbad=0,
                                    msg=('%s has needed restarting twice within the last '
                                         '%d seconds, is it working properly?' %
                                         (sensor, dt)))
                            self.db.LogAlarm(doc)
                            self.db.SetHostSetting(pull={'active' : sensor},
                                                   push={'in_error' : sensor})
                else:
                    # sensor has heartbeated recently
                    if sensor in in_error:
                        # clear a previous error
                        self.db.SetHostInfo(pull={'in_error': sensor})
                    if sensor not in active:
                        self.db.SetHostInfo(push={'active' : sensor})
        # TODO add checks for LAN sensors running on other hosts
        return host_cfg['hearbeat_timer']

    def StartSensor(self, sensor):
        threading.Thread(target=Doberman.SensorMonitor, _name=sensor, db=self.db,
            daemon=True).start()

    def HandleCommands(self):
        doc = self.db.FindCommand(self.name)
        while doc is None:
            cmd = doc['command']
            if cmd.startswith('start'):
                _, sensor = cmd.split(' ', maxsplit=1)
                self.StartSensor(sensor)
            elif cmd.startswith('heartbeat'):
                _, hb = cmd.split(' ', maxsplit=1)
                self.db.SetHostSetting(set={'heartbeat_timer' : float(hb)})
            else:
                self.logger.error(f'Command "{cmd}" not understood')
            doc = self.db.FindCommand()

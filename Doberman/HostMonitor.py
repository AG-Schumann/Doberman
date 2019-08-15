import Doberman
import psutil
import datetime

__all__ = 'HostMonitor'.split()


class HostMonitor(Doberman.Monitor):
    """
    A Monitor subclass to monitor a host. Makes sure a host's sensors are always
    running
    """

    def Setup(self):
        self.Register(func=self.SystemStatus, period=60)
        self.Register(func=self.Hearbeat, period=Doberman.heartbeat_timer)
        self.last_restart_time = {}

    def SystemStatus(self):
        ret = {}
        ret['load_1'], ret['load_5'], ret['load_15'] = psutil.getloadavg()
        ret['mem_avail'] = psutil.virtual_memory().available >> 20
        ret['swap_used'] = psutil.swap_memory().used >> 20
        for row in psutil.sensors_temperatures()['coretemp']:
            if 'Package' in row.label:
                socket = row.label[-1]  # max 10 sockets per machine
                ret['cpu_0'] = row.current
            else:
                core = row.label.split(' ')[-1]
                ret[f'cpu_{socket}_{core}'] = row.current
        for i,row in enumerate(psutil.cpu_freq(True)):
            ret[f'cpu_{i}_freq'] = row.current
        # TODO something with ret

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
                        if dt > 3*host_cfg['heartbeat_timer']:
                            doc = dict(host=self.hostname, howbad=0,
                                    msg=('%s has needed restarting twice within the last '
                                         '%d seconds, is it working properly?' %
                                         (sensor, dt))
                            self.db.LogAlarm(doc)
                            self.db.SetHostSetting(pull={'active' : sensor},
                                                   push={'in_error' : sensor})
                else:
                    # sensor has heartbeated recently
                    if sensor in in_error:
                        # clear a previous error
                        self.db.SetHostInfo(pull={'in_error': sensor})
        # TODO add checks for LAN sensors running on other hosts
        return host_cfg['hearbeat_timer']

    def StartSensor(self, sensor):
        threading.Thread(target=Doberman.SensorMonitor, _name=sensor, db=db,
            autostart=True, daemon=True).start()

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

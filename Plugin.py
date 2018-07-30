import threading
import datetime
import time
import logging
import DobermanDB
import importlib
import importlib.machinery
import argparse
import DobermanLogger


def FindPlugin(name, path):
    spec = importlib.machinery.PathFinder.find_spec(name, path)
    if spec is None:
        raise FileNotFoundError('Could not find a controller named %s' % name)
    controller_ctor = getattr(spec.loader.load_module(), plugin_name)
    return controller_ctor

def clip(val, low, high):
    return max(min(val, high), low)

class Plugin(threading.Thread):
    """
    Class that controls starting, running, and stopping the readout thread
    Reads data from the controller, checks it for warnings/alarms, and writes
    to the database
    """

    def __init__(self, name, plugin_paths):
        """
        Does the controller interfacing and stuff
        """
        self.logger = logging.getLogger(name)
        self.name = name
        self.logger.debug('Starting...')
        self.db = DobermanDB.DobermanDB()
        config_doc = self.db.readFromDatabase('settings','controllers',
                {'name' : self.name}, onlyone=True)
        if self.name != 'RAD7':
            plugin_name = self.name.rstrip('0123456789')
        else:
            plugin_name = self.name

        self.controller_ctor = FindPlugin(plugin_name, plugin_paths)
        self.ctor_opts = {}
        self.ctor_opts['name'] = self.name
        self.ctor_opts['initialize'] = True
        self.ctor_opts.update(config_doc['address'])
        if 'additional_params' in config_doc:
            self.ctor_opts.update(config_doc['additional_params'])

        self.number_of_data = config_doc['number_of_data']
        self.recurrence_counter = [0] * self.number_of_data
        self.last_message_time = datetime.datetime.now()
        self.late_counter = 0
        self.last_measurement_time = datetime.datetime.now()
        self.controller = None
        self.OpenController()
        self.running = False
        super().__init__()
        self.Tevent = threading.Event()

    def close(self):
        self.logger.info('Stopping...')
        self.running = False
        self.Tevent.set()
        if self.controller:
            self.controller.close()
        self.controller = None
        return

    def OpenController(self):
        if self.controller is not None:
            return
        try:
            self.controller = self.controller_ctor(self.ctor_opts)
        except Exception as e:
            self.logger.error('Could not open controller')
            self.controller = None
            raise
        else:
            self._connected = True

    def run(self):
        self.OpenController()
        now = time.time()
        self.running = True
        while self.running:
            rundoc = self.db.readFromDatabase('settings','controllers',
                    {'name' : self.name}, onlyone=True)
            then = time.time()
            dt = now - then
            if dt < rundoc['readout_interval']:
                self.Tevent.wait(rundoc['readout_interval'] - dt)
            now = time.time()
            if self._connected:
                if rundoc['status'][rundoc['runmode']] == 'ON':
                    data = self.Readout()
                    if data['retcode'] in [-1,-2]: # connection lost
                        self._connected = False
                    self.ProcessData(data, rundoc)
            else:
                try:
                    self.OpenController()
                except:
                    pass
            for command in self.CheckCommands():
                if 'runmode' in command:
                    try:
                        _, runmode = command.split()
                    except ValueError:
                        self.logger.error("Could not understand command '%s'" % command)
                    else:
                        self.db.updateDatabase('settings','controllers',
                                {'name': self.name}, {'$set' : {'runmode' : runmode}})
                elif 'stop' in command:
                    self.running = False
                    # note that this will cause some issues when not in standalone mode
                elif self._connected:
                    self.controller.ExecuteCommand(command)
        self.close()

    def Readout(self):
        """
        Actually interacts with the device. Returns [time, data, status]
        Ensures data and status are lists
        """
        vals = self.controller.Readout()
        if vals['data'] not isinstance(vals['data'], (list, tuple)):
            vals['data'] = [vals['data']]
        if len(vals['data']) != self.number_of_data:
            vals['data'] += [None]*(self.number_of_data - len(vals['data']))
        if not isinstance(vals['retcode'], (list, tuple)):
            vals['retcode'] = [vals['retcode']]
        if len(vals['retcode']) != self.number_of_data:
            vals['retcode'] += [-3]*(self.number_of_data - len(vals['data']))
        upstream = [datetime.datetime.now(), vals['data'], vals['retcode']]
        self.logger.debug('Measured %s' % vals['data'])
        return upstream

    def ProcessData(self, data, rundoc):
        """
        Checks data for warning/alarms and writes it to the database
        """
        when, values, status = data
        runmode = rundoc['runmode']
        alarm_status = rundoc['alarm_status'][runmode]
        alarm_low = rundoc['alarm_low'][runmode]
        alarm_high = rundoc['alarm_high'][runmode]
        warning_low = rundoc['warning_low'][runmode]
        warning_high = rundoc['warning_high'][runmode]
        message_time = rundoc['message_time'][runmode]
        recurrence = rundoc['alarm_recurrence'][runmode]
        readout_interval = rundoc['readout_interval']
        dt = (datetime.datetime.now() - self.last_message_time).total_seconds()
        too_soon = (dt < message_time*60)
        for i in range(self.number_of_data):
            try:
                if alarm_status[i] != 'ON':
                    continue
                if status[i] < 0 and not too_soon:
                    msg = f'Something wrong? Status[{i}] is {status[i]}'
                    self.logger.warning(msg)
                    self.db.logAlarm({'name' : self.name, 'index' : i,
                        'when' : when, 'status' : status[i], 'data' : values[i],
                        'reason' : 'NC', 'howbad' : 1, 'msg' : msg})
                elif clip(values[i], alarm_low[i], alarm_high[i]) in \
                    [alarm_low[i], alarm_high[i]]:
                    self.recurrence_counter[i] += 1
                    status[i] = 2
                    if self.recurrence_counter[i] >= recurrence[i] and not too_soon:
                        msg = (f'Reading {i} ({self.description[i]}, '
                               f'{data[i]:.2f}) is outside the alarm range '
                                f'({alarm_low[i]:.2f}, {alarm_high[i]:.2f})')
                        self.logger.critical(msg)
                        self.db.logAlarm({'name' : self.name, 'index' : i,
                            'when' : when, 'status' : status[i], 'data' : values[i],
                            'reason' : 'A', 'howbad' : 2, 'msg' : msg})
                        self.recurrence_counter[i] = 0
                        self.last_message_time = now
                elif clip(values[i], warning_low[i], warning_high[i]) in \
                    [warning_low[i], warning_high[i]]:
                    self.recurrence_counter[i] += 1
                    status[i] = 1
                    if self.recurrence_counter[i] >= recurrence[i] and not too_soon:
                        msg = (f'Reading {i} ({self.description[i]}, '
                                f'{data[i]:.2f}) is outside the warning range '
                                f'({warning_low[i]:.2f}, {warning_high[i]:.2f})')
                        self.logger.warning(msg)
                        self.db.logAlarm({'name' : self.name, 'index' : i,
                            'when' : when, 'status' : status[i], 'data' : values[i],
                            'reason' : 'W', 'howbad' : 1, 'msg' : msg})
                        self.recurrence_counter[i] = 0
                        self.last_message_time = now
                else:
                    self.recurrence_counter[i] = 0
            except Exception as e:
                self.logger.critical(f'Could not check data[{i}]: {e}')
        if not self._connected:
            return
        time_diff = (when - self.last_measurement_time).total_seconds()
        if time_diff > 2*readout_interval:
            self.late_counter += 1
            if self.late_counter >= 3 and not too_soon:
                msg = f'{self.name} last sent data {time_diff:.1f} sec ago instead of {readout_interval}'
                self.logger.warning(msg)
                self.db.logAlarm({'name' : self.name, 'when' : now, 'status' : status,
                    'data' : data, 'reason' : 'TD', 'howbad' : 1})
                self.late_counter = 0
        else:
            self.late_counter = 0
        self.last_measurement_time = when
        self.db.writeDataToDatabase(self.name, when, values, status)
        # success is logged upstream

    def CheckCommands(self):
        """
        Pings the database for new commands for the controller, returns a list
        """
        doc_filter = {'name' : self.name, 'acknowledged' : {'$exists' : 0}}
        collection = self.db._check('logging','commands')
        while(collection.count_documents(doc_filter)):
            updates = {'$set' : {'acknowledged' : datetime.datetime.now()}}
            yield collection.find_one_and_update(doc_filter, updates)['command']

def main():
    parser = argparse.ArgumentParser(description='Doberman plugin standalone')
    parser.add_argument('--name', type=str, dest='plugin_name', required=True,
                        help='Name of the controller')
    parser.add_argument('--runmode', type=str, dest='runmode',
                        help='Which run mode to use', default='default')
    parser.add_argument('--log', type=int, choices=range(10,60,10), default=20,
                        help='Logging level')
    args = parser.parse_args()
    plugin_paths=['.']
    logging.getLogger(args.plugin_name)
    logging.addHandler(DobermanLogger.DobermanLogger())
    logging.setLevel(args.log)

    plugin = Plugin(args.plugin_name, plugin_paths)
    plugin.start()
    running = True
    time.sleep(5)
    try:
        while running:
            if not (plugin.running and plugin.is_alive()):
                self.logger.error('%s died! Restarting...' % plugin.name)
                try:
                    plugin.running = False
                    plugin.close()
                    plugin.join()
                    plugin.start()
                except Exception as e:
                    self.logger.critical('Could not restart %s' % plugin.name)
                    plugin.running = False
                    plugin.close()
                    plugin.join()
                    running = False
            time.sleep(30)
    except KeyboardInterrupt:
        self.logger.fatal('Killed by ctrl-c')
    finally:
        plugin.close()

    return

if __name__ == '__main__':
    main()

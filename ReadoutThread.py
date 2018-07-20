import threading
import datetime
import time
import logging
import DobermanDB
import importlib
import importlib.machinery
import argparse
import DobermanLogger


def clip(val, low, high):
    return max(min(val, high), low)

class Plugin(threading.Thread):
    """
    Class that controls starting, running, and stopping the readout thread
    Reads data from the controller, checks it for warnings/alarms, and writes
    to the database
    """

    def __init__(self, opts):
        """
        Does the controller interfacing and stuff
        """
        self.logger = logging.getLogger(opts.name)
        self.name = opts.name
        self.logger.debug('Starting %s' % self.name)

        if self.name != 'RAD7':
            plugin_name = self.name.rstrip('0123456789')
        else:
            plugin_name = self.name

        spec = importlib.machinery.PathFinder.find_spec(plugin_name, opts.plugin_paths)
        if spec is None:
            raise FileNotFoundError('Could not find a controller named %s' % plugin_name)
        try:
            self.controller_ctor = getattr(spec.loader.load_module(), plugin_name)
        except Exception as e:
            self.logger.critical('Could not load controller %s' % plugin_name)
            raise

        self.number_of_data = opts.number_of_data
        self.recurrence_counter = [0] * self.number_of_data
        self.last_message_time = datetime.datetime.now()
        self.last_measurement_time = datetime.datetime.now()
        self.readout_counter = 0
        self.db = DobermanDB.DobermanDB()
        self.controller_ctor = controller_ctor
        self.opts = opts
        self.controller = None
        self.OpenController()
        self.running = False
        super().__init__()
        self.Tevent = threading.Event()

    def close(self):
        self.logger.info('Stopping %s' % self.name)
        if self.controller:
            self.controller.close()
        self.controller = None
        self.Tevent.set()
        self.running = False
        return

    def OpenController(self):
        if self.controller:
            return
        try:
            self.controller = self.controller_ctor(self.opts)
        except Exception as e:
            self.logger.error('Could not open controller')
            self.controller = None
            raise

    def run(self):
        self.OpenController()
        then = time.time()
        now = time.time()
        collection = self.db._check('settings','controllers')
        while self.running:
            then = time.time()
            rundoc = collection.find_one({'name' : self.name})
            if rundoc['status'][rundoc['runmode']] == 'ON':
                data = self.Readout()
                self.ProcessData(data, rundoc)
                for command in self.CheckCommands():
                    self.controller.ExecuteCommand(command)
            now = time.time()
            dt = now - then
            # some measurements are slow
            if dt < rundoc['readout_interval']:
                self.Tevent.wait(rundoc['readout_interval'] - dt)
        self.close()

    def Readout(self):
        """
        Actually interacts with the device. Returns [time, data, status]
        Ensures data and status are lists
        """
        vals = self.controller.Readout()
        if vals['data'] is not None and not isinstance(vals['data'], (list, tuple)):
            vals['data'] = [vals['data']]
        if not isinstance(vals['retcode'], (list, tuple)):
            vals['retcode'] = [vals['retcode']]
        upstream = [datetime.datetime.now(), vals['data'], vals['retcode']]
        self.logger.debug('Measured %s' % vals['data'])
        return upstream

    def ProcessData(self, data, rundoc):
        """
        Checks data for warning/alarms and writes it to the database
        """
        when, values, status = data
        alarm_status = rundoc['alarm_status'][rundoc['runmode']]
        alarm_low = rundoc['alarm_low'][rundoc['runmode']]
        alarm_high = rundoc['alarm_high'][rundoc['runmode']]
        warning_low = rundoc['warning_low'][rundoc['runmode']]
        warning_high = rundoc['warning_high'][rundoc['runmode']]
        message_time = rundoc['message_time'][rundoc['runmode']]
        recurrence = rundoc['alarm_recurrence'][rundoc['runmode']]
        readout_interval = rundoc['readout_interval']
        now = datetime.datetime.now()
        for i in range(self.number_of_data):
            try:
                if alarm_status[i] != 'ON':
                    continue
                if status[i] < 0:
                    msg = 'Something wrong with %s? Status %i is %i' % (self.name,
                            i, status[i])
                    self.logger.warning(msg)
                    self.db.logAlarm({'name' : self.name, 'index' : i,
                        'when' : when, 'status' : status[i], 'data' : values[i],
                        'reason' : 'NC', 'howbad' : 1, 'msg' : msg})
                elif clip(values[i], alarm_low[i], alarm_high[i]) in \
                    [alarm_low[i], alarm_high[i]]:
                    self.recurrence_counter[i] += 1
                    status[i] = 2
                    if self.recurrence_counter[i] >= recurrence[i] and \
                            (now - self.last_message_time).total_seconds() >= message_time*60:
                        msg = (f'Reading {i} from {self.name} ({self.description[i]}, '
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
                    if self.recurrence_counter[i] >= recurrence[i] and \
                            (now - self.last_message_time).total_seconds() >= message_time*60:
                        msg = (f'Reading {i} from {self.name} ({self.description[i]}, '
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
                self.logger.critical('Could not check data %i from %s: %s' % (i, self.name, e))
        time_diff = (when - self.last_measurement_time).total_seconds()
        if time_diff > 2*readout_interval:
            msg = f'{self.name} last sent data {time_diff:.1f} sec ago instead of {readout_interval}'
            self.logger.warning(msg)
            self.db.logAlarm({'name' : self.name, 'when' : now, 'status' : status,
                'data' : data, 'reason' : 'TD', 'howbad' : 1})
        self.last_measurement_time = when
        self.db.writeDataToDatabase(self.name, when, values, status)
        # success is logged upstream

    def CheckCommands(self):
        """
        Pings the database for new commands for the controller, returns a list
        """
        doc_filter = {'name' : self.name}
        projection = {'_id' : 1, 'command' : 1}
        collection = self.db._check('logging','commands')
        if collection.count_documents(doc_filter):
            for doc in collection.find(doc_filter, projection):
                yield doc['command']
                self.command_collection.delete_one({'_id' : doc['_id']})
        else:
            return []

def main():
    raise NotImplementedError('Too soon...')
    parser = argparse.ArgumentParser(description='Doberman plugin standalone')
    parser.add_argument('--name', type=str, dest='plugin_name', required=True,
                        help='Name of the controller')
    parser.add_argument('--runmode', type=str, dest='runmode',
                        help='Which run mode to use', default='default')
    parser.add_argument('--log', type=int, choices=range(10,60,10), default=20,
                        help='Logging level')
    args = parser.parse_args()

    logging.getLogger(args.plugin_name)
    logging.addHandler(DobermanLogger.DobermanLogger())
    return

if __name__ == '__main__':
    main()

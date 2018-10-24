#!/usr/bin/env python3
import threading
import datetime
import time
import logging
import DobermanDB
import argparse
import DobermanLogging
import utils
dtnow = datetime.datetime.now


def clip(val, low, high):
    """Clips `val` to be at least `low` and at most `high`"""
    return max(min(val, high), low)

class Plugin(threading.Thread):
    """
    Class that controls starting, running, and stopping the readout thread
    Reads data from the controller, checks it for warnings/alarms, and writes
    to the database.
    """

    def __init__(self, db, name, plugin_paths):
        """
        Constructor

        Parameters
        ----------
        db : DobermanDB instance
            The database backend connection
        name : str
            The name of the plugin/controller to use
        plugin_paths : list
            A list of directories in which to find plugins

        Returns
        -------
        None

        Raises
        ------
        None
        """
        threading.Thread.__init__(self)
        self.logger = logging.getLogger(name)
        self.name = name
        self.logger.debug('Starting plugin...')
        self.db = db
        config_doc = self.db.readFromDatabase('settings','controllers',
                {'name' : self.name}, onlyone=True)
        self.controller_ctor = utils.FindPlugin(self.name, plugin_paths)
        self.ctor_opts = {}
        self.ctor_opts['name'] = self.name
        self.ctor_opts['initialize'] = True
        self.ctor_opts.update(config_doc['address'])
        if 'additional_params' in config_doc:
            self.ctor_opts.update(config_doc['additional_params'])

        self.number_of_data = len(config_doc['readings'])
        self.recurrence_counter = [0] * self.number_of_data
        self.status_counter = [0] * self.number_of_data
        self.last_message_time = dtnow()
        self.late_counter = 0
        self.last_measurement_time = dtnow()
        self.controller = None
        self.OpenController()
        self.running = False
        self.has_quit = False

    def close(self):
        """Closes the controller"""
        self.running = False
        if not self.controller:
            return
        self.logger.info('Stopping...')
        self.controller.close()
        self.controller = None
        return

    def OpenController(self):
        """Tries to call the controller constructor. Raises any exceptions recieved"""
        if self.controller is not None:
            return
        try:
            self.controller = self.controller_ctor(self.ctor_opts)
        except Exception as e:
            self.logger.error('Could not open controller. Error: %s' % e)
            self.controller = None
            raise
        else:
            self._connected = True

    def run(self):
        """
        The main readout loop of the plugin. Ensures it always has a controller to read
        data from. If it doesn't it tries periodically to open it.
        While running, pulls data from the controller, checks its validity, checks for
        new commands, and repeats until told to quit. Closes the controller when finished

        Parameters
        ----------
        None

        Returns
        -------
        None

        Raises
        ------
        None
        """
        self.OpenController()
        self.running = True
        while self.running:
            loop_start_time = time.time()
            rundoc = self.db.readFromDatabase('settings','controllers',
                    {'name' : self.name}, onlyone=True)
            if rundoc['status'][rundoc['runmode']] == 'ON':
                if self._connected:
                    data = self.Readout()
                    if -1 in data[2] or -2 in data[2]: # connection lost
                        self._connected = False
                        self.logger.error('Lost connection to device?')
                    self.ProcessData(data, rundoc)
                else:
                    try:
                        self.logger.debug('Reopening controller...')
                        self.OpenController()
                    except Exception as e:
                        self.logger.error('Could not reopen controller! Error %s | %s' % (type(e), e))
                    else:
                        self.logger.debug('Reopened controller')
            self.HandleCommands()
            while (time.time() - loop_start_time) < rundoc['readout_interval'] and self.running:
                time.sleep(1)
                self.HandleCommands()
        self.close()

    def Readout(self):
        """
        Actually interacts with the device. Returns [time, data, status]
        Ensures data and status are lists

        Parameters
        ---------
        None

        Returns
        -------
        time : datetime.datetime
            When the data was recorded
        data : list
            The values read from the controller. Has length self.number_of_data, will
            be padded with None if necessary
        status : list
            The status codes returned by the controller. Has length self.number_of_data,
            will be padded with -3 if necessary

        Raises
        ------
        None
        """
        vals = self.controller.Readout()
        if not isinstance(vals['data'], (list, tuple)):
            vals['data'] = [vals['data']]
        if len(vals['data']) != self.number_of_data:
            vals['data'] += [None]*(self.number_of_data - len(vals['data']))
        if not isinstance(vals['retcode'], (list, tuple)):
            vals['retcode'] = [vals['retcode']]
        if len(vals['retcode']) != self.number_of_data:
            vals['retcode'] += [-3]*(self.number_of_data - len(vals['data']))
        upstream = [dtnow(), vals['data'], vals['retcode']]
        self.logger.debug('Measured %s' % list(map('{:.2g}'.format, vals['data'])))
        return upstream

    def ProcessData(self, data, rundoc):
        """
        Checks data for warning/alarms and writes it to the database

        Paramaters
        ----------
        data : [time, values, status]
            The quantity returned by Readout() above

        rundoc : dict
            The controller's settings document from the database, that contains all the
            current parameters (alarm levels, etc) for operation

        Returns
        -------
        None

        Raises
        ------
        None
        """
        when, values, status = data
        runmode = rundoc['runmode']
        message_time = self.db.getDefaultSettings(runmode=runmode,name='message_time')
        readout_interval = rundoc['readout_interval']
        readings = rundoc['readings']
        dt = (dtnow() - self.last_message_time).total_seconds()
        too_soon = (dt < message_time*60)
        for i, (value, reading) in enumerate(zip(values, readings)):
            level = reading['level'][runmode]
            try:
                if level == -1:
                    continue
                if status[i] < 0:
                    self.status_counter[i] += 1
                    if self.status_counter[i] >= 3 and not too_soon:
                        msg = f'Something wrong? Status[{i}] is {status[i]}'
                        self.logger.warning(msg)
                        self.db.logAlarm({'name' : self.name, 'index' : i,
                            'when' : when, 'status' : status[i], 'data' : value,
                            'reason' : 'status', 'howbad' : 0, 'msg' : msg})
                        self.status_counter[i] = 0
                        self.last_message_time = dtnow()
                else:
                    self.status_counter[i] = 0

                for j in range(len(reading['alarms'])-1, level-1, -1):
                    lo, hi = reading['alarms'][j]
                    if clip(value, lo, hi) in [lo, hi]:
                        self.recurrence_counter[i] += 1
                        status[i] = j
                        if self.recurrence_counter[i] >= reading['recurrence'] and not too_soon:
                            msg = (f"Reading {i} ({reading['description']}, value "
                               f'{value:.2g}) is outside the level {j} alarm range '
                               f'({lo:.2g}, {hi:.2g})')
                            self.logger.critical(msg)
                            self.db.logAlarm({'name' : self.name, 'index' : i,
                                'when' : when, 'status' : status[i], 'data' : value,
                                'reason' : 'alarm', 'howbad' : j, 'msg' : msg})
                            self.recurrence_counter[i] = 0
                            self.last_message_time = dtnow()
                        break
                else:
                    self.recurrence_counter[i] = 0
            except Exception as e:
                self.logger.critical(f"Could not check reading {i} ({reading['description']}): {e} ({str(type(e))}")
        if not self._connected:
            return
        time_diff = (when - self.last_measurement_time).total_seconds()
        if time_diff > 2*readout_interval:
            self.late_counter += 1
            if self.late_counter >= 3 and not too_soon:
                msg = f'Last sent data {time_diff:.1f} sec ago instead of {readout_interval}'
                self.logger.warning(msg)
                self.db.logAlarm({'name' : self.name, 'when' : dtnow(), 'status' : 0,
                    'data' : time_diff, 'reason' : 'time difference', 'howbad' : 0,
                    'msg' : msg})
                self.late_counter = 0
        else:
            self.late_counter = 0
        self.last_measurement_time = when
        self.db.writeDataToDatabase(self.name, when, values, status)
        # success is logged upstream

    def HandleCommands(self):
        """
        Pings the database for new commands for the controller

        Parameters
        ----------
        None

        Returns
        ------
        None

        Raises
        ------
        None
        """
        doc = self.db.FindCommand(self.name)
        while doc is not None:
            command = doc['command']
            self.logger.info(f"Found command '{command}'")
            if 'runmode' in command:
                _, runmode = command.split()
                self.db.updateDatabase('settings','controllers',
                                {'name': self.name}, {'$set' : {'runmode' : runmode}})
                loglevel = self.db.getDefaultSettings(runmode=runmode,name='loglevel')
                self.logger.setLevel(int(loglevel))
            elif command == 'stop':
                self.running = False
                self.has_quit = True
                # makes sure we don't get restarted
            elif command == 'wake':
                runmode = self.db.ControllerSettings(name=self.name)['runmode']
                self.db.updateDatabase('settings','controllers', {'name' : self.name},
                        {'$set' : {'status.%s' % runmode : 'ON'}})
            elif command == 'sleep':
                runmode = self.db.ControllerSettings(name=self.name)['runmode']
                self.db.updateDatabase('settings','controllers', {'name' : self.name},
                        {'$set' : {'status.%s' % runmode : 'OFF'}})
            elif self._connected:
                self.controller.ExecuteCommand(command)
            else:
                self.logger.error(f"Command '{command}' not accepted")
            doc = self.db.FindCommand(self.name)
        return

def main(db):
    names = db.Distinct('settings','controllers','name')
    runmodes = db.Distinct('settings','runmodes','mode')
    parser = argparse.ArgumentParser(description='Doberman plugin standalone')
    parser.add_argument('--name', type=str, dest='plugin_name', required=True,
                        help='Name of the controller',choices=names)
    parser.add_argument('--runmode', type=str, dest='runmode', choices=runmodes,
                        help='Which run mode to use', default='default')
    args = parser.parse_args()

    plugin_paths=['.']
    logger = logging.getLogger(args.plugin_name)
    logger.addHandler(DobermanLogging.DobermanLogger(db))
    loglevel = db.getDefaultSettings(runmode=args.runmode,name='loglevel')
    logger.setLevel(int(loglevel))
    doc = db.readFromDatabase('settings','controllers',
            {'name' : args.plugin_name},onlyone=True)
    if doc['online']:
        logger.fatal('%s already running!' % args.plugin_name)
        return
    db.updateDatabase('settings','controllers',{'name' : args.plugin_name},
            {'$set' : {'runmode' : args.runmode, 'online' : True}})
    logger.info('Starting %s' % args.plugin_name)
    plugin = Plugin(db, args.plugin_name, plugin_paths)
    plugin.start()
    sh = utils.SignalHandler(logger)
    running = True
    try:
        while running and not sh.interrupted:
            loop_start = time.time()
            logger.debug('I\'m still here')
            while time.time() - loop_start < 30 and not sh.interrupted:
                time.sleep(1)
            if plugin.has_quit:
                logger.info('Plugin stopped')
                break
            if not (plugin.running and plugin.is_alive()):
                logger.error('Controller died! Restarting...' % plugin.name)
                try:
                    plugin.running = False
                    plugin.join()
                    plugin = Plugin(db, args.plugin_name, plugin_paths)
                    plugin.start()
                except Exception as e:
                    logger.critical('Could not restart: %s | %s' % (type(e), e))
                    plugin.running = False
                    plugin.join()
                    running = False
    except Exception as e:
        logger.fatal(f'Why did I catch a {type(e)} here? {e}')
    finally:
        db.updateDatabase('settings','controllers',{'name' : args.plugin_name},
                {'$set' : {'online' : False}})
        plugin.running = False
        plugin.join()
        logger.info('Shutting down')

    return

if __name__ == '__main__':
    db = DobermanDB.DobermanDB()
    try:
        main(db)
    except:
        pass
    db.close()


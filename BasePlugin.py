#!/usr/bin/env python3
import threading
import datetime
import time
import logging
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
        config_doc = self.db.ControllerSettings(self.name)
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
        self.logger.debug('Started')

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
        self.logger.debug('Running...')
        while self.running:
            loop_start_time = time.time()
            configdoc = self.db.ControllerSettings(self.name)
            if configdoc['status'] == 'online':
                self.Readout(configdoc)
            self.HandleCommands()
            while (time.time() - loop_start_time) < configdoc['readout_interval'] and self.running:
                self.KillTime(configdoc)
        self.close()

    def KillTime(self, configdoc):
        """
        Kills time while waiting for the main readout loop timer
        """
        time.sleep(1)
        self.HandleCommands()
        return

    def Readout(self, configdoc):
        """
        Actually interacts with the device.

        Parameters
        ---------
        configdoc:
            The configuration document from the database

        Returns
        -------
        None

        Raises
        ------
        None
        """
        if self._connected:
            vals = self.controller.Readout()
            if not isinstance(vals['data'], (list, tuple)):
                vals['data'] = [vals['data']]
            if len(vals['data']) != self.number_of_data:
                vals['data'] += [None]*(self.number_of_data - len(vals['data']))
            if not isinstance(vals['retcode'], (list, tuple)):
                vals['retcode'] = [vals['retcode']]
            if len(vals['retcode']) != self.number_of_data:
                vals['retcode'] += [-3]*(self.number_of_data - len(vals['data']))
            data = [dtnow(), vals['data'], vals['retcode']]
            try:
                self.logger.debug('Measured %s' % (list(map('{:.3g}'.format, vals['data']))))
            except:
                pass
            if -1 in data[2] or -2 in data[2]: # connection lost
                self._connected = False
                self.logger.error('Lost connection to device?')
            self.ProcessData(data, configdoc)
        else:
            try:
                self.logger.debug('Reopening controller...')
                self.OpenController()
            except Exception as e:
                self.logger.error('Could not reopen controller! Error %s | %s' % (type(e), e))
            else:
                self.logger.debug('Reopened controller')
        return

    def ProcessData(self, data, configdoc):
        """
        Checks data for warning/alarms and writes it to the database

        Paramaters
        ----------
        data : [time, values, status]
            The quantity returned by Readout() above

        configdoc : dict
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
        runmode = configdoc['runmode']
        message_time = self.db.getDefaultSettings(runmode=runmode,name='message_time')
        readout_interval = configdoc['readout_interval']
        readings = configdoc['readings']
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
                               f'{value:.3g}) is outside the level {j} alarm range '
                               f'({lo:.3g}, {hi:.3g})')
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
                self.logger.critical(f"Could not check reading {i} ({reading['description']}): {e} ({str(type(e))})")
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
            if command.startswith('runmode'):
                _, runmode = command.split()
                self.db.updateDatabase('settings','controllers', {'name': self.name},
                        {'$set' : {'runmode' : runmode}})
                loglevel = self.db.getDefaultSettings(runmode=runmode,name='loglevel')
                self.logger.setLevel(int(loglevel))
            elif command == 'stop':
                self.running = False
                self.has_quit = True
                # makes sure we don't get restarted
            elif command == 'wake':
                self.db.updateDatabase('settings','controllers', {'name' : self.name},
                        {'$set' : {'status' : 'online'}})
            elif command == 'sleep':
                self.db.updateDatabase('settings','controllers', {'name' : self.name},
                        {'$set' : {'status' : 'sleep'}})
            elif self._connected:
                self.controller.ExecuteCommand(command)
            else:
                self.logger.error(f"Command '{command}' not accepted")
            doc = self.db.FindCommand(self.name)
        return


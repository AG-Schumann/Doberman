#!/usr/bin/env python3
import threading
import datetime
import time
import logging
import utils
import queue
dtnow = datetime.datetime.now


def clip(val, low, high):
    """Clips `val` to be at least `low` and at most `high`"""
    return max(min(val, high), low)

class Plugin(threading.Thread):
    """
    Class that controls starting, running, and stopping the readout thread
    Reads data from the sensor, checks it for warnings/alarms, and writes
    to the database.
    """

    def __init__(self, db, name, plugin_paths):
        """
        Constructor for the main Plugin class

        :param db: an instance of the database api
        :param name: the name of the sensor to run
        :param plugin_paths: a list of paths to search for the driver
        """
        threading.Thread.__init__(self)
        self.logger = logging.getLogger(name)
        self.name = name
        self.logger.debug('Starting plugin...')
        self.db = db
        config_doc = self.db.GetSensorSettings(self.name)
        self.sensor_ctor = utils.FindPlugin(self.name, plugin_paths)
        self.ctor_opts = utils.SensorOpts(config_doc)
        self.status_counter = {}
        self.recurrence_counter = {}
        self.last_message_time = dtnow()
        self.late_counter = 0
        self.last_measurement_time = time.time()
        self.sensor = None
        self.OpenSensor()
        self.has_quit = False
        self.reading_names = config_doc['readings']
        self.readout_threads = {}
        self.process_queue = queue.Queue()
        self.buffer_thread = None
        self.buffer_lock = threading.RLock()
        self.buffer = []
        self.sh = utils.SignalHandler(self.logger)
        self.logger.debug('Started')

    def close(self):
        """Closes the sensor"""
        self.logger.debug('Beginning shutdown')
        self.sh.interrupted = True
        for t in self.readout_threads.values():
            t.join()
        self.readout_threads = {}
        if self.buffer_thread is not None:
            self.buffer_thread.join()
            self.buffer_thread = None
        if not self.sensor:
            return
        self.sensor.close()
        self.sensor = None
        self.logger.info('Stopping...')
        return

    def OpenSensor(self, reopen=False):
        """Tries to call the sensor constructor. Raises any exceptions recieved"""
        self.logger.debug('Connecting to sensor')
        if self.sensor is not None and not reopen:
            self.logger.debug('Already connected!')
            return
        if reopen:
            self.logger.debug('Attempting reconnect')
            self.controller.running = False
            self.controller.close()
        try:
            self.sensor = self.sensor_ctor(self.ctor_opts)
            self.sensor._Setup()
        except Exception as e:
            self.logger.error('Could not open sensor. Error: %s' % e)
            self.sensor = None
            raise
        else:
            self._connected = True

    def run(self):
        """
        The main readout loop of the plugin. Ensures it always has a sensor to read
        data from. If it doesn't it tries to open it. If it fails, it returns.
        While running, pulls data the process queue and process it. Also checks for
        new commands, and repeats until told to quit. Closes the sensor when finished
        """
        self.OpenSensor()
        self.buffer_thread = threading.Thread(target=self.Bufferer)
        self.buffer_thread.start()
        for name in self.reading_names:
            t = threading.Thread(target=self.ReadoutLoop, args=(name, ))
            t.start()
            self.readout_threads[name] = t
            time.sleep(0.1)
        self.logger.debug('Running...')
        while not self.sh.interrupted:
            self.KillTime()
        self.close()

    def KillTime(self):
        """
        Kills time while waiting for the main readout loop timer
        """
        time.sleep(1)
        self.HandleCommands()
        return

    def Bufferer(self):
        """
        Empties the buffer into the database periodically
        """
        self.logger.debug('Bufferer starting')
        while not self.sh.interrupted:
            loop_start_time = time.time()
            with self.buffer_lock:
                if len(self.buffer):
                    doc = dict(self.buffer)
                    self.logger.debug('%i readings, %i values' % (len(doc), len(self.buffer)))
                    self.db.WriteDataToDatabase(self.name, doc)
                    self.buffer = []
                else:
                    self.logger.debug('No data in buffer')
            sleep_until = loop_start_time + utils.buffer_timer
            now = time.time()
            while now < sleep_until and not self.sh.interrupted:
                time.sleep(min(1, sleep_until-now))
                now = time.time()
        self.logger.debug('Bufferer returning')

    def ReadoutLoop(self, reading_name):
        """
        A loop that puts readout commands into the Sensor's readout queue

        :param reading_name: the name of the reading that this loop handles
        """
        self.logger.debug('Loop "%s" starting' % reading_name)
        while not self.sh.interrupted:
            loop_start_time = time.time()
            reading = self.db.GetReading(sensor=self.name, name=reading_name)
            if reading['readout_interval'] <= 0:
                break
            if reading['status'] == 'online' and self._connected:
                self.sensor.AddToSchedule(reading_name=reading_name,
                                          callback=self.ProcessReading)
            sleep_until = loop_start_time + reading['readout_interval']
            now = time.time()
            while not self.sh.interrupted and now < sleep_until:
                time.sleep(min(1, sleep_until - now))
                now = time.time()
        self.logger.debug('Loop "%s" returning' % reading_name)

    def ProcessReading(self, rd_name, value, retcode):
        """
        Checks data for warning/alarms and writes it to the database

        :param rd_name: the name of the reading to process
        :param value: the value the sensor returns
        :param retcode: the status code the sensor returns
        """
        self.logger.debug('Processing (%s %s %i)' % (rd_name, value, retcode))
        reading = self.db.GetReading(self.name, rd_name)
        runmode = reading['runmode']
        if rd_name not in self.status_counter:
            self.status_counter[rd_name] = 0
            self.recurrence_counter[rd_name] = 0
        message_time = self.db.getDefaultSettings(runmode=runmode, name='message_time')
        readout_interval = reading['readout_interval']
        dt = (dtnow() - self.last_message_time).total_seconds()
        too_soon = (dt < message_time*60)
        alarm_level = reading['config'][runmode]['level']
        alarm_ranges = reading['alarms']
        if retcode < 0:
            try:
                self.logger.error('Lost connection to device?')
                self._connected = False
                self.OpenSensor(reopen=True)
            except Exception as e:
                self.logger.critical('Could not reconnect')
                try:
                    self._connected = False
                    self.sensor.running = False
                    self.sensor.close()
                except:
                    pass
                finally:
                    self.sensor = None
                    self.sh.interrupted = True
                    return
            else:
                self.logger.info('Successfully reconnected')
            self.status_counter[rd_name] += 1
            if self.status_counter[rd_name] >= 3 and not too_soon:
                msg = f'Something wrong? Status {index} is {retcode}'
                self.logger.warning(msg)
                self.db.logAlarm({'name' : self.name, 'reading' : rd_name,
                            'when' : when, 'status' : retcode,
                            'reason' : 'status', 'howbad' : 0, 'msg' : msg})
                self.status_counter[rd_name] = 0
                self.last_message_time = dtnow()
        else:
            self.status_counter[rd_name] = 0
        if alarm_level > -1:
            try:
                levels_to_check = list(range(alarm_level, len(alarm_ranges)))[::-1]
                for j in levels_to_check:
                    lo, hi = alarm_ranges[j]
                    if clip(value, lo, hi) in [lo, hi]:
                        self.recurrence_counter[rd_name] += 1
                        if self.recurrence_counter[rd_name] >= reading['recurrence'] and not too_soon:
                            msg = (f"Reading {rd_name} ({reading['description']}, value "
                               f'{value:.3g}) is outside the level {j} alarm range '
                               f'({lo:.3g}, {hi:.3g})')
                            self.logger.warning(msg)
                            self.db.logAlarm({'name' : self.name, 'reading' : rd_name,
                                'when' : dtnow(), 'data' : value,
                                'reason' : 'alarm', 'howbad' : j, 'msg' : msg})
                            self.recurrence_counter[rd_name] = 0
                            self.last_message_time = dtnow()
                    break
                else:
                    self.recurrence_counter[rd_name] = 0
            except Exception as e:
                self.logger.error(f"Could not check reading {rd_name} "
                    f"({reading['description']}): {e} ({str(type(e))})")
        if value is None:
            return
        time_diff = time.time() - self.last_measurement_time
        if time_diff > 1.5*max(reading['readout_interval'], utils.heartbeat_timer):
            self.late_counter += 1
            if self.late_counter >= 2 and not too_soon:
                msg = f'Sensor responding slowly?'
                self.logger.warning(msg)
                self.db.logAlarm({'name' : self.name, 'when' : dtnow(),
                        'data' : time_diff, 'reason' : 'time difference',
                        'howbad' : 0, 'msg' : msg})
                self.late_counter = 0
        else:
            self.late_counter = 0
        self.last_measurement_time = time.time()
        with self.buffer_lock:
            self.buffer.append((rd_name, value))
        return

    def HandleCommands(self):
        """
        Pings the database for new commands for the sensor and deals with them
        """
        doc = self.db.FindCommand(self.name)
        while doc is not None:
            command = doc['command']
            self.logger.info(f"Found command '{command}'")
            if command.startswith('runmode'):
                _, runmode = command.split()
                self.db.SetSensorSetting(self.name, 'runmode', runmode)
                loglevel = self.db.getDefaultSettings(runmode=runmode,name='loglevel')
                self.logger.setLevel(int(loglevel))
            elif command == 'stop':
                self.sh.interrupted = True
                self.has_quit = True
                # makes sure we don't get restarted
            elif command == 'wake':
                self.db.SetSensorSetting(self.name, 'status', 'online')
            elif command == 'sleep':
                self.db.SetSensorSetting(self.name, 'status', 'sleep')
            elif self._connected:
                self.sensor.ExecuteCommand(command)
            else:
                self.logger.error(f"Command '{command}' not accepted")
            doc = self.db.FindCommand(self.name)
        return


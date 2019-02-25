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
        self.ctor_opts = {}
        self.ctor_opts['name'] = self.name
        self.ctor_opts['initialize'] = True
        self.ctor_opts.update(config_doc['address'])
        if 'additional_params' in config_doc:
            self.ctor_opts.update(config_doc['additional_params'])

        self.recurrence_counter = [0] * len(config_doc['readings'])
        self.status_counter = [0] * len(config_doc['readings'])
        self.runmode = config_doc['runmode']
        self.last_message_time = dtnow()
        self.late_counter = 0
        self.last_measurement_time = time.time()
        self.sensor = None
        self.OpenSensor()
        self.running = False
        self.has_quit = False
        self.readings = config_doc['readings']
        self.readout_threads = []
        self.process_queue = queue.Queue()
        self.reading_lock = threading.RLock()
        self.sh = utils.SignalHandler(self.logger)
        self.logger.debug('Started')

    def close(self):
        """Closes the sensor"""
        self.logger.debug('Beginning shutdown')
        self.running = False
        for t in self.readout_threads:
            t.join()
        if not self.sensor:
            return
        self.sensor.close()
        self.sensor = None
        self.logger.info('Stopping...')
        return

    def OpenSensor(self):
        """Tries to call the sensor constructor. Raises any exceptions recieved"""
        if self.sensor is not None:
            return
        try:
            self.sensor = self.sensor_ctor(self.ctor_opts)
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
        self.running = True
        for i in range(len(self.readings)):
            self.readout_threads.append(threading.Thread(
                target=self.ReadoutLoop,
                args=(i,)))
            self.readout_threads[-1].start()
            time.sleep(0.1)
        self.logger.debug('Running...')
        while self.running and not self.sh.interrupted:
            self.logger.debug('Top of main loop')
            loop_start_time = time.time()
            with self.reading_lock:
                configdoc = self.db.GetSensorSettings(self.name)
                self.readings = configdoc['readings']
                self.runmode = configdoc['runmode']
            self.HandleCommands()
            while (time.time() - loop_start_time) < utils.heartbeat_timer and self.running:
                try:
                    packet = self.process_queue.get_nowait()
                except queue.Empty:
                    pass
                else:
                    while packet is not None:
                        if packet[3] < 0:
                            self._connected = False
                            self.logger.error('Lost connection to device?')
                            try:
                                self.sensor.close()
                                self.sensor = None
                                self.OpenSensor()
                            except:
                                self.logger.fatal('Could not reconnect!')
                                try:
                                    self.sensor.close()
                                except:
                                    pass
                                finally:
                                    self.sensor = None
                                    self.running = False
                                    break
                            else:
                                self.logger.info('Reconnected successfully')

                        self.ProcessReading(*packet)
                        try:
                            self.logger.debug('Queue at %i' % self.process_queue.qsize())
                            packet = self.process_queue.get_nowait()
                        except queue.Empty:
                            packet = None
                        else:
                            continue
                self.KillTime()
                if self.sh.interrupted:
                    break
        self.close()

    def KillTime(self):
        """
        Kills time while waiting for the main readout loop timer
        """
        time.sleep(1)
        self.HandleCommands()
        return

    def ReadoutLoop(self, i):
        """
        A loop that puts readout commands into the Sensor's readout queue

        :param i: the index of the reading that this loop handles
        """
        while self.running and not self.sh.interrupted:
            loop_start_time = time.time()
            with self.reading_lock:
                reading = self.readings[i]
                runmode = self.runmode
            sleep_until = loop_start_time + reading['readout_interval']
            if reading['config'][runmode]['active'] and self._connected:
                self.sensor.AddToSchedule(reading_index=i,
                        callback=self.process_queue.put)
            now = time.time()
            while self.running and not self.sh.interrupted and now < sleep_until:
                time.sleep(min(1, sleep_until - now))
                now = time.time()
        self.logger.debug('Loop %i returning' % i)

    def ProcessReading(self, index, timestamp, value, retcode):
        """
        Checks data for warning/alarms and writes it to the database

        :param index: the index of the reading to process
        :param timestamp: unix timestamp of when the value was recorded
        :param value: the value the sensor returns
        :param retcode: the status code the sensor returns
        """
        self.logger.debug('Processing (%i %s %i)' % (index, value, retcode))
        runmode = self.runmode
        reading = self.readings[index]
        message_time = self.db.getDefaultSettings(runmode=runmode,name='message_time')
        readout_interval = reading['readout_interval']
        dt = (dtnow() - self.last_message_time).total_seconds()
        too_soon = (dt < message_time*60)
        alarm_level = reading['config'][runmode]['level']
        alarm_ranges = reading['alarms']
        if alarm_level > -1:
            if retcode < 0:
                self.status_counter[index] += 1
                if self.status_counter[index] >= 3 and not too_soon:
                    msg = f'Something wrong? Status {index} is {retcode}'
                    self.logger.warning(msg)
                    self.db.logAlarm({'name' : self.name, 'index' : index,
                            'when' : when, 'status' : retcode,
                            'reason' : 'status', 'howbad' : 0, 'msg' : msg})
                    self.status_counter[index] = 0
                    self.last_message_time = dtnow()
            else:
                self.status_counter[index] = 0
            try:
                levels_to_check = list(range(alarm_level, len(alarm_ranges)))[::-1]
                for j in levels_to_check:
                    lo, hi = alarm_ranges[j]
                    if clip(value, lo, hi) in [lo, hi]:
                        self.recurrence_counter[index] += 1
                        if self.recurrence_counter[index] >= reading['recurrence'] and not too_soon:
                            msg = (f"Reading {index} ({reading['description']}, value "
                               f'{value:.3g}) is outside the level {j} alarm range '
                               f'({lo:.3g}, {hi:.3g})')
                            self.logger.critical(msg)
                            self.db.logAlarm({'name' : self.name, 'index' : index,
                                'when' : dtnow(), 'data' : value,
                                'reason' : 'alarm', 'howbad' : j, 'msg' : msg})
                            self.recurrence_counter[index] = 0
                            self.last_message_time = dtnow()
                    break
                else:
                    self.recurrence_counter[index] = 0
            except Exception as e:
                self.logger.critical(f"Could not check reading {index} ({reading['description']}): {e} ({str(type(e))})")
        if value is None:
            return
        time_diff = timestamp - self.last_measurement_time
        if time_diff > 3*reading['readout_interval']:
            self.late_counter += 1
            if self.late_counter >= 3 and not too_soon:
                msg = f'Sensor responding slowly?'
                self.logger.warning(msg)
                self.db.logAlarm({'name' : self.name, 'when' : dtnow(),
                        'data' : time_diff, 'reason' : 'time difference',
                        'howbad' : 0, 'msg' : msg})
                self.late_counter = 0
        else:
            self.late_counter = 0
        self.last_measurement_time = timestamp
        collection_name = '%s__%s' % (self.name, reading['name'])
        when = datetime.datetime.fromtimestamp(timestamp)
        self.db.writeDataToDatabase(collection_name, when, value)

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
                self.running = False
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


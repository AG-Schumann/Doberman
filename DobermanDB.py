#!/usr/bin/env python3
import logging
import datetime
import pymongo
import utils
import json
import argparse
import os
import time
import re  # EVERYBODY STAND BACK xkcd.com/208
dtnow = datetime.datetime.now


class DobermanDB(object):
    """
    Class to handle interfacing with the Doberman database
    """

    def __init__(self, appname):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.appname = appname
        # Load database connection details
        try:
            conn_str = os.environ['connection_uri']
        except KeyError:
            try:
                with open(os.path.join(utils.doberman_dir, 'connection_uri'), 'r') as f:
                    conn_str = f.read().rstrip()
            except Exception as e:
                print("Can not load database connection details. Error %s" % e)
                raise
        try:
            self.experiment_name = os.environ['experiment_name']
        except KeyError:
            try:
                with open(os.path.join(utils.doberman_dir, 'experiment_name'), 'r') as f:
                    self.experiment_name = f.read().strip()
            except Exception as e:
                print("Cannot load experiment name. %s: %s" % (type(e), str(e)))

        self.client = None
        self._connect(conn_str)

    def close(self):
        if self.client is not None:
            self.client.close()
            self.client = None

    def __del__(self):
        self.close()
        return

    def __exit__(self):
        self.close()
        return

    def _connect(self, conn_str):
        if self.client is not None:
            return
        self.client = pymongo.MongoClient(conn_str, appname=self.appname, w=1)

    def _check(self, db_name, collection_name):
        """
        Returns the requested collection and logs if the database or
        collection don't yet exist. If the collection must be
        created, it adds an index onto the 'when' field (used for logs,
        alarms, data, etc)

        :param db_name: the name of the database
        :param collection_name: the name of the collections
        :returns collection instance of the requested collection.
        """
        if not hasattr(self, 'experiment_name'):
            raise ValueError('I don\'t know what experiment to look for')
        db_name = self.experiment_name + '_' + db_name
        #if db_name not in self.client.list_database_names():
        #    self.logger.debug('Database %s doesn\'t exist yet, creating it...' % db_name)
        if collection_name not in self.client[db_name].list_collection_names(False):
            self.logger.debug('Collection %s not in database %s, creating it...' % (collection_name, db_name))
            self.client[db_name].create_collection(collection_name)
            if 'data' in db_name:
                self.client[db_name][collection_name].create_index([('when',-1)])
        return self.client[db_name][collection_name]

    def insertIntoDatabase(self, db_name, collection_name, document, **kwargs):
        """
        Inserts document(s) into the specified database/collection

        :param db_name: name of the database
        :param collection_name: name of the collection
        :param document: a dictionary or iterable of dictionaries
        :param **kwargs: any keyword args, passed to collection.insert_(one|many)
        :returns 0 if successful, -1 if a multiple insert failed, -2 if a single
        insert failed, or 1 if `document` has the wrong type
        """
        collection = self._check(db_name, collection_name)
        if isinstance(document, (list, tuple)):
            result = collection.insert_many(document, **kwargs)
            if len(result.inserted_ids) != len(document):
                self.logger.error('Inserted %i entries instead of %i into %s/%s' % (
                    len(result.inserted_ids), len(document), db_name, collection_name))
                return -1
            return 0
        elif isinstance(document, dict):
            result = collection.insert_one(document, **kwargs)
            if result.acknowledged:
                return 0
            else:
                return -2
        else:
            self.logger.error('Not sure what to do with %s type' % type(document))
            return 1

    def readFromDatabase(self, db_name, collection_name, cuts={}, onlyone = False, **kwargs):
        """
        Finds one or more documents that pass the specified cuts

        :param db_name: name of the database
        :param collection_name: name of the collection
        :param cuts: dictionary of the query to apply. Default {}
        :param onlyone: bool, if only one document is requested
        :param **kwargs: keyword args passed to collection.find. The 'sort' kwarg
        is handled separately because otherwise it doesn't do anything
        :returns document if onlyone=True else cursor
        """
        collection = self._check(db_name,collection_name)
        cursor = collection.find(cuts, **kwargs)
        if 'sort' in kwargs:
            cursor.sort(kwargs['sort'])
        if onlyone:
            for doc in cursor:
                return doc
        else:
            return cursor

    def updateDatabase(self, db_name, collection_name, cuts, updates, **kwargs):
        """
        Updates documents that meet pass the specified cuts

        :param db_name: name of the database
        :param collection_name: name of the collection
        :param cuts: the dictionary specifying the query
        :param updates: the dictionary specifying the desired changes
        :param **kwargs: keyword args passed to collection.update_many
        :returns 0 if successful, 1 if not
        """
        collection = self._check(db_name, collection_name)
        ret = collection.update_many(cuts, updates, **kwargs)
        if not ret.acknowledged:
            return 1
        return 0

    def DeleteDocuments(self, db_name, collection_name, cuts):
        """
        Deletes documents from the specified collection

        :param db_name: name of the database
        :param collection_name: name of the collection
        :param cuts: dictionary specifying the query
        :returns None
        """
        collection = self._check(db_name, collection_name)
        collection.delete_many(cuts)

    def GetData(self, name, start_time, index, end_time=None):
        """
        This function basically exists to support the PID loop. Returns a
        numpy-structurable array of (timestamp, value) between start_time
        and end_time, for the specified data index. 'Timestamp' is a float
        of time since epoch

        :param name: the name of the plugin to get data for
        :param start_time: python Datetime instance of the earliest time to fetch
        :param index: which entry in the data array you want
        :param end_time: python Datetime instance of the latest time to fetch

        Returns [(timestamp, value), (timestamp, value), ...]
        """
        query = {'when' : {'$gte' : start_time}}
        coll_name = "%s__%s" % (name,
                self.GetSensorSettings(name)['readings'][index]['name'])
        if end_time is not None:
            query['when'].update({'$lte' : end_time})
        sort = [('when', 1)]
        b = []
        for row in self.readFromDatabase('data', coll_name, query, sort=sort):
            b.append((row['when'].timestamp(), row['data']))
        return b

    def Distinct(self, db_name, collection_name, field, cuts={}, **kwargs):
        """
        Transfer function for collection.distinct
        """
        return self._check(db_name, collection_name).distinct(field, cuts, **kwargs)

    def Count(self, db_name, collection_name, cuts, **kwargs):
        """
        Transfer function for collection.count/count_documents
        """
        return self._check(db_name, collection_name).count_documents(cuts, **kwargs)

    def FindOneAndUpdate(self, db_name, collection_name, cuts, updates, **kwargs):
        """
        Finds one document and applies updates. A bit of a special implementation so
        the 'sort' kwarg will actually do something

        :param db_name: name of the database
        :param collection_name: name of the collection
        :param cuts: a dictionary specifying the query
        :param updates: a dictionary specifying the updates
        :**kwargs: keyword args passed to readFromDatabase
        :returns document
        """
        doc = self.readFromDatabase(db_name, collection_name, cuts, onlyone=True, **kwargs)
        if doc is not None:
            self.updateDatabase(db_name, collection_name, {'_id' : doc['_id']}, updates)
        return doc

    def FindCommand(self, name):
        """
        Finds the oldest unacknowledged command for the specified entity
        and updates it as acknowledged. Deletes command documents used in
        the feedback subsystem

        :param name: the entity to find a command for
        :returns command document
        """
        now = dtnow()
        doc = self.FindOneAndUpdate('logging', 'commands',
                cuts={'name' : name,
                      'acknowledged' : {'$exists' : 0},
                      'logged' : {'$lte' : now}},
                updates={'$set' : {'acknowledged' : now}},
                sort=[('logged',1)])
        if doc and 'by' in doc and doc['by'] == 'feedback':
            self.DeleteDocuments('logging', 'commands', {'_id' : doc['_id']})
        return doc

    def getMessageProtocols(self, level):
        """
        Gets message protocols for the specified alarm level. If none are found,
        takes those from the next lowest level.

        :param level: which alarm level is in question (0, 1, etc)
        :returns: list of message protocols to use
        """
        doc = self.readFromDatabase('settings','alarm_config', {'level' : level}, onlyone=True)
        if doc is None:
            self.logger.error('No message protocols for alarm level %i! Defaulting to next lowest level' % level)
            doc = self.readFromDatabase('settings','alarm_config',
                    {'level' : {'$lte' : level}}, onlyone=True,
                    sort=[('level', -1)])
        return doc['protocols']

    def getContactAddresses(self, level):
        """
        Returns a list of addresses to contact at 'level'

        :param level: which alarm level the message will be sent at
        :returns dict, keys = message protocols, values = list of addresses
        """
        protocols = self.getMessageProtocols(level)
        ret = {k : [] for k in protocols}
        for doc in self.readFromDatabase('settings','contacts',
                {'status' : {'$gte' : 0, '$lte' : level}}):
            for p in protocols:
                ret[p].append(doc[p])
        return ret

    def Heartbeat(self, name):
        """
        Heartbeats the specified sensor (or doberman)

        :param name: the name of the heartbeat to update
        """
        if name == 'doberman':
            cuts={}
            coll = 'current_status'
        else:
            cuts={'name' : name}
            coll = 'sensors'
        self.updateDatabase('settings', coll, cuts=cuts,
                    updates={'$set' : {'heartbeat' : dtnow()}})
        return

    def CheckHeartbeat(self, name):
        """
        Checks the heartbeat of the specified sensor.

        :param name: the name of the sensor to check
        :returns: number of seconds since the last heartbeat
        """
        doc = self.GetSensorSettings(name=name)
        last_heartbeat = doc['heartbeat']
        return (dtnow() - last_heartbeat).total_seconds()

    def PrintHelp(self, name):
        print('Accepted commands:')
        print('help [<plugin_name>]: help [for specific plugin]')
        print('start <plugin_name> [<runmode>]: starts a plugin [in the specified runmode]')
        print('stop <plugin_name>: stops a plugin')
        print('restart <plugin_name>: restarts a plugin')
        print('runmode <runmode>: changes the active runmode')
        print('sleep <duration>: puts Doberman to sleep for specified duration (5m, 6h, etc)')
        print('wake: reactivates Doberman')
        print()
        print('Available plugins:')
        names = self.Distinct('settings','sensors','name')
        print(' | '.join(names))
        print()
        print('Plugin commands:')
        print('<plugin_name> sleep <duration>: puts the specified plugin to sleep for the specified duration')
        print('<plugin_name> wake: reactivates the specified plugin')
        print('<plugin_name> runmode <runmode>: changes the active runmode for the specified sensor')
        print()
        if name:
            print('Commands specific to %s:' % name)
            snsr_cls = utils.FindPlugin(name, ['.'])
            if not hasattr(snsr_cls, 'accepted_commands'):
                print('none')
            else:
                for row in snsr_cls.accepted_commands:
                    print(row)
        print()
        print('Plugin name == "all" issues the command to applicable plugins. Context-aware.')
        print()
        print('Available runmodes:')
        runmodes = self.Distinct('settings','runmodes','mode')
        print(' | '.join(runmodes))
        print()
        return

    def ProcessCommandStepOne(self, command_str, user=None):
        """
        Does the regex matching for command input

        :param command_str: the string as received from the command line
        :param external_user: a dict of info from the web interface
        """
        names = self.Distinct('settings','sensors','name')
        names_ = '|'.join(names + ['all'])
        runmodes_ = '|'.join(self.Distinct('settings','runmodes','mode'))
        if command_str.startswith('help'):
            n = None
            if len(command_str) > len('help '):
                name = command_str[len('help '):]
                if name in names:
                    n = name
            self.PrintHelp(n)
            return

        patterns = [
            '^(?P<command>start|stop|restart) (?P<name>%s)(?: (?P<runmode>%s))?' % (names_, runmodes_),
            '^(?:(?P<name>%s) )?(?P<command>sleep|wake)(?: (?P<duration>(?:[1-9][0-9]*[dhms])|(?:inf)))?' % names_,
            '^(?:(?P<name>%s) )?(?P<command>runmode) (?P<runmode>%s)' % (names_, runmodes_),
            '^(?P<name>%s) (?P<command>.+)$' % names_,
        ]
        for pattern in patterns:
            m = re.search(pattern, command_str)
            if m:
                self.ProcessCommandStepTwo(m, user=user)
                break
        else:
            print('Command \'%s\' not understood' % command_str)

    def ProcessCommandStepTwo(self, m, user=None):
        """
        Takes the match object (m) from StepOne and figures out what it actually means
        """
        command = m['command']
        name = str(m['name'])
        if self.getDefaultSettings(name='status') == 'sleep':
            if command != 'wake' and name != 'None':
                print('System currently in sleep mode, command not accepted')
                return
        if command == 'sleep' and name == 'None':
            if len(self.getDefaultSettings(name='managed_plugins')) > 0:
                print('Can\'t sleep while managing plugins!')
                return
        names = {'None' : ['doberman']}
        if name != 'None':
            names.update({name : [name]})
        online = self.Distinct('settings','sensors','name', {'status' : 'online'})
        offline = self.Distinct('settings','sensors','name', {'status' : 'offline'})
        asleep = self.Distinct('settings','sensors','name', {'status' : 'sleep'})
        if command in ['start', 'stop', 'restart', 'sleep', 'wake', 'runmode']:
            names.update({'all' : {
                'start' : offline,
                'stop' : online,
                'restart' : online,
                'sleep' : online,
                'wake' : asleep,
                'runmode' : online}[command]})
        if command == 'start':
            for n in names[name]:
                self.ProcessCommandStepThree('doberman', 'start %s %s' % (n, m['runmode']), user=user)
        elif command == 'stop':
            for n in names[name]:
                self.ProcessCommandStepThree(n, 'stop', user=user)
        elif command == 'restart':
            td = datetime.timedelta(seconds=1.1*utils.heartbeat_timer)
            for n in names[name]:
                self.ProcessCommandStepThree(n, 'stop', user=user)
                self.ProcessCommandStepThree('doberman', 'start %s None' % n, td, user=user)
        elif command == 'sleep':
            duration = m['duration']
            if duration is None:
                print('Can\'t sleep without specifying a duration!')
            elif duration == 'inf':
                for n in names[name]:
                    self.ProcessCommandStepThree(n, 'sleep')
            else:
                howmany = int(duration[:-1])
                which = duration[-1]
                time_map = {'s' : 'seconds', 'm' : 'minutes', 'h' : 'hours', 'd' : 'days'}
                kwarg = {time_map[which] : howmany}
                sleep_time = datetime.timedelta(**kwarg)
                for n in names[name]:
                    self.ProcessCommandStepThree(n, 'sleep', user=user)
                    self.ProcessCommandStepThree(n, 'wake', sleep_time, user=user)
        elif command == 'wake':
            for n in names[name]:
                self.ProcessCommandStepThree(n, 'wake', user=user)
        elif command == 'runmode':
            for n in names[name]:
                self.ProcessCommandStepThree(n, 'runmode %s' % m['runmode'], user=user)
        else:
            self.ProcessCommandStepThree(name, command, user=user)

    def ProcessCommandStepThree(self, name, command, future=None, user=None):
        """
        Puts a command into the database

        :param name: the name of the entity the command is for
        :param command: the command to be issued
        :param future: a timedelta instance of how far into the future the
        command should be handled, default None
        :param user: the info about an external user
        """
        command_doc = {'name' : name, 'command' : command, 'logged' : dtnow()}
        if user is None:
            user = {
                    'client_addr' : '127.0.0.1',
                    'client_host' : 'localhost',
                    'client_name' : os.environ['USER']
                    }
        command_doc.update(user)
        if future is not None:
            command_doc['logged'] += future
        self.insertIntoDatabase('logging','commands', command_doc)
        print(f'Stored "{command}" for {name}')
        return

    def logAlarm(self, document):
        """
        Adds the alarm to the history.
        """
        if self.insertIntoDatabase('logging','alarm_history',document):
            self.logger.warning('Could not add entry to alarm history!')
            return -1
        return 0

    def LogUpdate(self, **kwargs):
        """
        Logs changes submitted from the website
        """
        self.insertIntoDatabase('logging', 'updates', kwargs)
        return

    def GetSensorSettings(self, name):
        """
        Reads the settings in the database.

        :param name: the name of the sensor
        :returns: configuration document for the specified sensor
        """
        return self.readFromDatabase('settings', 'sensors', cuts={'name' : name},
                onlyone=True)

    def GetSensorSetting(self, sensor_name, field):
        """
        Gets a specific setting from one sensor

        :param sensor_name: the name of the sensor
        :param field: the field you want
        :returns: the value of the named field
        """
        doc = self.GetSensorSettings(sensor_name)
        return doc[field]

    def GetReading(self, sensor=None, name=None):
        """
        Gets the document from one reading

        :param sensor: the name of the sensor
        :param name: the name of the reading
        :returns: reading document
        """
        return self.readFromDatabase('settings', 'readings',
                cuts={'sensor' : sensor, 'name' : name}, onlyone=True)

    def UpdateReading(self, sensor=None, name=None, field=None, value=None):
        """
        Updates a parameter for a reading

        :param sensor: the name of the sensor
        :param name: the name of the reading
        :param field: the specific field to update
        :param value: the new value
        """
        self.updateDatabase('settings', 'readings',
                cuts={'sensor' : sensor, 'name' : name},
                updates={'$set' : {field : value}})

    def SetSensorSetting(self, name, field, value):
        """
        Updates the setting from one sensor

        :param name: the name of the sensor
        :param field: the specific field to update
        :param value: the new value
        """
        self.updateDatabase('settings', 'sensors', cuts={'name' : name},
                updates = {'$set' : {field : value}})

    def getDefaultSettings(self, runmode=None, name=None):
        """
        Reads default Doberman settings from database.

        :param runmode: the runmode to get settings for
        :param name: the name of the setting
        :returns: the setting dictionary if name=None, otherwise the specific field
        """
        if runmode:
            doc = self.readFromDatabase('settings','runmodes',
                    {'mode' : runmode}, onlyone=True)
            if name:
                return doc[name]
            return doc
        doc = self.readFromDatabase('settings','current_status', onlyone=True)
        if name:
            return doc[name]
        return doc

    def ManagePlugins(self, name, action):
        """
        Adds or removes a plugin from the managed list. Doberman adds, plugins remove

        :param name: the name of the plugin
        :param action: 'add' or 'remove'
        :returns: None
        """
        managed_plugins = self.getDefaultSettings(name='managed_plugins')
        if action=='add':
            if name in managed_plugins:
                self.logger.info('%s already managed' % name)
            else:
                self.updateDatabase('settings','current_status',cuts={},
                        updates={'$push' : {'managed_plugins' : name}})
        elif action=='remove':
            if name not in managed_plugins:
                self.logger.debug('%s isn\'t managed' % name)
            else:
                self.updateDatabase('settings','current_status',cuts={},
                        updates={'$pull' : {'managed_plugins' : name}})
        return

    def updateContacts(self):
        """
        Allows a command-line user to update active contacts
        """
        contacts = [c for c in self.readFromDatabase('settings','contacts')]
        existing_numbers = list(map(str, range(len(contacts))))
        # Print informations
        print('\n' + 60 * '-' + '\n')
        print('  - No string signs (") needed.\n  '
              '- Enter n for no change')
        print('Status = -1 -> contact is not responsible')
        print('Lower status numbers mean more messages')
        print('\n' + 60 * '-' +
              '\n  Saved contacts are:\n  (Name, Status)\n')
        if contacts == -1:
            self.logger.error("Could not load contacts.")
            return -1
        for i, contact in enumerate(contacts):
            print('(%i) %s:\t%i' % (i, contact['name'], contact['status']))
        print('\n' + 60 * '-' + '\n')

        # Change contact
        text = "Enter the number of the contact you would like to update: "
        num = utils.getUserInput(text,
                                 input_type=[int],
                                 be_in=range(len(contacts)))
        contact = contacts[num]
        name = contact['name']
        # Status
        text = ("Enter new status level of %s (or n for no change). " % name)
        status = utils.getUserInput(text, input_type=[int],
            exceptions=['n'])
        if status != 'n':
            if self.updateDatabase('settings','contacts',
                    cuts={'name' : contact['name']},
                    updates={'$set' : {'status' : status}}):
                self.logger.error('Could not update contact!')
                return -1
            print('Done!')
        print()
        return 0

    def WriteDataToDatabase(self, sensor_name, data_doc):
        """
        Writes data to the database

        :param sensor_name: the name of the sensor
        :param data_doc: the document with data
        :returns 0 on success, -1 otherwise
        """
        ret = self.insertIntoDatabase('data', sensor_name, data_doc)
        if ret:
            self.logger.warning("Can not write data from %s to Database. "
                                "Database interaction error." % sensor_name)
            return -1
        return 0

    def askForUpdates(self):
        """
        Allows a command-line user to update settings
        """
        which = ''
        to_quit = ['q','Q','n']
        while which not in to_quit:
            print('What do you want to update?')
            print(' contacts | sensors')
            print('(use q, Q, or n to quit)')
            which = input('>>> ')
            if which == 'contacts':
                self.updateContacts()
            elif which == 'sensors':
                print('Feature removed')
                #self.updateAlarms()
            elif which not in to_quit:
                print('Invalid input: %s' % which)
        return

    def addContact(self):
        """
        Allows a command-line user to add a new contact
        """
        print('Here are the contacts currently available:')
        print('\n'.join(self.Distinct('settings','contacts','name')))
        print('\n\n')
        print('New contact:')
        firstname = input('First name: ')
        lastname = input('Last name: ')
        sms = input('sms: ')
        email = input('email: ')
        status = '-1'
        if self.insertIntoDatabase('settings','contacts',{'name' : firstname + lastname[0],
            'sms' : sms, 'email' : email, 'status' : status}):
            print('Could not add contact!')
        return

    def addSensor(self, filename):
        """
        Adds a new sensor to the system
        """
        with open(filename, 'r') as f:
            try:
                d = json.load(f)
            except Exception as e:
                print('Could not read file! Error: %s' % e)
                return
            if 'heartbeat' not in d:
                d.update({'heartbeat' : dtnow()})
            if 'status' not in d:
                d.update({'status' : 'offline'})
            if self.insertIntoDatabase('settings','sensors',d):
                print('Could not add sensor!')
            else:
                print('Sensor added')
        return

    def GetCurrentStatus(self):
        """
        Gives a snapshot of the current system status
        """
        status = {}
        now = dtnow()
        for sensor_doc in self.readFromDatabase('settings','sensors'):
            sensor_name = sensor_doc['name']
            #if 'Test' in sensor_name:
            #    continue
            status[sensor_name] = {
                    'status' : sensor_doc['status'],
                    'last_heartbeat' : (now - sensor_doc['heartbeat']).total_seconds(),
                    'readings' : {}
                }
            for reading_name in sensor_doc['readings']:
                reading_doc = self.GetReading(sensor_name, reading_name)
                status[sensor_name]['readings'][reading_name] = {
                        'description' : reading_doc['description'],
                        'status' : reading_doc['status'],
                    }
                if reading_doc['status'] == 'online':
                    status[sensor_name]['readings'][reading_name]['runmode'] = reading_doc['runmode'],
                    data_doc = self.readFromDatabase('data', sensor_name,
                                cuts={reading_name : {'$exists' : 1}},
                                sort=[('_id', -1)], onlyone=True)
                    status[sensor_name]['readings'][reading_name]['last_value'] = data_doc[reading_name]
                    doc_time = int(str(data_doc['_id'])[:8], 16)
                    status[sensor_name]['readings'][reading_name]['last_time'] = time.time() - doc_time
        return status

def PrintCurrentStatus(status_doc):
        """
        Gives a command-line user a snapshot of the current system status
        """
        now = dtnow()
        print()
        print('Sensor status and latest heartbeat:')
        for name, doc in status_doc['sensor_status'].items():
            print("\t{0}: {1} | {2:.2g} s".format(name, doc['status'], doc['last_heartbeat']))
        print()
        print('Reading status and latest value:')
        for name, doc in status_doc['reading_status'].items():
            print("\t{0} {1} {2}".format(
                '%s - %s:' % name.split('__'),
                doc['status'],
                f"{(doc['runmode'])} | {doc['last_measurement_time']:.1f} s, {doc['last_measured_value']:.3g}" if doc['status'] == 'online' else ''))


def main(db):
    parser = argparse.ArgumentParser(usage='%(prog)s [options] \n\n Doberman interface')

    parser.add_argument('--update', action='store_true', default=False,
                        help='Update contacts')
    parser.add_argument('command', nargs='*',
                        help='Issue a command to the system. Try \'help\'')
    parser.add_argument('--add-contact', action='store_true', default=False,
                        help='Add a new contact')
    parser.add_argument('--add-sensor', default=None, type=str,
                        help='Specify a new sensor config file to load')
    parser.add_argument('--status', action='store_true', default=False,
                        help='List current status')
    args = parser.parse_args()
    if args.command:
        db.ProcessCommandStepOne(' '.join(args.command))
        return
    if args.status:
        PrintCurrentStatus(db.GetCurrentStatus())
        return
    try:
        if args.add_contact:
            db.addContact()
        if args.add_sensor:
            db.addSensor(args.add_sensor)
        if args.update:
            db.updateContacts()
    except KeyboardInterrupt:
        print('Interrupted!')
    except Exception as e:
        print('I caught a %s exception: %s' % (type(e),e))

    return

if __name__ == '__main__':
    db = DobermanDB(appname='CLI')
    try:
        main(db)
    except Exception as e:
        print('Caught a %s: %s' % (type(e),e))
    db.close()

#!/scratch/anaconda3/bin/python3
import logging
import datetime
import pymongo
import utils
import json
import argparse
import os
import re  # EVERYBODY STAND BACK xkcd.com/208
dtnow = datetime.datetime.now


class DobermanDB(object):
    """
    Class to handle interfacing with the Doberman database
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        # Load database connection details
        try:
            with open('/scratch/doberman/connection_uri','r') as f:
                conn_str = f.read().rstrip()
        except Exception as e:
            print("Can not load database connection details. Error %s" % e)
            raise

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
        self.client = pymongo.MongoClient(conn_str)

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
        if db_name not in self.client.list_database_names():
            self.logger.debug('Database %s doesn\'t exist yet, creating it...' % db_name)
        elif collection_name not in self.client[db_name].list_collection_names(False):
            self.logger.debug('Collection %s not in database %s, creating it...' % (collection_name, db_name))
            self.client[db_name].create_collection(collection_name)
            if db_name == 'data':
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

    def GetData(self, plugin_name, start_time, data_index, end_time=None):
        """
        This function basically exists to support the PID loop. Returns a
        numpy-structurable array of (timestamp, value) between start_time
        and end_time, for the specified data index. 'Timestamp' is a float
        of time since epoch

        :param plugin_name: the name of the plugin to get data for
        :param start_time: python Datetime instance of the earliest time to fetch
        :param data_index: which entry in the data array you want
        :param end_time: python Datetime instance of the latest time to fetch

        Returns [(timestamp, value), (timestamp, value), ...]
        """
        collection = self._check('data', plugin_name)
        query = {'when' : {'$gte' : start_time}}
        if end_time is not None:
            query['when'].update({'$lte' : end_time})
        proj = {'status' : 0, '_id' : 0, 'data' : 1, 'when' : 1}
        sort = [('when', 1)]
        b = []
        for row in self.readFromDatabase('data', plugin_name, query,
                projection=proj, sort=sort):
            b.append((row['when'].timestamp(), row['data'][data_index]))
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
        if doc and doc['by'] == 'feedback':
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
            coll = 'defaults'
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
            ctrl_cls = utils.FindPlugin(name, ['.'])
            if not hasattr(ctrl_cls, 'accepted_commands'):
                print('none')
            else:
                for row in ctrl_cls.accepted_commands:
                    print(row)
        print()
        print('Plugin name == "all" issues the command to applicable plugins. Context-aware.')
        print()
        print('Available runmodes:')
        runmodes = self.Distinct('settings','runmodes','mode')
        print(' | '.join(runmodes))
        print()
        return

    def StoreCommand(self, name, command, future=None):
        """
        Puts a command into the database

        :param name: the name of the entity the command is for
        :param command: the command to be issued
        :param future: a timedelta instance of how far into the future the
        command should be handled, default None
        """
        template = {'name' : name, 'command' : command,
                'by' : os.environ['USER'], 'logged' : dtnow()}
        if future is not None:
            template['logged'] += future
        self.insertIntoDatabase('logging','commands', template)
        return

    def ParseCommand(self, command_str):
        """
        Does the regex matching for command input

        :param command_str: the string as received from the command line
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
                self.ProcessCommand(m)
                break
        else:
            print('Command \'%s\' not understood' % command_str)

    def ProcessCommand(self, m):
        """
        Takes the match object (m) and figures out what it actually means
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
                self.StoreCommand('doberman', 'start %s %s' % (n, m['runmode']))
        elif command == 'stop':
            for n in names[name]:
                self.StoreCommand(n, 'stop')
        elif command == 'restart':
            td = datetime.timedelta(seconds=1.1*utils.heartbeat_timer)
            for n in names[name]:
                self.StoreCommand(n, 'stop')
                self.StoreCommand('doberman', 'start %s None' % n, td)
        elif command == 'sleep':
            duration = m['duration']
            if duration is None:
                print('Can\'t sleep without specifying a duration!')
            elif duration == 'inf':
                for n in names[name]:
                    self.StoreCommand(n, 'sleep')
            else:
                howmany = int(duration[:-1])
                which = duration[-1]
                time_map = {'s' : 'seconds', 'm' : 'minutes', 'h' : 'hours', 'd' : 'days'}
                kwarg = {time_map[which] : howmany}
                sleep_time = datetime.timedelta(**kwarg)
                for n in names[name]:
                    self.StoreCommand(n, 'sleep')
                    self.StoreCommand(n, 'wake', sleep_time)
        elif command == 'wake':
            for n in names[name]:
                self.StoreCommand(n, 'wake')
        elif command == 'runmode':
            for n in names[name]:
                self.StoreCommand(n, 'runmode %s' % m['runmode'])
        else:
            self.StoreCommand(name, command)

    def logAlarm(self, document):
        """
        Adds the alarm to the history.
        """
        if self.insertIntoDatabase('logging','alarm_history',document):
            self.logger.warning('Could not add entry to alarm history!')
            return -1
        return 0

    def GetSensorSettings(self, name):
        """
        Reads the settings in the database.

        :param name: the name of the sensor
        :returns configuration document for the specified sensor
        """
        return self.readFromDatabase('settings', 'sensors', cuts={'name' : name}, onlyone=True)

    def SetSensorSetting(self, name, field, value):
        """
        Updates the setting from one sensor

        :param name: the name of the sensor
        :param field: the specific field to update
        :param value: the new value
        """
        self.updateDatabase('settings','sensors',cuts={'name' : name},
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
                    {'mode' : runmode},onlyone=True)
            if name:
                return doc[name]
            return doc
        doc = self.readFromDatabase('settings','defaults', onlyone=True)
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
                self.updateDatabase('settings','defaults',cuts={},
                        updates={'$push' : {'managed_plugins' : name}})
        elif action=='remove':
            if name not in managed_plugins:
                self.logger.debug('%s isn\'t managed' % name)
            else:
                self.updateDatabase('settings','defaults',cuts={},
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

    def writeDataToDatabase(self, collection_name, when, value):
        """
        Writes data to the database

        :param collection_name: <sensor name>__<reading name>
        :param when: datetime instance of reading timestamp
        :param value: the actual value to insert
        :returns 0 on success, -1 otherwise
        """
        ret = self.insertIntoDatabase('data', collection_name,
                {'when' : when, 'data' : value})
        if ret:
            self.logger.warning("Can not write data from %s to Database. "
                                "Database interaction error." % collection_name)
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

    def updateAlarms(self):
        """
        Allows a command-line user to update alarm settings. Disabled due to abuse
        """
        names = self.Distinct('settings','sensors','name')
        print('Here are the available sensors:')
        print('\n'.join(names))
        print()
        print('Which one do you want to update?')
        name = input('>>> ')
        if name not in names:
            print('What is "%s"? It isn\'t in the above list' % name)
            return
        config_doc = self.GetSensorSettings(name)
        descs = [r['description'] for r in config_doc['readings']]
        print('Here are the different readings for %s:' % name)
        for d in enumerate(descs):
            print('%i: %s' % d)
        print('What is the number of the reading you want to change?')
        number = input('>>> ')
        if number != 'expert':
            try:
                number = int(number)
                if number not in range(len(descs)):
                    raise ValueError
            except ValueError:
                print('Invalid number')
                return

            print('Here are the alarm levels for %s:' % descs[number])
            for i,(lo,hi) in enumerate(config_doc['readings'][number]['alarms']):
                print('(%i) low: %.2g | high: %.2g' % (i, lo, hi))

            print('Which alarm level do you want to change?')
            al_num = input('>>> ')
            try:
                al_num = int(al_num)
                if al_num not in range(len(config_doc['readings'][number]['alarms'])):
                    raise ValueError
            except ValueError:
                print('Invalid number')
                return
        else:
            print('Give it to me:')
            number, al_num = map(int, input('>>> ').split())

        s = 'readings.%i.alarms.%i' % (number, al_num)

        print('Enter new low value (n for no change):')
        lo = input('>>> ')
        print('Enter new high value (n for no change):')
        hi = input('>>> ')
        try:
            if lo != 'n':
                lo = float(lo)
            else:
                lo = config_doc['readings'][number]['alarms'][al_num][0]
            if hi != 'n':
                hi = float(hi)
            else:
                hi = config_doc['readings'][number]['alarms'][al_num][1]
        except ValueError:
            print('Invalid numbers')
            return

        cuts = {'name' : name}
        updates = {'$set' : {s : [lo,hi]}}
        self.updateDatabase('settings','sensors',cuts=cuts,updates=updates)
        print('You got it')

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
        if firstname in self.Distinct('settings','contacts','name'):
            firstname = firstname + lastname[0]
        sms = input('sms: ')
        email = input('email: ')
        status = utils.getUserInput('Status (int): ', input_type=[int], exceptions=['n'])
        if status == 'n':
            status = '-1'
        if self.insertIntoDatabase('settings','contacts',{'name' : firstname, 'sms' : sms,
            'email' : email, 'status' : status}):
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

    def CurrentStatus(self):
        """
        Gives a command-line user a snapshot of the current system status
        """
        now = dtnow()
        doc = self.getDefaultSettings()
        print('Status: %s\nRunmode: %s' % (doc['status'], doc['runmode']))
        print('Last heartbeat: %i seconds ago' % ((now - doc['heartbeat']).total_seconds()))
        print()
        print('Currently running sensors:')
        print("  Name: runmode")
        print("    Description: seconds since last measurement | value")
        s = "{name: >18s}: {dt: .3g} | {value: .3g}"
        for row in self.readFromDatabase('settings','sensors',{'status' : 'online'}):
            runmode = row['runmode']
            print('{name: <12s}: {runmode: >12s}'.format(**row))
            for reading in row['readings']:
                datadoc = self.readFromDatabase('data','%s__%s' % (row['name'], reading['name']), onlyone=True, sort=[('when',-1)])
                try:
                    print(s.format(name=reading['description'],
                        when=(now-datadoc['when']).total_seconds(),
                        value=datadoc['data']))
                except TypeError as e:
                    print('{name: <12s} | TypeError | {desc}'.format(
                        name=reading['description'], desc=e))
        for row in self.readFromDatabase('settings','sensors',{'status' : 'sleep'}):
            print('  {name} | sleep'.format(name=row['name']))
        return

def main(db):
    parser = argparse.ArgumentParser(usage='%(prog)s [options] \n\n Doberman interface')

    parser.add_argument('--update', action='store_true', default=False,
                        help='Update settings/contacts/etc')
    parser.add_argument('command', nargs='*',
                        help='Issue a command to the system. Try \'help\'')
    parser.add_argument('--add-runmode', action='store_true', default=False,
                        help='Add a new operation preset')
    parser.add_argument('--add-contact', action='store_true', default=False,
                        help='Add a new contact')
    parser.add_argument('--add-sensor', default=None, type=str,
                        help='Specify a new sensor config file to load')
    parser.add_argument('--status', action='store_true', default=False,
                        help='List current status')
    args = parser.parse_args()
    if args.command:
        db.ParseCommand(' '.join(args.command))
        return
    if args.status:
        db.CurrentStatus()
        return
    try:
        if args.add_runmode:
            db.addOpmode()
        if args.add_contact:
            db.addContact()
        if args.add_sensor:
            db.addSensor(args.add_sensor)
        if args.update:
            #db.askForUpdates()
            db.updateContacts()
    except KeyboardInterrupt:
        print('Interrupted!')
    except Exception as e:
        print('I caught a %s exception: %s' % (type(e),e))

    return

if __name__ == '__main__':
    db = DobermanDB()
    try:
        main(db)
    except Exception as e:
        print('Caught a %s: %s' % (type(e),e))
    db.close()

#!/usr/bin/env python3
import logging
import datetime
import pymongo
import utils
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
        Returns the requested collection and logs if the database/collection don't yet exist
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
                return 1
        else:
            self.logger.error('Not sure what to do with %s type' % type(document))
            return -1

    def readFromDatabase(self, db_name, collection_name, cuts={}, onlyone = False, **kwargs):
        """
        Finds one or more documents that pass the specified cuts
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
        """
        collection = self._check(db_name, collection_name)
        ret = collection.update_many(cuts, updates, **kwargs)
        if not ret.acknowledged:
            return 1
        return 0

    def DeleteDocuments(self, db_name, collection_name, cuts):
        """
        Deletes documents from the specified collection
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
        for row in self.readFromDatabase('data', plugin_name, query, projection=proj, sort=sort):
            b.append((row['when'].timestamp(), row['data'][data_index]))
        return b

    def Distinct(self, db_name, collection_name, field, cuts={}, **kwargs):
        return self._check(db_name, collection_name).distinct(field, cuts, **kwargs)

    def Count(self, db_name, collection_name, cuts, **kwargs):
        return self._check(db_name, collection_name).count_documents(cuts, **kwargs)

    def FindOneAndUpdate(self, db_name, collection_name, cuts, updates, **kwargs):
        """
        Finds one document and applies updates. A bit of a special implementation so
        the 'sort' kwarg will actually do something
        """
        doc = self.readFromDatabase(db_name, collection_name, cuts, onlyone=True, **kwargs)
        if doc is not None:
            self.updateDatabase(db_name, collection_name, {'_id' : doc['_id']}, updates)
        return doc

    def FindCommand(self, name):
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
        doc = self.readFromDatabase('settings','alarm_config', {'level' : level}, onlyone=True)
        if doc is None:
            self.logger.error('No message protocols for alarm level %i! Defaulting to next lowest level' % level)
            doc = self.readFromDatabase('settings','alarm_config',
                    {'level' : {'$lte' : level}}, onlyone=True,
                    sort=[('level', -1)])
            return doc['protocols']
        return doc['protocols']

    def getContactAddresses(self, level):
        """
        Returns a list of addresses to contact at 'level'
        """
        protocols = self.getMessageProtocols(level)
        ret = {k : [] for k in protocols}
        for doc in self.readFromDatabase('settings','contacts',
                {'status' : {'$gte' : 0, '$lte' : level}}):
            for p in protocols:
                ret[p].append(doc[p])
        return ret

    def PrintHelp(self, name):
        print('Accepted commands:')
        print('help <plugin_name>: help for specific plugin')
        print('start <plugin_name>: starts the specified plugin')
        print('stop <plugin_name>: stops the specified plugin')
        print('restart <plugin_name>: hard restarts the specified plugin')
        print('runmode <runmode>: changes the active runmode')
        print('sleep: puts Doberman to sleep')
        print('wake: reactivates Doberman')
        print()
        print('Available plugins:')
        names = self.Distinct('settings','controllers','name')
        print(' | '.join(names))
        print()
        print('Plugin commands:')
        print('<plugin_name> sleep: puts the specified plugin to sleep')
        print('<plugin_name> wake: reactivates the specified plugin')
        print('<plugin_name> runmode <runmode>: changes the active runmode for the specified controller')
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
        print('Plugin name == "all" issues the command to all running plugins')
        print()
        print('Available runmodes:')
        runmodes = self.Distinct('settings','runmodes','mode')
        print(' | '.join(runmodes))
        print()
        return

    def StoreCommand(self, command_str):
        """
        Stores commands for the system. Command == 'help' describes accepted commands
        """
        names = self.Distinct('settings','controllers','name')
        names_ = '|'.join(names + ['all'])
        runmodes_ = '|'.join(self.Distinct('settings','runmodes','mode'))
        whoami = os.environ['USER']
        online = self.Distinct('settings','controllers','name', {'online' : True})
        if command_str.startswith('help'):
            n = None
            if len(command_str) > len('help '):
                name = command_str[len('help '):]
                if name in names:
                    n = name
            self.PrintHelp(n)
            return

        patterns = [
            ('^start (?P<name>%s)' % names_, lambda m : ('doberman', 'start ' + m.group('name'))),
            ('^stop (?P<name>%s)' % names_, lambda m : (m.group('name'), 'stop')),
            ('^restart (?P<name>%s)' % names_, lambda m : (m.group('name'), 'restart')),
            ('^runmode (?P<runmode>%s)' % runmodes_, lambda m : ('doberman', 'runmode ' + m.group('runmode'))),
            ('^sleep', lambda m : ('doberman', 'sleep')),
            ('^wake', lambda m : ('doberman', 'wake')),
            ('^(?P<name>%s) sleep' % names_, lambda m : (m.group('name'), 'sleep')),
            ('^(?P<name>%s) wake' % names_, lambda m : (m.group('name'), 'wake')),
            ('^(?P<name>%s) runmode (?P<runmode>%s)' % (names_, runmodes_), lambda m : (m.group('name'), 'runmode ' + m.group('runmode'))),
            ('^(?P<name>%s) (?P<command>.+)$' % names_, lambda m : (m.group('name'), m.group('command'))),
        ]
        for pattern, func in patterns:
            m = re.search(pattern, command_str)
            if m:
                name, com = func(m)
                print('Storing command \'%s\' for %s' % (com, name))
                docs = []
                if name == 'all':
                    for n in online:
                        docs.append({'name' : n, 'by' : whoami, 'logged' : dtnow(),
                            'command' : com if com != 'restart' else 'stop'})
                        if com == 'restart':
                            docs.append({'name' : 'doberman', 'by' : whoami,
                                'command' : 'start ' + n,
                                'logged' : dtnow() + datetime.timedelta(seconds=10)})
                else:
                    docs.append({'name' : name, 'by' : whoami, 'logged' : dtnow(),
                        'command' : com if com != 'restart' else 'stop'})
                    if com == 'restart':
                        docs.append({'name' : 'doberman', 'by' : whoami,
                            'command' : 'start ' + name,
                            'logged' : dtnow() + datetime.timedelta(seconds=10)})

                self.insertIntoDatabase('logging','commands',docs)
                break
        else:
            print('Command \'%s\' not understood' % command_str)

    def logAlarm(self, document):
        """
        Adds the alarm to the history.
        """
        if self.insertIntoDatabase('logging','alarm_history',document):
            self.logger.warning('Could not add entry to alarm history!')
            return -1
        return 0

    def ControllerSettings(self, name='all'):
        """
        Reads the settings in the database.
        """
        if name == 'all':
            return {row['name'] : row for row in self.readFromDatabase('settings', 'controllers')}
        else:
            return self.readFromDatabase('settings', 'controllers', cuts={'name' : name}, onlyone=True)

    def getDefaultSettings(self, runmode=None, name=None):
        """
        Reads default Doberman settings from database.
        Returns a dict or the specified value
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

    def updateContacts(self):
        """
        Update active contacts
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

    def writeDataToDatabase(self, name, when, data, status):
        """
        Writes data to the database
        Status:
          0 = OK,
          -1 = No connection to controller
          -2 = Could not communicate with controller
          -3 = Wrong number of data received
          -4 = Error parsing data
          1 = Warning
          2 = Alarm
        """
        ret = self.insertIntoDatabase('data', name,
                {'when' : when, 'data' : data, 'status' : status})
        if ret:
            self.logger.warning("Can not write data from %s to Database. "
                                "Database interaction error." % name)
            return -1
        self.logger.debug('Wrote data from %s' % name)
        return 0

    def askForUpdates(self):
        which = ''
        to_quit = ['q','Q','n']
        while which not in to_quit:
            print('What do you want to update?')
            print(' contacts | controllers')
            print('(use q, Q, or n to quit)')
            which = input('>>> ')
            if which == 'contacts':
                self.updateContacts()
            elif which == 'controllers':
                self.updateAlarms()
            elif which not in to_quit:
                print('Invalid input: %s' % which)
        return

    def updateAlarms(self):
        names = self.Distinct('settings','controllers','name')
        print('Here are the available controllers:')
        print('\n'.join(names))
        print()
        print('Which one do you want to update?')
        name = input('>>> ')
        if name not in names:
            print('What is "%s"? It isn\'t in the above list' % name)
            return
        config_doc = self.ControllerSettings(name)
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
        self.updateDatabase('settings','controllers',cuts=cuts,updates=updates)
        print('You got it')

    def addOpmode(self):
        print('What is the name of this runmode?')
        name = input('>>> ')
        print('What loglevel (default 20 = \'info\')?')
        loglevel = utils.getUserInput('>>> ', input_type=[int], be_in=range(10,60,10),
                exceptions=['n'])
        if loglevel == 'n':
            loglevel = 20
        print('Testrun - how soon after starting can alarms be issued (default 5)?')
        testrun = utils.getUserInput('>>> ', input_type=[int],exceptions=['n'])
        if testrun == 'n':
            testrun = 5
        print('Message timer - how often (in minutes) alarms can be issued (default 5)?')
        msg_time = utils.getUserInput('>>> ', input_type=[int], exceptions=['n'])
        if msg_time == 'n':
            msg_time = 5
        if self.insertIntoDatabase('settings','runmodes',{'mode' : name,
            'loglevel' : loglevel, 'testrun' : testrun, 'message_time' : msg_time}):
            print('Could not add runmode!')
        return

    def addContact(self):
        print('Contact name:')
        name = input('>>> ')
        print('Contact sms')
        sms = input('>>> ')
        print('Contact email')
        email = input('>>> ')
        print('Contact status (int)')
        status = utils.getUserInput('>>> ', input_type=[int], exceptions=['n'])
        if status == 'n':
            status = '-1'
        if self.insertIntoDatabase('settings','contacts',{'name' : name, 'sms' : sms,
            'email' : email, 'status' : status}):
            print('Could not add contact!')
        return

    def addController(self, filename):
        with open(filename, 'r') as f:
            try:
                d = eval(f.read())
            except Exception as e:
                print('Could not read file! Error: %s' % e)
            if self.insertIntoDatabase('settings','controllers',d):
                print('Could not add controller!')
            else:
                print('Controller added')
        return

    def CurrentStatus(self):
        now = dtnow()
        doc = self.getDefaultSettings()
        print('Status: %s\nRunmode: %s' % (doc['status'], doc['runmode']))
        print('Last heartbeat: %i seconds ago' % ((now - doc['heartbeat']).total_seconds()))
        print()
        print('Currently running controllers:')
        print('  |  '.join(['Name','Runmode',
            'Seconds since last measurement','Values']))
        for row in self.readFromDatabase('settings','controllers',{'online' : True}):
            runmode = row['runmode']
            datadoc = self.readFromDatabase('data',row['name'],onlyone=True,sort=[('when',-1)])
            print('  {name} | {runmode} | {when:.1f} | {values}'.format(
                name=row['name'], runmode=runmode,
                when=(now-datadoc['when']).total_seconds(),
                values=', '.join(['%.3g' % v for v in datadoc['data']])))
        return

def main(db):
    parser = argparse.ArgumentParser(usage='%(prog)s [options] \n\n Doberman interface')

    parser.add_argument('--update', action='store_true', default=False,
                        help='Update settings/contacts/etc')
    parser.add_argument('command', nargs='*',
                        help='Issue a command to the system. Format: '
                            '<name> <command>. Try \'help\'')
    parser.add_argument('--add-runmode', action='store_true', default=False,
                        help='Add a new operation preset')
    parser.add_argument('--add-contact', action='store_true', default=False,
                        help='Add a new contact')
    parser.add_argument('--add-controller', default=None, type=str,
                        help='Specify a new controller config file to load')
    parser.add_argument('--status', action='store_true', default=False,
                        help='List current status')
    args = parser.parse_args()
    if args.command:
        db.StoreCommand(' '.join(args.command))
        return
    if args.status:
        db.CurrentStatus()
        return
    try:
        if args.add_runmode:
            db.addOpmode()
        if args.add_contact:
            db.addContact()
        if args.add_controller:
            db.addController(args.add_controller)
        if args.update:
            db.askForUpdates()
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

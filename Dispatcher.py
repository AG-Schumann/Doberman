import re
import DobermanDB
import datetime
import os
import time
dtnow = datetime.datetime.now


def StoreCommand(db, name, command, future=None):
    """
    Puts a command into the database
    """
    template = {'name' : name, 'command' : command,
                'by' : os.environ['USER'], 'logged' : dtnow()}
    if future is not None:
            template['logged'] += future
    db.insertIntoDatabase('logging', 'commands', template)
    return

def ParseCommand(db, command_str):
    """
    Does the regex matching for command input
    """
    names = db.Distinct('settings', 'controllers', 'name')
    if command_str.startswith('help'):
        n = None
        if len(command_str) > len('help '):
            name = command_str[len('help '):]
            if name in names:
                n = name
        db.PrintHelp(n)
        return
    ctrl_names = '|'.join(names + ['all'])
    hostnames = '|'.join(db.Distinct('settings','hosts','hostname'))
    runmodes = '|'.join(db.Distinct('settings', 'runmodes', 'mode'))

    patterns = [
        '^(?P<command>start|stop|restart) (?P<name>%s)(?: (?P<runmode>%s))?' % \
                (ctrl_names, runmodes),
        '^(?P<name>%s) (?P<command>sleep|wake)(?: (?P<duration>(?:[1-9][0-9]*[dhms])|(?:inf)))?' % (ctrl_names + hostnames),
        '^(?P<name>%s) (?P<command>runmode) (?P<runmode>%s)' % \
                (ctrl_names + hostnames, runmodes),
        '^(?P<name>%s) (?P<command>.+)$' % ctrl_names,
    ]
    for pattern in patterns:
        m = re.search(pattern, command_str)
        if m:
            ret = ProcessCommand(db, m.groupdict())
            break
    else:
        print('Command \'%s\' not understood' % command_str)
        return
    if ret == 0:
        print("Let's see if that worked...")
        time.sleep(3)
        cur = db.readFromDatabase('logging','logs',cuts={'when' :
            {'$gte' : dtnow() - datetime.timedelta(seconds=4)}},sort=[('when',1)])
        for doc in cur:
            print("{when} | {name} | {msg}".format(**doc))

def ProcessCommand(db, m):
    """
    Takes the match object dictionary (m) and figures out what it actually means
    """
    command = m['command']
    name = str(m['name'])
    which_host = {ctrl['name'] : ctrl['hostname']
            for ctrl in db.readFromDatabase('settings','controllers',
                cuts={}, projection={'name' : 1, 'hostname' : 1})}
    hostnames = db.Distinct('settings','hosts','hostname', cuts={'status' : 'online'})
    online = db.Distinct('settings','controllers','name', {'status' : 'online'})
    offline = db.Distinct('settings','controllers','name', {'status' : 'offline'})
    asleep = db.Distinct('settings','controllers','name', {'status' : 'sleep'}) + \
             db.Distinct('settings','hosts','hostname', cuts={'status' : 'sleep'})

    if command == 'start':
        if name == 'all':
            for n in offline:
                StoreCommand(db, which_host[n], 'start %s %s' % (n, m['runmode']))
        else:
            StoreCommand(db, which_host[name], 'start %s %s' % (name, m['runmode']))
    elif command == 'stop':
        if name == 'all':
            for n in online:
                StoreCommand(db, n, 'stop')
        else:
            StoreCommand(db, name, 'stop')
    elif command == 'restart':
        td = datetime.timedelta(seconds=1.1*utils.heartbeat_timer)
        if name == 'all':
            for n in online:
                StoreCommand(db, n, 'stop')
                StoreCommand(db, which_host[n], 'start %s None' % n, td)
        else:
            StoreCommand(db, name, 'stop')
            StoreCommand(db, which_host[name], 'start %s None' % name, td)
    elif command == 'sleep':
        duration = m['duration']
        if duration is None:
            print('Can\'t sleep without specifying a duration!')
            return 1
        elif duration == 'inf':
            if name == 'all':
                print('No')
                return 1
            else:
                StoreCommand(db, name, 'sleep')
        else:
            howmany = int(duration[:-1])
            which = duration[-1]
            time_map = {'s' : 'seconds', 'm' : 'minutes', 'h' : 'hours', 'd' : 'days'}
            kwarg = {time_map[which] : howmany}
            sleep_time = datetime.timedelta(**kwarg)
            if name == 'all':
                for n in online + hostnames:
                    StoreCommand(db, n, 'sleep')
                    StoreCommand(db, n, 'wake', sleep_time)
            else:
                StoreCommand(db, name, 'sleep')
                StoreCommand(db, name, 'wake', sleep_time)
    elif command == 'wake':
        if name == 'all':
            for n in asleep:
                StoreCommand(db, n, 'wake')
        else:
            StoreCommand(db, name, 'wake')
    elif command == 'runmode':
        if name == 'all':
            for n in online + hostnames:
                StoreCommand(db, n, 'runmode %s' % m['runmode'])
        else:
            StoreCommand(db, name, 'runmode %s' % m['runmode'])
    else:
        self.StoreCommand(name, command)
    return 0

def main(db):
    parser = argparse.ArgumentParser(usage='Doberman command dispatcher')
    parser.add_argument('command', nargs='+',
                        help='Issue a command to the system. Try \'help\'')
    args = parser.parse_args()
    ParseCommand(db, ' '.join(args.command))
    return

if __name__ == '__main__':
    db = DobermanDB.DobermanDB()
    try:
        main()
    except Exception as e:
        print("Caught a %s: %s" % (type(e), e))
    finally:
        db.close()

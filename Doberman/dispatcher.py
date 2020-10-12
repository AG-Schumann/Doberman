import re
import datetime
import time
import sys
import Doberman
import os
import socket
from pymongo import MongoClient

dtnow = datetime.datetime.utcnow

__all__ = 'PrintHelp ProcessCommand'.split()


def print_help(db, name):
    print('Accepted commands:')
    print('help [<plugin_name>]: help [for specific plugin]')
    print('start <plugin_name> [<runmode>]: starts a plugin [in the specified runmode]')
    print('stop <plugin_name>: stops a plugin')
    print('restart <plugin_name>: restarts a plugin')
    print()
    print('Available plugins:')
    names = db.distinct('settings', 'sensors', 'name')
    print(' | '.join(names))
    print()
    print('Plugin commands:')
    print('<plugin_name> [<reading_name>] runmode <runmode>: '
          + 'changes the active runmode for the specified sensor\'s reading (\'all\' accepted)')
    print()
    if name:
        print('Commands specific to %s:' % name)
        path = db.read_from_db('common', 'hosts', {'hostname': socket.gethostname()}, onlyone=True)['plugin_dir']
        snsr_cls = Doberman.utils.find_plugin(name, path)
        if not hasattr(snsr_cls, 'accepted_commands'):
            print('none')
        else:
            for row in snsr_cls.accepted_commands:
                print(row)
    print()
    print('Plugin name == "all" issues the command to applicable plugins. Context-aware.')
    print()
    print('Available runmodes:')
    runmodes = db.distinct('settings', 'runmodes', 'mode')
    print(' | '.join(runmodes))
    print()
    return


def process_command(db, command_str, user=None):
    """
    Does the regex matching for command input
    :param db: instance of Database
    :param command_str: the string as received from the command line
    :param user: a dict of info from the web interface
    """
    names = db.distinct('settings', 'sensors', 'name')
    names_ = '|'.join(names + ['all'])
    runmodes_ = '|'.join(db.distinct('settings', 'runmodes', 'mode'))
    if command_str.startswith('help'):
        n = None
        if len(command_str) > len('help '):
            name = command_str[len('help '):]
            if name in names:
                n = name
        print_help(db, n)
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
            step_two(db, m, user=user)
            if user is not None:  # for non-CLI users
                break
            time.sleep(3)
            for log in db.read_from_db('logging', 'logs',
                                       cuts={'when': {'$gte': dtnow() - datetime.timedelta(seconds=3)}},
                                       sort=([('_id', -1)])):
                print('{when} | {level} | {name} | {msg}'.format(**log))
            break
    else:
        print('Command \'%s\' not understood' % command_str)


def step_two(db, m, user=None):
    """
    Takes the match object (m) from StepOne and figures out what it actually means
    """

    command = m['command']
    name = str(m['name'])
    names = {'None': ['doberman']}
    if name != 'None':
        names.update({name: [name]})
    online = db.distinct('settings', 'sensors', 'name', {'status': 'online'})
    offline = db.distinct('settings', 'sensors', 'name', {'status': 'offline'})
    asleep = db.distinct('settings', 'sensors', 'name', {'status': 'sleep'})
    if command in ['start', 'stop', 'restart', 'sleep', 'wake', 'runmode']:
        names.update({'all': {
            'start': offline,
            'stop': online,
            'restart': online,
            'sleep': online,
            'wake': asleep,
            'runmode': online}[command]})
    if command == 'start':
        for n in names[name]:
            step_three(db, 'doberman', 'start %s %s' % (n, m['runmode']), user=user)
    elif command == 'stop':
        for n in names[name]:
            step_three(db, n, 'stop', user=user)
    elif command == 'restart':
        td = datetime.timedelta(seconds=1.1 * Doberman.utils.heartbeat_timer)
        for n in names[name]:
            step_three(db, n, 'stop', user=user)
            step_three(db, n, 'start', td, user=user)
    elif command == 'runmode':
        for n in names[name]:
            step_three(db, n, f'runmode {m["runmode"]}', user=user)
    else:
        step_three(db, name, command, user=user)


def step_three(db, name, command, future=None, user=None):
    """
    Puts a command into the database

    :param db: the instance of Database
    :param name: the name of the entity the command is for
    :param command: the command to be issued
    :param future: a timedelta instance of how far into the future the
    command should be handled, default None
    :param user: the info about an external user
    """
    command_doc = {'name': name, 'command': command, 'logged': dtnow()}
    if user is None:
        user = {
            'client_addr': '127.0.0.1',
            'client_host': 'localhost',
            'client_name': os.environ['USER']
        }
    command_doc.update(user)
    if future is not None:
        command_doc['logged'] += future
    db.insert_into_db('logging', 'commands', command_doc)
    return


def main(mongo_client):
    command = ' '.join(sys.argv[1:])
    db = Doberman.Database(mongo_client, experiment_name=os.environ['DOBERMAN_EXPERIMENT_NAME'])
    process_command(db, command)


if __name__ == '__main__':
    with MongoClient(os.environ['DOBERMAN_CONNECTION_URI']) as client:
        try:
            main(client)
        except Exception as e:
            print('Caught a %s: %s' % (type(e), e))

from ast import literal_eval
import serial
from subprocess import Popen, PIPE, TimeoutExpired
import importlib
import importlib.machinery
import time
import datetime
import signal
import os.path
import inspect
import re
dtnow = datetime.datetime.now


heartbeat_timer = 300
buffer_timer = 5
number_regex = r'[\-+]?[0-9]+(?:\.[0-9]+)?(?:[eE][\-+]?[0-9]+)?'
doberman_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

def getUserInput(text, input_type=None, be_in=None, be_not_in=None, be_array=False, limits=None, string_length=None, exceptions=None):
    """
    Ask for an input bye displaying the 'text'.
    It is asked until:
      the input has the 'input_type(s)' specified,
      the input is in the list 'be_in' (if not None),
      not in the list 'be_not_in' (if not None),
      the input is between the limits (if not None).
      has the right length if it is a string (if not None)
    'input_type', 'be_in' and 'be_not_in' must be lists or None.
    'limits' must be a list of type [lower_limit, higher_limit].
    ' lower_limit' or 'higher_limit' can be None. The limit is <=/>=.
    'string_length' must be a list of [lower_length, higher_length]
    ' lower_length' or 'higher_length' can be None. The limit is <=/>=.
    'be_array' can be True or False, it returns the input as array or not.
    If the input is in the exceptions it is returned without checks.
    """
    while True:
        # Read input.
        try:
            user_input = input_eval(input(text), input_type != [str])
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print("Error: %s. Try again." % e)
            continue
        # Check for input exceptions
        if exceptions:
            if user_input in exceptions:
                return user_input
        # Remove string signs
        if input_type == [str] and isinstance(user_input, str):
            user_input = ''.join(c for c in user_input if c not in ['"',"'"])
        # Transform input to list
        if not be_array:
            user_input = [user_input]
        else:
            if isinstance(user_input, tuple):
                user_input = list(user_input)
            elif isinstance(user_input, str):
                user_input = user_input.split(",")
            elif isinstance(user_input, (int, float)):
                user_input = [user_input]
        # Remove spaces after comma for input lists
        if be_array and input_type == [str]:
            user_input = [item.strip() for item in user_input]
        # Check input for type, be_in, be_not_in, limits.
        if input_type:
            if not all(isinstance(item, tuple(input_type)) for item in user_input):
                print("Wrong input format. Must be in %s. Try again." %
                    str(tuple(input_type)))
                continue
        if be_in:
            if any(item not in be_in for item in user_input):
                print("Input must be in: %s. Try again." % str(be_in))
                continue
        if be_not_in:
            if any(item in be_not_in for item in user_input):
                print("Input is not allowed to be in: %s. Try again." % str(be_not_in))
                continue
        if limits:
            if limits[0] or limits[0] == 0:  # Allows also 0.0 as lower limit
                if any(item < limits[0] for item in user_input):
                    print("Input must be between: %s. Try again." % str(limits))
                    continue
            if limits[1]:
                if any(item > limits[1] for item in user_input):
                    print("Input must be between: %s. Try again." % str(limits))
                    continue
        # Check for string length
        if string_length:
            if string_length[0] != None:
                if any(len(item) < string_length[0] for item in user_input):
                    print("Input string must have more than %s characters."
                        " Try again." % str(string_length[0]))
                    continue
            if string_length[1] != None:
                if any(len(item) > string_length[1] for item in user_input):
                    print("Input string must have less than %s characters."
                        " Try again." % str(string_length[1]))
                    continue
        break
    if not be_array:
        return user_input[0]
    return user_input

def adjustListLength(input_list, length, append_item, input_name=None):
    """
    Appending 'append_item' to the 'input_list'
    until 'length' is reached.
    """
    if len(input_list) < length:
        input_list += [append_item]*(length - len(input_list))
    elif len(input_list) > length:
        input_list = input_list[:length]
    return input_list

def input_eval(inputstr, literaleval=True):
    if not isinstance(inputstr, str):
        return -1
    inputstr = inputstr.strip(' \r\t\n\'"').expandtabs(4)
    if literaleval:
        try:
            return literal_eval(inputstr)
        except:
            pass
    return str(inputstr)

def refreshTTY(db):
    """
    Brute-force matches sensors to ttyUSB assignments by trying
    all possible combinations, and updates the database
    """
    cuts = {'status' : 'online', 'address.tty' : {'$exists' : 1, '$regex' : 'USB'}}
    if db.Count('settings','sensors', cuts):
        print('Some USB sensors are running! Stopping them now')
        running_sensors = db.Distinct('settings','sensors','name', cuts)
        for name in running_sensors:
            db.ProcessCommandStepOne('stop %s' % name)
        time.sleep(heartbeat_timer*1.2)
    else:
        running_sensors = []
    db.updateDatabase('settings','sensors',
            cuts={'address.tty' : {'$exists' : 1, '$regex' : '^0|USB[1-9]?[0-9]'}},
            updates={'$set' : {'address.tty' : '0'}})
    print('Refreshing ttyUSB mapping...')
    proc = Popen('ls /dev/ttyUSB*', shell=True, stdout=PIPE, stderr=PIPE)
    try:
        out, err = proc.communicate(timeout=5)
    except TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
    if not len(out) or len(err):
        raise OSError('Could not check ttyUSB! stdout: %s, stderr %s' % (out.decode(), err.decode()))
    ttyUSBs = out.decode().splitlines()
    cursor = db.readFromDatabase('settings','sensors',
            cuts={'address.tty' : {'$exists' : 1, '$regex' : '^0|USB[1-9]?[0-9]'}})
    sensor_config = {row['name'] : row for row in cursor}
    sensor_names = list(sensor_config.keys())
    sensors = {name: None for name in sensor_names}
    matched = {'sensors' : [], 'ttys' : []}
    for sensor in sensor_names:
        opts = SensorOpts(sensor_config[sensor])
        sensors[sensor] = FindPlugin(sensor, [doberman_dir])(opts)
    dev = serial.Serial()
    for tty in ttyUSBs:
        tty_num = int(re.search('USB([1-9]?[0-9])', tty).group(1))
        print('Checking %s' % tty)
        dev.port = tty
        try:
            dev.open()
        except serial.SerialException as e:
            print('Could not connect to %s: %s' % (tty, e))
            continue
        for name, sensor in sensors.items():
            if name in matched['sensors']:
                continue
            if sensor.isThisMe(dev):
                print('Matched %s to %s' % (tty, name))
                matched['sensors'].append(name)
                matched['ttys'].append(tty)
                db.updateDatabase('settings','sensors', {'name' : name},
                        {'$set' : {'address.tty' : 'USB%i' % tty_num}})
                dev.close()
                break
            #print('Not %s' % name)
            time.sleep(0.5)  # devices are slow
        else:
            print('Could not assign %s!' % tty)
        dev.close()
    if len(matched['sensors']) == len(sensors)-1: # n-1 case
        try:
            name = (set(sensors.keys())-set(matched['sensors'])).pop()
            tty = (set(ttyUSBs) - set(matched['ttys'])).pop()
            print('Matched %s to %s via n-1' % (name, tty))
            db.updateDatabase('settings','sensors', {'name' : name},
                    {'$set' : {'address.tty' : tty.split('tty')[-1]}})
        except:
            pass
    elif len(matched['sensors']) != len(sensors):
        print('Didn\'t find the expected number of sensors!')
        print('Sensors unmatched:')
        l = set(sensors.keys()) - set(matched['sensors'])
        print('\n'.join(l))
        print()
        print('tty ports unmatched:')
        l = set(ttyUSBs) - set(matched['ttys'])
        print('\n'.join(l))
        return False
    #for usb, name in zip(matched['ttys'],matched['sensors']):
    #        db.updateDatabase('settings','sensors', {'name' : name},
    #                {'$set' : {'address.ttyUSB' : int(usb.split('USB')[-1])}})

    db.updateDatabase('settings','current_status', {}, {'$set' : {'tty_update' : dtnow()}})
    for name in running_sensors:
        db.ParseCommand('start %s' % name)
    return True

def FindPlugin(name, path):
    """
    Finds the sensor constructor with the specified name, in the specified paths.
    Will attempt to strip numbers off the end of the name if necessary (ex,
    'iseries1' -> iseries, 'caen_n1470' -> caen_n1470)

    :param name: the name of the sensor you want
    :param path: a list of paths in which to search for the file
    :returns constructor: the constructor of the requested sensor
    """
    strip = False
    spec = importlib.machinery.PathFinder.find_spec(name, path)
    if spec is None:
        strip = True
        spec = importlib.machinery.PathFinder.find_spec(name.strip('0123456789'), path)
    if spec is None:
        raise FileNotFoundError('Could not find a sensor named %s' % name)
    try:
        if strip:
            sensor_ctor = getattr(spec.loader.load_module(), name.strip('0123456789'))
        else:
            sensor_ctor = getattr(spec.loader.load_module(), name)
    except AttributeError:
        raise AttributeError('Cound not find constructor for %s!' % name)
    return sensor_ctor

def SensorOpts(config_doc):
    """
    Returns the dictionary of settings to be passed to a Sensor constructor
    """
    opts = {}
    opts['name'] = config_doc['name']
    opts.update(config_doc['address'])
    opts['readings'] = config_doc['readings']
    if 'additional_params' in config_doc:
        opts.update(config_doc['additional_params'])
    return opts

class SignalHandler(object):
    """ Handles signals from the OS
    """
    def __init__(self, logger=None):
        self.interrupted = False
        signal.signal(signal.SIGINT, self.interrupt)
        signal.signal(signal.SIGTERM, self.interrupt)
        self.logger = logger

    def interrupt(self, *args):
        if self.logger is not None:
            self.logger.info('Received signal %i' % args[0])
        self.signal_number = int(args[0])
        self.interrupted = True

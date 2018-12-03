from ast import literal_eval
import serial
from subprocess import Popen, PIPE, TimeoutExpired
import importlib
import importlib.machinery
import time
import datetime
import signal
dtnow = datetime.datetime.now

heartbeat_timer = 30
number_regex = r'[\-+]?[0-9]+(?:\.[0-9]+)?(?:[eE][\-+]?[0-9]+)?'

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
    cuts = {'status' : 'online', 'address.ttyUSB' : {'$exists' : 1}}
    if db.Count('settings','controllers', cuts):
        print('Some USB controllers are running! Stopping them now')
        running_controllers = db.Distinct('settings','controllers','name', cuts)
        for name in running_controllers:
            db.ParseCommand('stop %s' % name)
        time.sleep(35)
    else:
        running_controllers = []
    db.updateDatabase('settings','controllers',cuts={'address.ttyUSB' : {'$exists' : 1}}, updates={'$set' : {'address.ttyUSB' : -1}})
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
    cursor = db.readFromDatabase('settings','controllers', {'address.ttyUSB' : {'$exists' : 1}})
    sensor_config = {row['name'] : row for row in cursor}
    sensor_names = list(sensor_config.keys())
    sensors = {name: None for name in sensor_names}
    matched = {'sensors' : [], 'ttys' : []}
    for sensor in sensor_names:
        opts = {}
        opts['name'] = sensor
        opts['initialize'] = False
        opts.update(sensor_config[sensor]['address'])
        if 'additional_params' in sensor_config[sensor]:
            opts.update(sensor_config[sensor]['additional_params'])
        sensors[sensor] = FindPlugin(sensor, ['.'])(opts)
    dev = serial.Serial()
    for tty in ttyUSBs:
        tty_num = int(tty.split('USB')[-1])
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
                print('Matched %s to %s' % (tty_num, name))
                matched['sensors'].append(name)
                matched['ttys'].append(tty)
                db.updateDatabase('settings','controllers',
                        {'name' : name}, {'$set' : {'address.ttyUSB' : tty_num}})
                dev.close()
                break
            #print('Not %s' % name)
            time.sleep(0.5)  # devices are slow
        else:
            print('Could not assign %s!' % tty)
        dev.close()
    print(len(matched['sensors']))
    print(len(sensors))
    if len(matched['sensors']) == len(sensors)-1: # n-1 case
        name = (set(sensors.keys())-set(matched['sensors'])).pop()
        tty = (set(ttyUSBs) - set(matched['ttys'])).pop()
        print('Matched %s to %s via n-1' % (name, tty))
        db.updateDatabase('settings','controllers', {'name' : name},
                {'$set' : {'address.ttyUSB' : int(tty.split('USB')[-1])}})
    elif len(matched['sensors']) != len(sensors):
        print('Didn\'t find the expected number of sensors!')
        return False
    db.updateDatabase('settings','defaults', {}, {'$set' : {'tty_update' : dtnow()}})
    for name in running_controllers:
        db.ParseCommand('start %s' % name)
    return True

def FindPlugin(name, path):
    """
    Finds the controller constructor with the specified name, in the specified paths

    Parameters
    ---------
    name : str
        The name of the controller to load
    path : [str]
        The paths to look through to find the file named `name.py`

    Returns
    -------
    fcn
        The constructor of the controller

    Raises
    ------
    FileNotFoundError
        If the specified file can't be found
    AttributeError
        If the constructor can't be found
    """
    spec = importlib.machinery.PathFinder.find_spec(name, path)
    if spec is None:
        spec = importlib.machinery.PathFinder.find_spec(name.strip('0123456789'), path)
    if spec is None:
        raise FileNotFoundError('Could not find a controller named %s' % name)
    try:
        controller_ctor = getattr(spec.loader.load_module(), name)
    except AttributeError:
        try:
            controller_ctor = getattr(spec.loader.load_module(), name.strip('0123456789'))
        except AttributeError:
            raise AttributeError('Cound not find constructor for %s!' % name)
    return controller_ctor

class SignalHandler(object):
    """ Handles signals from the OS
    """
    def __init__(self, logger):
        self.interrupted = False
        signal.signal(signal.SIGINT, self.interrupt)
        signal.signal(signal.SIGTERM, self.interrupt)
        self.logger = logger

    def interrupt(self, *args):
        self.logger.info('Received signal %i' % args[0])
        self.signal_number = int(args[0])
        self.interrupted = True

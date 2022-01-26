# Doberman: Slow Control and Monitoring #

**D. Masson, J. Grigat**

Last Update: 2022-01-21
University of Freiburg

## Brief ##

Doberman is a versatile monitoring and process control ("slow control") package designed for mid-scale operations (O(10)-O(100) distinct quantities) but capable of rather more. Each quantity from each physical hardware module is read out independently where possible and stored individually.

## Documentation ##

See the [wiki](https://github.com/AG-Schumann/Doberman/wiki) on Github

## Prerequisites ##

The code is designed for >=python3.8 on linux but would probably work on other OSs but not older python versions. A limited number of libraries are required for the core operation (`pymongo`, `requests`, `psutil`, and `python-dateutil`), and some additional libraries may be necessary for your sensor hardware. Sensors accessed via RS-232 require the `pyserial` library.

Two databases are necessary for operation, one MongoDB and one InfluxDB. We won't cover the installation and setup here but we will discuss what Doberman expects from each of them. Cloud options exist for both databases if you don't want to physically host them yourself, but crashes will happen if network interruption affects database access.

### Infrastructure ###

You will need one server to host databases (if you're hosting them yourself) and run most of the Highlander processes. The highlanders can run on very modest hardware unless you're doing some particularly extreme things, so if your database "server" is a Raspberry Pi you'll probably be fine.

The system Doberman was designed to work for is centered around Raspberry Pi-based industrial PLCs. It will also work on an old box with a stack of RS-232 ports if that's more your style, but we recommend the PLCs.

## Installation ##
Installation guide tested for Ubuntu 18.04 LTS

1. (Optional) Create a virtual environment (Steps shown for Anaconda):
    * Download and install Anaconda for python >=3.8 for linux by following the steps (step 1 and 3, step 2 is optional) on https://www.continuum.io/downloads (at "Linux Anaconda Installation").
    * Open a new terminal to activate the Anaconda installation. If you did not include conda to your bash path, make sure to add it before each command or navigate to the anaconda directory.
    * Create an virtual environment, e.g. called 'doberman', (including pip) with `conda create --name doberman pip`. (If you aren't going to use an environment install these packages into the default (base) environment)
    * Activate environment with `source activate doberman`.
2.  Download this repository to a directory (e.g. `git clone https://github.com/AG-Schumann/doberman.git`).
    * Install the requirements via `pip install -r requirements.txt`
3. Setup a [MongoDB server](docs.mongodb.com/manual/installation)
4. Setup an [InfluxDB server](influxdata.com)
5. Setup environment variables 
    * `export DOBERMAN_MONGO_URI="mongodb://${username}:${password}@${host}:${port}/admin"`
    * `export DOBERMAN_EXPERIMENT_NAME="your experiment name here"`
6. Setup the database (see below)
7. Setup hardware drivers (see below)

## Parlance ##

There are a couple of terms it's worth defining up top:
* **device** This is a physical hardware module you connect to the system somehow. Doberman will connect to a device and ask it to read out various things, for instance a cryo controller that has multiple temperature sensors or a vacuum gauge readout with multiple channels.
* **sensor** Something that measures something, like a pressure gauge or a thermocouple or something. They can be capable of measuring multiple things, but the default assumption is that these produce one number when read by their owning _device_.
* **plugin** This is the code Doberman uses to communicate with a _device_. It is responsible for translating commands from Doberman into something the device itself understands. You'll need to write a new one for each new type of device you want to use. If you're using an existing plugin archetype Doberman already knows about (currently this includes devices communicating via ethernet and RS-232, and dedicated devices like the Revolution Pi PLC) it's 10-15 lines of code; if you're using more complex things (like other Raspberry Pi-based PLCs) you'll need a bit more.

## Usage ##

Doberman has one main executable that performs one of four primary functions. All of these respond normally to a ctrl-c and will shutdown as soon as possible (generally this is very fast but some readout processes can take some seconds). The recommended deployment paradigm is to have things run in a screen session because this facilitates automated failure recovery more so than running things under systemd. Also with `screen` it's easy to connect to it and see exactly what it's doing at any one moment.

### Alarm monitor ###

This Highlander process monitors the database for new alarms and notifies whoever is responsible that something undesired is currently happening. Start with `./Monitor.py --alarm`. You'll want one of these running 

### Pipeline monitor ###

This process (or processes) handle the various data processing pipelines you have configured. Pipelines generating alarms are all handled by one pipeline while pipelines with control funtionality are handled individually. Start with `./Monitor.py --pipeline <name>`. Use `<name> == 'pl_alarm'` for the alarm pipeline. The alarm pipeline is a Highlander, while control pipelines each run by themselves.

### Device monitor ###

These processes (one for each hardware module) connect to the readout devices, measure the configured quantities from its sensors, and push them upstream into the database. Start with `./Monitor.py --device <name>`

### Hypervisor ###

This Highlander process oversees the entire system and is responsible for interprocess communication and also starting new processes. The hypervisor can also be given devices to manage, which means that the hypervisor will automatically restart the readout process if it stops running for whatever reason.

### Other uses ###

You can also get a status snapshot of the system via `./Monitor.py --status` which will contain most recently recorded values for each measured quantity.

## Setup ##

### General infrastructure ###

We very strongly recommend having a commonly-mounted network drive that can host the code and logging directories. You can get by without this, but it's very convenient to have everything referencing one set of binaries and code, rather than having everything referencing its own. Note that as of writing the Revolution Pi is based on a Raspberry Pi v3 which runs ARMv7, and the latest anaconda release for this architecture is v3.6 which is too old for Doberman. We got around this by building python 3.9 from source for the Pis, but something based on a Raspberry Pi v4 (running ARMv8) will have access to more recent versions of anaconda. Because servers will (probably) be running x86 and Raspberries ARM, separate python binaries and environments must be maintained, but common Doberman code is possible.

### MongoDB ###

Two databases are needed inside a given instance of MongoDB. One stores configuration info, the other is used for things like log messages and alarms.

#### Config database ####

This database has a number of collections.

##### `experiment_config` #####

This collection stores a variety of documents with high-level configuration information. These include:

* Influx information. Required fields:
  * `name`: `influx`
  * `url`: `http://{host}:{port}`
  * `precision`: the precision you want timestamps stored with. We recommend `ms` (this is the default)
  * `org`: the InfluxDB organization you set up
  * `bucket`: the name of the bucket you will write data to.
  * `db`: You need to map a bucket and retention policy to the name of a database, see [this page](https://docs.influxdata.com/influxdb/v2.0/query-data/influxql/#map-unmapped-buckets) for info
  * `token`: the authorization token
* Info for the hypervisor. Required fields:
  * `name`: `hypervisor`
  * `period`: how often you want the hypervisor control loop to run in seconds. Recommend something like 60
  * `path`: the path to the `scripts` folder inside your Doberman installation
  * `restart_timeout`: how often (in seconds) the hypervisor can restart failing processes. Recommended something like 300
  * `dispatch_port`: int, a valid port number for the internal communications. Default 8942
  * `host`: the hostname of the machine on which the hypervisor runs
  * `processes`: a dictionary containing two fields, `managed` and `active`. Both should be empty lists; processes will put themselves into the `active` list when they start, and things in the `managed` list are under the control of the hypervisor.

##### `devices` #####

This collection stores information for each of the readout devices. Each document must include:
* `name`: the name of the device, must be unique. If you have several identical devices, append numbers to the end. Doberman knows that both `iseries1` and `iseries2` will use a generic `iseries` driver.
* `status`: the current status of the device, either `offline` or `online`
* `address`: a dictionary containing information about how to connect to the device. Ethernet-connected devices need `ip` and `port` fields, serial-connected devies `tty` and `baud`. The `tty` field should be something like `USB0`, the full address is formed as `'/dev/tty' + {tty}`.
* `host`: the hostname of the machine that reads this device.
* `sensors`: a dictionary containing the names and readout commands of sensors. The keys must match an entry in the `sensors` collection, and the value should be something the device understands. For instance for our cryo controller, one entry would look like `"T_TS_01": "input? a:units k"`.
* `additional_params`: a dictionary containing other quantities the device driver needs to operate, for instance constant bias values

##### `sensors` #####

This collection stores information for each sensor you read out. Each document must include:
* `name`: a unique name of the device. We found a scheme like `quantity_subsystem_number` scaled well, where `quantity` is something like pressure or temperature (or abbreviations thereof) and `subsystem` is something like `inner_cryostat` or `lab`, but pick something that works for you.
* `description`: a text description of what this sensor reads.
* `readout_interval`: how often (in seconds) this sensor should be read.
* `status`: either `online` or `offline`, should this sensor be read out?
* `topic`: what physical quantity (temperature, pressure, etc) this sensor reads.
* `subsystem`: which subsystem this sensor belongs to
* `alarm_recurrence`: how many successive values outside the thresholds must occur before an alarm state is entered.
* `alarm_thresholds`: a list with two entries that form the lower and upper alarm boundaries.
* `alarm_level`: what alarm level this sensor starts at (more on alarms later)
* `device`: the name of the device that reads this sensor
* `units`: the units of the measurement ('K', 'mbar', etc)
* `pipelines`: a list of pipelines that use values from this sensor (more on pipelines later)
* (optional) `value_xform`: polynomial coefficients to be applied to the directly measured quantity before insertion into the database. Given in little-endian form, the calculation is done as `v = sum(a_i * x**i)` where `x` is the raw value from the sensor, so a value of `[0, 1]` is `0*x**0 + 1*x**1` which is no change.


### InfluxDB ###

For influx there's 


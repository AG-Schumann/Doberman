# Doberman: Slow Control and Monitoring #

**D. Masson, J. Grigat **

Last Update: 2021-11-26
University of Freiburg

## Brief ##

Doberman is a versatile monitoring and process control ("slow control") package designed for mid-scale operations (O(10)-O(100) distinct quantities). Each quantity from each physical hardware module is read out independently.

Doberman is a versatile slow control software of a system with several controllers (e.g. observation of temperature, pressure and other quantities of an experiment). The main program (Doberman.py) is programmed generically with plugins so that it is independent of the used instruments (each instrument requires a plugin). All plugins given in the settings are started with their individual program (can also be written in an other programming language), and have to run individually, collect data and transfer their data back to the main database.

## Prerequisites ##

The code is designed for >=python3.8 on linux. A limited number of libraries are required for the core operation (`pymongo`, `numpy`, `requests`, `psutil`, and `python-dateutil`), and some additional libraries may be necessary for your sensor hardware. Sensors accessed via RS-232 require the `pyserial` library.

## Installation ##
Installation guide tested for Ubuntu 18.04 LTS

1. (Optional) Create a virtual environment (Steps shown for Anaconda):
    * Download and install Anaconda for python >=3.8 for linux by following the steps (step 1 and 3, step 2 is optional) on https://www.continuum.io/downloads (at "Linux Anaconda Installation") and accept everything required.
    * Open a new terminal to activate the Anaconda installation. If you did not include conda to your bash path, make sure to add it before each command or navigate to the anaconda directory.
    * Create an virtual environment, e.g. called 'doberman', (including pip) with `conda create --name doberman pip`. (If you aren't going to use an environment (ie, running as a system service) install these packages into the default (base) environment)
    * Activate environment with `source activate doberman`.
2.  Download this repository to a directory (e.g. `git clone https://github.com/AG-Schumann/doberman.git`).
    * Install the requirements via `pip install -r requirements.txt`
3.  Setup a [MongoDB server](docs.mongodb.com/manual/installation)
4. Setup an [InfluxDB server](influxdata.com)
4. Setup environment variables 
    * `export DOBERMAN_MONGO_URI="mongodb://${username}:${password}@${host}:${port}/admin"`
    * `export DOBERMAN_EXPERIMENT_NAME="your experiment name here"`
5. Setup the database (see below)
7. Add your Plugins. See Plugins/ExampleController.py for a generic example, or the existing plugins.

## Usage ##

Doberman has one main executable that performs one of three primary functions. All of these respond normally to a ctrl-c and will shutdown as soon as possible (generally this is very fast but some readout processes can take some seconds).

### Alarm monitor ###

This process monitors the database for new alarms and notifies whoever is responsible that something undesired is currently happening. Start with `./Monitor.py --alarm`.

### Pipeline monitor ###

This process (or processes) handle the various data processing pipelines you have configured. Pipelines generating alarms are all handled by one pipeline while pipelines with control funtionality are handled individually. Start with `./Monitor.py --pipeline <name>`

### Sensor monitor ###

These processes (one for each hardware module) connect to sensors, measure the configured quantities, and push them upstream into the database. Start with `./Monitor.py --sensor <name>`

### Other uses ###

You can also get a status snapshot of the system via `./Monitor.py --status` which will contain most recently recorded values for each measured quantity.

## Database setup ##

### MongoDB ###

Two databases are needed inside a given instance of MongoDB

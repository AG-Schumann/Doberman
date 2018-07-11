## Release notes version 2.0.0: ##
* Totally overhauled backend
  * Now uses MongoDB rather than SQL
  * Has a class-based structure rather than thousands of copy-pasted lines of code

* Reading plugin settings from file now possible with the filereading option -f[filename], where filename is optional (default is configBackup.txt). The format has to be the same as in configBackup.txt. Warning: When changing parameters or adding a new plugin from a file, the values and format of the parameters are not checked and can lead to malfuction of Doberman.

* Default values (e.g. for default testrun time, default warning/alarm repetition time, etc.) can be customized with the option -ud (update defaults).

# Doberman: Slow Control Monitoring #

**Author: P. Zappa, D. Masson **

Date: 16. June 2015, Last Update: 2018-06-28
University of Freiburg

## Brief ##

Doberman is a versatile slow control software of a system with several controllers (e.g. permanent observation of temperature, pressure and other quantities of an experiment). The main program (Doberman.py) is programmed generically with plugins so that it is independent of the used instruments (each instrument requires a plugin). All plugins given in the settings are started with their individual program (can also be written in an other programming language), and have to run individually, collect data and transfer their data back to the main program. The collected data is then stored in a database, and can be monitored.

## Prerequisites ##

The code is designed for python3.6 on linux. The computer should be compatible with all individual programs which are imported by the main Doberman slow control program. A virtual environment is recommended (tested with Anaconda) and also a MongoDB database is advised (installation guides given below). For the installation 'git' is recommended.

## Installation ##
Installation guide tested for linux ubuntu 18.04 LTS

* Install git if not pre-installed already, e.g.`sudo apt-get install git` (apt-get needs to be up to date: `sudo apt-get update`)

1. Create a virtual environment (Steps shown for Anaconda):
     * Download and install Anaconda for python 3.6 for linux by following the steps (step 1 and 3, step 2 is optional) on https://www.continuum.io/downloads (at "Linux Anaconda Installation") and accept everything required.
     * Open a new terminal to activate the Anaconda installation. If you did not include conda to your bash path, make sure to add it before each command or navigate to the anaconda directory.
     * Create an virtual environment, e.g. called 'Doberman', (incl. mongodb and pip packages) with `conda create --name Doberman pymongo pip` and accept the package downloads. (Be aware that OpenSSH is delivered with this packages for remote control and make sure your computer is protected sufficiently).
     * Activate environment with `source activate Doberman`.
2.  Download this repository to a directory (e.g. `git clone https://github.com/AG-Schumann/doberman.git`).
3.  Install and create a MongoDB server (These steps are for a local database, it is also possible to separate Doberman and the database. Follow https://docs.mongodb.com/manual/tutorial/install-mongodb-on-ubuntu/).
4. Write the connection details according to the server details (host, port, etc) used in step 3. to the txt file '*Database_connectiondetails.txt*' located in the Doberman folder. (The file must be formatted like a python dictionary, use host='localhost' if database is not separated from Doberman)
5. Install python and required packages by running `pip install -r [PATH/TO/Doberman/]requirements.txt`. (Check the wiki if errors occur)
6. Fill out the files '*MAIL_connectiondetails.txt*' and '*SMS_connectiondetails.txt*' for the warning and alarm distribution.
7. To create the tables in the database run `python Doberman.py -n` in the terminal. Confirm that you want to create all the tables (Don't start Doberman yet).
8. Add your Plugins. See Plugins/ExampleController.py for a generic example, or the existing plugins.
9. Optionally: Manage your settings (contacts, defaults, etc.) as described below ("Manage Settings").
10. Optionally: Install the Web-App if required. [Doberman WebApp](https://github.com/AG-Schumann/webapp)
## Usage ##

### Run main program ###
Navigate to your Doberman slow control folder and run `python Doberman.py [-opts]` script.

The different options '*-opt*' are:

* -t[=x]: Test modus: No alarms will be sent [for the first x minutes] (default t=2 minutes).

* -d=x: (debug) Log level: What messages get to the terminal/the log files (x=10: debug, x=20: info, x=30: warning (default), x=40: error, x=50: critical)

* -i=x: Import timeout: Timeout for each plugin at the import (x in seconds). (Default i=10 s)

* -ar: Alarm repetition: Minimal time after an alarm before a new alarm can be sent for each plugin and each channel (Default ar=5 min).

* -f[filename]: Filereading: Read your plugins settings from the file [filename] or default file (default=configBackup.txt)

## Manage Settings ##
### Add/remove a plugin to/from the settings ###
* Run `python Doberman.py -a` in the terminal to add a plugin or `python Doberman.py -r` to remove one.
* Make sure you follow the steps on wiki (https://bitbucket.org/Doberman_slowcontrol/doberman/wiki/Home -> Add a new Plugin) on how to properly write the controller specific code and where to save it.
* Optionally a plugin can be added in a file (same structure as backup file 'configBackup.txt' needed) and Doberman has to be run with -f=filename. (Warning: The format and values are not controlled when using this method).
### Change/update plugin settings ###
* Run `python Doberman.py -u` in the terminal to update status, alarm status and all alarm/warning limits
* Optionally the changes can be made in a file (same structure as backup file 'configBackup.txt' needed) and Doberman has to be run with -f=filename, or the changes made directly in the database. (Warning: The format and values are not controlled when using this method).
### Manage contatacts for alarm/warning distribution ###
Run `python Doberman.py -c` in the terminal to enable/disable and remove contacts from the list.
### Update default values ###
Run `python Doberman.py -ud` in the terminal to update the default values for testrun time (-t), loglevel (-d), importtimeout (-i), and alarm repetition time (-ar)

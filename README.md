## Release notes version 1.1.1: ##
* Reading plugin settings from file now possible with the filereading option -f[filename], where filename is optional (default is configBackup.txt). The format has to be the same as in configBackup.txt. Warning: When changing parameters or adding a new plugin from a file, the values and format of the parameters are not checked and can lead to malfuction of Doberman.

* Default values (e.g. for default testrun time, default warning/alarm repetition time, etc.) can be customized with the option -ud (update defaults).

# Doberman: Slow Control Monitoring #

**Author: P. Zappa **

Date: 16. June 2015, Last Update: 07.07.2016

## Brief ##

Doberman is a versatile slow control software of a system with several controllers (e.g. permanent observation of temperature, pressure and other quantities of an experiment). The main program (Doberman.py) is programmed generically with plugins so that it is independent of the used instruments (each instrument requires a plugin). All plugins given in the settings are started with their individual program (can also be written in an other programming language), and have to run individually, collect data and transfer their data back to the main program. The collected data is then stored in a database, and can be monitored.

## Prerequisites ##

The code is designed for python2.7 on linux. The computer should be compatible with all individual programs which are imported by the main Doberman slow control program. A virtual environment is recommended (tested with Anaconda) and also a PostgreSLQ database is advised (installation guides given below). For the installation 'git' is recommended.

## Installation ##
Installation guide tested for linux ubuntu 16.04 LTS

* Install git if not pre-installed already, e.g.`sudo apt-get install git` (apt-get needs to be up to date: `sudo apt-get update`)

1. Create a virtual environment (Steps shown for Anaconda):
     * Download and install Anaconda for python 2.7 for linux by following the steps (step 1 and 3, step 2 is optional) on https://www.continuum.io/downloads (at "Linux Anaconda Installation") and accept everything required.
     * Open a new terminal to activate the Anaconda installation. If you did not include conda to your bash path, make sure to add it before each command or navigate to the anaconda directory.
     * Create an virtual environment, e.g. called 'Doberman', (incl. postgresql and pip packages) with `conda create --name Doberman postgresql pip` and accept the package downloads. (Be aware that OpenSSH is delivered with this packages for remote control and make sure your computer is protected sufficiently).
     * Activate environment with `source activate Doberman`.
2.  Download this repository to a directory (e.g. `git clone https://Doberman_slowcontrol@bitbucket.org/Doberman_slowcontrol/doberman.git`).
3.  Install and create a PostgreSLQ Database (These steps are for a local database, it is also possible to separate Doberman and the database. Tutorials: https://help.ubuntu.com/community/PostgreSQL). Steps (for a local server):
     * Download posgresql: `sudo apt-get install postgresql postgresql-contrib`.
     * Create the role 'postgres' with `sudo -u postgres psql postgres` and choose a password with `\password postgres`.
     * Optionally (recommended): Create additional roles with different access rights. (https://www.postgresql.org/docs/8.1/static/sql-createrole.html)
     * Quit postgres with `\q`
     * Create a database, e.g. named "Doberman", with `sudo -u postgres createdb Doberman`.
4. Write the connection details according to the database name (e.g. Doberman), password and role ("postgres" or name of the additionally created role) used in step 3. to the txt file '*Database_connectiondetails.txt*' located in the Doberman folder. (Maintain the format, use host='localhost' if database is not separated from Doberman)
5. Install python and required packages by running `pip install -r [PATH/TO/Doberman/]requirements.txt`. (Check the wiki if errors occur)
6. Fill out the files '*MAIL_connectiondetails.txt*' and '*SMS_connectiondetails.txt*' for the warning and alarm distribution.
7. To create the tables in the database run `python Doberman.py -n` in the terminal. Confirm that you want to create all the tables (Don't start Doberman yet).
8. Add your Plugins. Make sure you follow the steps on wiki (https://bitbucket.org/Doberman_slowcontrol/doberman/wiki/Home -> "Add a new Plugin") on how to add and properly write the Plugin specific code and where to save it.
9. Optionally: Manage your settings (contacts, defaults, etc.) as described below ("Manage Settings").
10. Optionally: Install the Web-App if required. ** MISSING: Link to Web-App **
## Usage ##

### Run main program ###
Navigate to your Doberman slow control folder and run `python Doberman.py [-opts]` script.

The different options '*-opt*' are:

* -t[=x]: Test modus: No alarms will be sent [for the first x minutes] (default t=2 minutes).

* -d=x: (debug) Log level: What messages get to the terminal/the log files (x=10: debug, x=20: info, x=30: warning (default), x=40: error, x=50: critical)

* -i=x: Import timeout: Timeout for each plugin at the import (x in seconds). (Default i=10 s)

* -o=x[,y,]: Occupied ttyUSB ports: Use this option if the Doberman slow control should not connect to a [several] ttyUSB port x [and y,...]. This can be useful if you don't want to disturb a controller which is already connected.

* -wr: Warning repetition: Minimal time after a warning or alarm until a new warning can be sent for each plugin and each channel (Default wr=10 min).

* -ar: Alarm repetition: Minimal time after an alarm before a new alarm can be sent for each plugin and each channel (Default ar=5 min).

* -f[filename]: Filereading: Read your plugins settings from the file [filename] or default file (default=configBackup.txt)

## Manage Settings ##
### Add/remove a plugin to/from the settings ###
* Run `python Doberman.py -a` in the terminal to add a plugin or `python Doberman.py -r` to remove one.
* Make sure you follow the steps on wiki (https://bitbucket.org/Doberman_slowcontrol/doberman/wiki/Home -> Add a new Plugin) on how to properly write the controller specific code and where to save it.
* Optionally a plugin can be added in a file (same structure as backup file 'configBackup.txt' needed) and Doberman has to be run with -f=filename. (Warning: The format and values are not controlled when using this method).
### Change/update plugin settings ###
* Run `python Doberman.py -u` in the terminal to update status, alarm status and all alarm/warning limits
* or `python Doberman.py -uu` to update all config parameters.
* Optionally the changes can be made in a file (same structure as backup file 'configBackup.txt' needed) and Doberman has to be run with -f=filename. (Warning: The format and values are not controlled when using this method).
### Manage contatacts for alarm/warning distribution ###
Run `python Doberman.py -c` in the terminal to add, change, enable/disable and remove contacts from the list.
### Update default values ###
Run `python Doberman.py -ud` in the terminal to update the default values for testrun time (-t), loglevel (-d), importtimeout (-i), occupied ttyUSB ports (-o), warning repetition time (-wr) and alarm repetition time (-ar)

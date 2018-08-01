## Release notes version 2.0.0: ##
* Totally overhauled backend
  * Now uses MongoDB rather than SQL
  * Has a class-based structure rather than thousands of copy-pasted lines of code

* Reading plugin settings from file now possible with the filereading option -f[filename], where filename is optional (default is configBackup.txt). The format has to be the same as in configBackup.txt. Warning: When changing parameters or adding a new plugin from a file, the values and format of the parameters are not checked and can lead to malfuction of Doberman.

* Default values (e.g. for default testrun time, default warning/alarm repetition time, etc.) can be customized with the option -ud (update defaults).

# Doberman: Slow Control Monitoring #

**Author: P. Zappa, D. Masson **

Date: 16. June 2015, Last Update: 2018-07-30
University of Freiburg

## Brief ##

Doberman is a versatile slow control software of a system with several controllers (e.g. permanent observation of temperature, pressure and other quantities of an experiment). The main program (Doberman.py) is programmed generically with plugins so that it is independent of the used instruments (each instrument requires a plugin). All plugins given in the settings are started with their individual program (can also be written in an other programming language), and have to run individually, collect data and transfer their data back to the main database.

## Prerequisites ##

The code is designed for python3.6 on linux. The computer should be compatible with all individual programs which are imported by the main Doberman slow control program. A virtual environment is recommended (tested with Anaconda) and also a MongoDB database is necessary (installation guides given below). For the installation 'git' is recommended.

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
4. Write the connection details according to the server details (host, port, etc) used in step 3. to the txt file '*Database_connectiondetails.txt*' located in the 'settings' folder. The file must be formatted like a python dictionary.
5. Install python and required packages by running `pip install -r [PATH/TO/Doberman/]requirements.txt`. (Check the wiki if errors occur)
6. Setup the database (see below)
7. Add your Plugins. See Plugins/ExampleController.py for a generic example, or the existing plugins.
8. Optionally: Manage your settings (contacts, defaults, etc.) as described below ("Manage Settings").
9. Optionally: Install the Web-App if required. [Doberman WebApp](https://github.com/AG-Schumann/webapp)
## Usage ##

### Run main program ###
Navigate to your Doberman slow control folder and run `./Doberman.py [-opts]`.

The different options '*-opt*' are:

* --runmode <runmode>: Which set of operational parameters to load. Current options are 'default' (default), 'testing', and 'recovery'. Determines values like logging verbosity and alarm message frequency.

* --version: Prints the current version and exits.

## Manage Settings ##
### Add/remove a plugin to/from the settings ###
* Run `./DobermanDB.py --add <filename>` in the terminal to add a plugin or `python Doberman.py --remove <plugin>` to remove one. The file specified by <filename> must be a python-readable dictionary with the configuration for the specified controller.
* Make sure you follow the steps on wiki (https://github.com/AG-Schumann/Doberman/wiki) -> Add a new Plugin) on how to properly write the controller-specific code.

### Change/update plugin settings ###
* Run `./DobermanDB.py --update` in the terminal to update some controller settings, contact statuses, and operational parameters
* Commands can be sent to Doberman or to controllers by `python DobermanDB.py --command <command>`. See the wiki for formatting details.

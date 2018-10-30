## Release notes version 3.x: ##

* Now functions as a system service (ie, you can't accidentally turn it off)
* Overhauled alarm system:
  * Moves away from monolithic hard-coded "warning" and "alarm" levels to a more adaptable level-based system. Controllers now have more options for escalation of alarm states. Additionally, message protocols (ie, how alarm messages are distributed) can now be set on a per-level basis.
  * Changing things via the command-line is now limited to contact statuses as the settings are rather too structured to make easy changing via prompts.
* Issuing commands to controllers is now more structured

## Release notes version 2.0.0: ##
* Totally overhauled backend
  * Now uses MongoDB rather than SQL
  * Has a class-based structure rather than thousands of copy-pasted lines of code

* Reading plugin settings from file now possible with the filereading option -f[filename], where filename is optional (default is configBackup.txt). The format has to be the same as in configBackup.txt. Warning: When changing parameters or adding a new plugin from a file, the values and format of the parameters are not checked and can lead to malfuction of Doberman.

* Default values (e.g. for default testrun time, default warning/alarm repetition time, etc.) can be customized with the option -ud (update defaults).

# Doberman: Slow Control and Monitoring #

**Author: D. Masson **

Last Update: 2018-10-30
University of Freiburg

## Brief ##

Doberman is a versatile slow control software of a system with several controllers (e.g. observation of temperature, pressure and other quantities of an experiment). The main program (Doberman.py) is programmed generically with plugins so that it is independent of the used instruments (each instrument requires a plugin). All plugins given in the settings are started with their individual program (can also be written in an other programming language), and have to run individually, collect data and transfer their data back to the main database.

## Prerequisites ##

The code is designed for python3.6 on linux. The computer should be compatible with all individual programs which are imported by the main Doberman slow control program. A virtual environment can be used (tested with Anaconda) and also a MongoDB database is necessary (installation guides given below).

## Installation ##
Installation guide tested for Ubuntu 18.04 LTS

* Install git if not pre-installed already, e.g.`sudo apt-get install git` (apt-get needs to be up to date: `sudo apt-get update`)

1. (Optional) Create a virtual environment (Steps shown for Anaconda):
     * Download and install Anaconda for python 3.6 for linux by following the steps (step 1 and 3, step 2 is optional) on https://www.continuum.io/downloads (at "Linux Anaconda Installation") and accept everything required.
     * Open a new terminal to activate the Anaconda installation. If you did not include conda to your bash path, make sure to add it before each command or navigate to the anaconda directory.
     * Create an virtual environment, e.g. called 'Doberman', (incl. mongodb and pip packages) with `conda create --name Doberman pymongo pip pyserial`. (If you aren't going to use an environment (ie, running as a system service) install these packages into the default (base) environment)
     * Activate environment with `source activate Doberman`.
2.  Download this repository to a directory (e.g. `git clone https://github.com/AG-Schumann/doberman.git`).
3.  Install and create a MongoDB server (These steps are for a local database, it is also possible to separate Doberman and the database. Follow https://docs.mongodb.com/manual/tutorial/install-mongodb-on-ubuntu/).
4. Write the connection details according to the server details (username, host, port, etc) used in step 3. to the txt file '*connection_uri*' located in the main folder.
5. Install python and required packages by running `pip install -r [PATH/TO/Doberman/]requirements.txt`. (Check the wiki if errors occur)
6. Setup the database (see below)
7. Add your Plugins. See Plugins/ExampleController.py for a generic example, or the existing plugins.
8. (Optional) Manage your settings (contacts, defaults, etc.) as described below ("Manage Settings").
9. (Optional) Install the Web-App if required. [Doberman WebApp](https://github.com/AG-Schumann/webapp)
10. (Optional) Install Doberman as a system service. Copy `doberman.service` to `/lib/systemd/system`
## Usage ##

### Run main program ###
Navigate to your Doberman slow control folder and run `./Doberman.py [-opts]` (if a system service, start with `systemctl start doberman`.

The different options '*-opt*' are:

* --refresh: refreshes the ttyUSB mapping (done automatically when necessary)
* --version: Prints the current version and exits.

By default doberman starts in the `testing` runmode. Set it to your desired runmode via `./DobermanDB.py runmode <runmode>`.

### Running plugins ###
Plugins are all run independently of the main doberman executable. Plugins can either be manually started (`./Plugin.py --name <plugin name> [--runmode <runmode>]`) or automatically started (`./DobermanDB.py start <plugin name>`).

Plugins can be stopped by either ctrl-c (if started manually) or automatically (`./DobermanDB.py stop <plugin name>`).

See the command help (`./DobermanDB.py help`) for more info.

## Manage Settings ##
### Add a plugin ###
* Run `./DobermanDB.py --add <filename>` in the terminal to add a plugin. The file specified by <filename> must be a python-readable dictionary with the configuration for the specified controller.
* Make sure you follow the steps on wiki (https://github.com/AG-Schumann/Doberman/wiki/Plugins) on how to properly write the controller-specific code.

### Change settings ###
* Commands can be sent to Doberman or to controllers by `./DobermanDB.py <command>`. See the wiki for formatting details.
* Some parameters can be changed via the command line (`./DobermanDB.py --update`)

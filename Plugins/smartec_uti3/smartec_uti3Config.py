#! /usr/bin/env python3.3

# Choose the measurement mode from the list below:
# 0 -> Mode 0  - 5 Capacitors, 0-2 pF
# 1 -> Mode 1  - 3 Capacitors, 0-2 pF
# 2 -> Mode 2  - 5 Capacitors, 0-12 pF
# 3 -> Mode 3  - Unavailable
# 4 -> Mode 4  - 3 Capacitors, variable range to 300 pF
# 5 -> Mode 5  - Platinum resistor Pt100 - Pt1000, 4 wire
# 6 -> Mode 6  - Thermistor 1k-25k, 4 wire
# 7 -> Mode 7  - 2 or 3 platinum resistors Pt100 - Pt1000
# 8 -> Mode 8  - 2 or 3 thermistors 1k-25k
# 9 -> Mode 9  - Resistive bridge, ref. is Vbridge,+/- 200 mV
# A -> Mode 10 - Resistive bridge, ref. is Vbridge,+/- 12.5 mV
# B -> Mode 11 - Resistive bridge, ref. is Ibridge,+/- 200 mV
# C -> Mode 12 - Resistive bridge, ref. is Ibridge,+/- 12.5 mV
# D -> Mode 13 - Resistive bridge and 2 resistors,+/- 200 mV
# E -> Mode 14 - Resistive bridge and 2 resistors,+/- 12.5 mV
# F -> Mode 15 - 3 Potentiometers 1k-50k

mode = 4

# Enter the reference capacitance/ resistance without unit. Restart doberman when changed
# Output values will have the same unit. Set to 1 to just get the measurement ratio.

ref = 181

# Similar to ref for the resistive bridges. Set to 1 to get the bridge imbalance

bridgeref = 1

# Enter the number of final output values (between 1 and 3) to be stored in the database
# Set the same value in doberman plugin configuration
# Example: 1-3 outputs for mode 0; 1 output for mode 1;...   (not implemented yet, leave at 1)

output = 1

# Only change this to 3 if using resistive modes with 3-wire connection. Otherwise set to anything else

wire = 4

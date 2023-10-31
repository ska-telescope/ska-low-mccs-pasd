# pylint: skip-file
# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This is a basic temporary script to generate a configuration for FieldStation."""
import json

NUMBER_OF_SMARTBOXES = 24
NUMBER_OF_SMARTBOX_PORTS = 12
NUMBER_OF_ANTENNAS = 256

_antenna_mask = [False for _ in range(NUMBER_OF_ANTENNAS + 1)]

for antenna in range(1, 13):
    _antenna_mask[antenna] = True

_antenna_mask[90] = True

_antenna_mapping = {
    smartbox_no * NUMBER_OF_SMARTBOX_PORTS
    + smartbox_port
    + 1: [smartbox_no + 1, smartbox_port + 1]
    for smartbox_no in range(0, NUMBER_OF_SMARTBOXES)
    for smartbox_port in range(0, NUMBER_OF_SMARTBOX_PORTS)
    if smartbox_no * NUMBER_OF_SMARTBOX_PORTS + smartbox_port < NUMBER_OF_ANTENNAS
}
_smartbox_mapping = {port: port for port in range(1, NUMBER_OF_SMARTBOXES + 1)}
_smartbox_mapping[1] = 2
_smartbox_mapping[2] = 1

antennas = {}

for antenna in range(1, NUMBER_OF_ANTENNAS + 1):
    antenna_info = {
        "smartbox": str(_antenna_mapping[antenna][0]),
        "smartbox_port": _antenna_mapping[antenna][1],
        "masked": _antenna_mask[antenna],
    }
    antennas[antenna] = antenna_info

antennass = {"antennas": antennas}

smartboxes = {}
for smartbox in range(1, NUMBER_OF_SMARTBOXES + 1):
    fndh_port = {"fndh_port": _smartbox_mapping[smartbox]}
    smartboxes[str(smartbox)] = fndh_port

pasd = {"pasd": {"smartboxes": smartboxes}}

config = antennass | pasd

with open("src/ska_low_mccs_pasd/field_station/resources/config.json", "w") as f:
    f.write(json.dumps(config))

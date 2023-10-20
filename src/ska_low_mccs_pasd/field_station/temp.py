# pylint: skip-file
# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""This module implements the MCCS FieldStation device."""
import json

SMARTBOX_NUMBER = 24
SMARTBOX_PORTS = 12
ANTENNA_NUMBER = 256

_antenna_mask = [False for _ in range(ANTENNA_NUMBER + 1)]

for antenna in range(1, 13):
    _antenna_mask[antenna] = True

_antenna_mask[90] = True

_antenna_mapping = {
    smartbox_no * SMARTBOX_PORTS
    + smartbox_port
    + 1: [smartbox_no + 1, smartbox_port + 1]
    for smartbox_no in range(0, SMARTBOX_NUMBER)
    for smartbox_port in range(0, SMARTBOX_PORTS)
    if smartbox_no * SMARTBOX_PORTS + smartbox_port < ANTENNA_NUMBER
}
_smartbox_mapping = {port + 1: port + 1 for port in range(0, SMARTBOX_NUMBER)}
_smartbox_mapping[1] = 2
_smartbox_mapping[2] = 1

antennas = {}

for antenna in range(1, ANTENNA_NUMBER + 1):
    antenna_info = {
        "smartbox": str(_antenna_mapping[antenna][0]),
        "smartbox_port": _antenna_mapping[antenna][1],
        "masked": _antenna_mask[antenna],
    }
    antennas[antenna] = antenna_info

antennass = {"antennas": antennas}

smartboxes = {}
for smartbox in range(1, SMARTBOX_NUMBER + 1):
    fndh_port = {"fndh_port": _smartbox_mapping[smartbox]}
    smartboxes[str(smartbox)] = fndh_port

pasd = {"pasd": {"smartboxes": smartboxes}}

config = antennass | pasd

with open("config.txt", "a") as f:
    f.write(json.dumps(config))

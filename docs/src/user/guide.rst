==================
PaSD Tango Devices
==================
  
The PaSD (Power and Signal Distribution) system is controlled and monitored via
a number of Tango devices, described below.

---------------------
PaSD Bus
---------------------
The PaSD Bus Tango device is responsible for funneling all communications
between MCCS and the PaSD hardware. It ensures that only one request is sent on
the bus at any one time, and handles the prioritization of requests. It also
supports a number of commands.

---------------------
FNDH
---------------------
The FNDH Tango device reflects the state of the Field Node and Distribution Hub,
including port power status.

---------------------
Smartboxes
---------------------
The Smartbox Tango devices reflect the state of the individual smartboxes,
including port power status.

---------------------
FNCC
---------------------
The FNCC Tango device reflects the state of the Field Node Communications
Controller.
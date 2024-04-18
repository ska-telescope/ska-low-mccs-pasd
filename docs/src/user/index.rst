==================
PaSD Tango devices
==================

The Power and Signal Distribution (PaSD) system is controlled and monitored 
via a number of Tango devices, described in the following sections:

.. toctree::
  :maxdepth: 1
  :titlesonly:

  Field station<field_station>
  PaSD bus<pasd_bus>
  FNDH<fndh>
  SMART Box<smartbox>
  FNCC<fncc>

For more detailed information on the hardware the Tango devices are interfacing with, refer to the 
`PaSD Monitor & Control System Firmware Description <https://ska-aw.bentley.com/SKAProd/Framework/Object.aspx?o=64000&t=3>`_ 
document on the SKAO ALIM system.

Overview of the PaSD system
---------------------------
Each of the stations in SKA-Low will consist of 256 antennae distributed in a circle
40m in diameter. Each of the 256 antennae is connected via coaxial cable to a
nearby SMART Box, located on the ground screen between the antennae. The
SMART Box delivers DC power over the coaxial cable to an LNA (low noise
amplifier) in the antenna, and converts the incoming radio frequency (RF) from
the antenna into an optical RF signal on an outgoing fibre.

Each station will typically have 24 SMART Boxes in the field, and each SMART Box
has 12 antenna ports, making a total of 288 available inputs for antennae. Since
there are only 256 antennae in a station, not all of the ports on each SMART Box
will necessarily be in use at any given time. The remainder are available as spares
in case of faults.

Each SMART Box has an internal low-speed, low-power microcontroller to monitor
temperatures, currents and voltages, and to switch antennae on and off as
required. Power comes from a single Field Node Distribution Hub (FNDH) for the
entire station. A low-speed (9600 bps) low-RFI (radio frequency interference)
communications link to the SMART Box microcontroller is carried over the 48Vdc
power line.

Each station has a FNDH to provide power and communications for the SMART
Boxes, and to act as a fibre aggregation point for the fibres carrying RF signals
from the SMART Boxes to go back to the control building. The FNDH is powered
from 240 VAC mains power, and has two 48Vdc power supplies for the SMART
Boxes, and a 5V power supply for the local microcontroller.

The FNDH has 28 possible slots in which a Power and Data over Coax (PDoC) card
can be installed, each providing a port to which a SMART Box can be connected.
Again, not all of the slots will have PDoC cards installed at any given time, and
not all PDoC cards will be connected to a SMART Box. The extra ports are provided
for redundancy.

A single fibre pair from the control building to the FNDH is connected to an
ethernet-serial bridge (via a media converter), allowing the monitoring control and
calibration system (MCCS) in the control building to send and receive data over
the network to a given FNDH (with a unique IP address). The serial data from the
ethernet-serial bridge is passed to the local microcontroller in the FNDH, and
shared with all of the SMART Boxes via a multi-drop serial bus. When the MCCS
sends data, every device on the shared bus (the FNDH microcontroller and all of
the SMART Boxes in the station) receives it.

The microcontroller in the FNDH monitors temperatures, voltages and currents in
the FNDH, and allows the 28 possible output ports to be switched on and off. It
does NOT communicate with the SMART Boxes at all. Instead, the SMART Boxes
are controlled by the MCCS in the main building, talking to them directly via serial
traffic over the shared serial bus.

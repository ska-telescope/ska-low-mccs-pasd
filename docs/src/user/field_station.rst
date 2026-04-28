===================
Fieldstation device
===================

The Fieldstation Tango device is used to control the Power and Signal Distribution System components
for a field station, comprising a single FNDH and 24 smartboxes (see :ref:`pasd-tango-devices` for an
overview of the architecture). Most of the control and monitoring is done directly through the
relevant lower level Tango devices, but the antennas can be powered on and off through this device,
and the thermistor mounted on the floor of the FNDH EP Enclosure is also exposed as an attribute.

In addition, the Fieldstation device provides a way of setting AdminMode on all PaSD components
from a single place, and captures an overall health state of the field station. The health state is
calculated from the health of the FNDH and smartboxes; possible values are:

* 0 = OK: All components are in a normal state.
* 1 = DEGRADED: At least one component is in a warning or alarm state.
* 2 = FAILED: Either the FNDH or all smartboxes are in an alarm state.
* 3 = UNKNOWN: It is unable to determine its health (also its initial state).

The following attributes are provided by the Fieldstation device:

1. `OutsideTemperature` - the outside temperature in degrees Celsius, as reported by the FNDH
   (thermistor mounted on the floor of the FNDH EP Enclosure)
2. `HealthState` - the overall health state of the field station
3. `HealthReport` - A report of the health state of the field station, including the health state of
   each component.

See :ref:`fndh-health-evaluation` and :ref:`smartbox-health-evaluation` for more details on how the
health of the FNDH and smartboxes is evaluated.

The following commands are also provided:

+------------------------+------------------------------+-------------------------------------------------------------------+
| Command name           | Arguments                    | Description                                                       |
+========================+==============================+===================================================================+
| PowerOnAntenna         | Antenna name, e.g. "sb01-02" | Request to power on the specified antenna                         |
+------------------------+------------------------------+-------------------------------------------------------------------+
| PowerOffAntenna        | Antenna name, e.g. "sb01-02" | Request to power off the specified antenna                        |
+------------------------+------------------------------+-------------------------------------------------------------------+
| SetAntennaMasking      | JSON antenna-mask dict       | Set the masked status for one or more antennas (see below)        |
+------------------------+------------------------------+-------------------------------------------------------------------+
| Standby                | None                         | Turn on all smartboxes, but leave their ports switched off        |
+------------------------+------------------------------+-------------------------------------------------------------------+
| Off                    | None                         | Turn off power to all antennas in the fieldstation                |
+------------------------+------------------------------+-------------------------------------------------------------------+
| On                     | None                         | Turn on power to all antennas in the fieldstation                 |
+------------------------+------------------------------+-------------------------------------------------------------------+

The names of the antennas take the form of the string "sbxx-yy" where xx represents the smartbox number, and yy represents the
FEM port number on that smartbox.

Antenna masking
---------------

``SetAntennaMasking`` accepts a JSON string that maps antenna names to a boolean masked status, for
example::

    '{"sb01-01": true, "sb03-01": false}'

``true`` means the antenna is masked — its port will not be powered on. ``false`` unmasks the
antenna. Antennas absent from the dict are left unchanged, so partial updates are safe. The command
routes each antenna to its owning smartbox automatically; antennas belonging to different smartboxes
can be included in a single call.

The command returns ``REJECTED`` if none of the supplied antenna names are found on any smartbox
(e.g. all names are unrecognised, or the dict is empty). Antennas that cannot be routed to any
smartbox are logged as a warning but do not prevent the rest of the call from succeeding.





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
supports the following commands:

+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| Command name              | Arguments                           | Description                                                                                     |
+===========================+=====================================+=================================================================================================+
| InitializeFndh            | None                                | Request to transition to operational state. This is needed after power-up and alarm conditions. |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| InitializeSmartbox        | Smartbox device id                  | Request to transition to operational state. This is needed after power-up and alarm conditions. |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetFnccStatus           | None                                | Reset an FNCC communications error                                                              |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| SetFndhPortPowers         | See: `Setting Port Powers`_         | Request to set multiple FNDH port powers in a single command                                    |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| SetFndhLedPattern         | See: `Setting LED Patterns`_        | Control the FNDH service LED                                                                    |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| SetFndhLowPassFilters     | See: `Setting Filter Constants`_    | Set the low pass filters for the FNDH                                                           |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetFndhAlarms           | None                                | Clear the FNDH's alarm flags register                                                           |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetFndhWarnings         | None                                | Clear the FNDH's warning flags register                                                         |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetFndhPortBreaker      | Port number                         | NOT IMPLEMENTED - TO BE REMOVED                                                                 |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| SetSmartboxPortPowers     | See: `Setting Port Powers`_         | Request to set multiple Smartbox port powers in a single command                                |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| SetSmartboxLedPattern     | See: `Setting LED Patterns`_        | Control the Smartbox's service LED                                                              |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| SetSmartboxLowPassFilters | See: `Setting Filter Constants`_    | Set the low pass filters for a Smartbox                                                         |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetSmartboxPortBreaker  | See: `Resetting Breakers`_          | Reset a Smartbox's port breaker                                                                 |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetSmartboxAlarms       | Smartbox device id                  | Clear the Smartbox's alarm flags register                                                       |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+
| ResetSmartboxWarnings     | Smartbox device id                  | Clear the Smartbox's warning flags register                                                     |
+---------------------------+-------------------------------------+-------------------------------------------------------------------------------------------------+

Setting Filter Constants
------------------------
The ``SetFndhLowPassFilters`` command accepts a JSON object with the following keys:

- *cutoff* - Cut-off frequency to use for the low-pass filtering (between 0.1 and 1000.0)
- *extra_sensors* (optional) - Write the filter constant to the extra sensors' registers after the LED status register (default: False)

The target cut-off frequency is used to calculate a filter decay constant which is written to the
FNDH telemetry registers to enable low-pass filtering. If *extra_sensors* is set to True, the
constant is also written to the extra sensors' registers. 

The ``SetSmartboxLowPassFilters`` command works as above to set the filtering on a given Smartbox with
the additional required key:

- *smartbox_number* - Device id of the Smartbox being addressed

**IMPORTANT NOTE**: The specified cut-off frequency is peristed to the Tango database (overwriting the value in
the deployment configuration) and the calculated constant is automatically written to *ALL* sensor registers
of the FNDH and smartboxes after MccsPasdBus is initialised and set ONLINE, and after any of them are
powered on (regardless of which command was used).

Resetting Breakers
------------------
The ``ResetSmartboxPortBreaker`` command accepts a JSON object with the following keys:

- *smartbox_number* - The device id of the Smartbox being addressed
- *port_number* - Number of the port whose breaker is to be reset

Setting Port Powers
-------------------
The MccsPasdBus ``SetFNDHPortPowers`` and FNDH/Smartbox ``SetPortPowers`` commands accept
a JSON object with the following keys:

- *port_powers* - An array of desired power states (True for 'On', False for 'Off', None for no change)
- *stay_on_when_offline* - Whether to stay on when the FNPC is offline

The ``SetSmartboxPortPowers`` command accepts a JSON object with the following keys:

- *smartbox_number* - The device id of the Smartbox being addressed
- *port_powers* - An array of desired power states (True for 'On', False for 'Off', None for no change)
- *stay_on_when_offline* - Whether to stay on when the FNSC is offline

All requested changes of state are issued in a single Modbus command.

Setting LED Patterns
--------------------
The ``SetFndhLedPattern`` command controls the FNDH service LED and accepts a JSON object
with the following keys:

- *pattern* - One of the following strings:

    - "OFF"
    - "ON"
    - "VFAST"
    - "FAST"
    - "SLOW"
    - "VSLOW"

The ``SetSmartboxLedPattern`` controls the Smartbox service LEDs and accepts a JSON object
with the following keys:

- *smartbox_number* - The device id of the Smartbox being addressed.
- *pattern* - One of the following strings:

    - "OFF"
    - "ON"
    - "VFAST"
    - "FAST"
    - "SLOW"
    - "VSLOW"


---------------------
FNDH
---------------------
The FNDH Tango device reflects the state of the Field Node Peripheral Controller (FNPC),
including the status of the PDOC ports which are used to power the Smartboxes. The
following attributes are exposed; note that all temperatures are in deg C and all
attributes are read-only with the exception of the alarm and warning thresholds which
are read/write.

+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Tango Attribute name                 | Register address(es)   | Register description                                                     |
+======================================+========================+==========================================================================+
| ModbusRegisterMapRevisionNumber      | 1                      | Modbus FNPC register map revision number, fixed at firmware compile time |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PcbRevisionNumber                    | 2                      | FNCB revision number, fixed at firmware compile time                     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| CpuId                                | 3-4                    | Microcontroller device ID                                                |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| ChipId                               | 5-12                   | Microcontroller unique device ID                                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FirmwareVersion                      | 13                     | Firmware revision number, fixed at compile time                          |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Uptime                               | 14-15                  | Time, in seconds, since FNPC boot                                        |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| SysAddress                           | 16                     | Modbus address                                                           |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vVoltages                       | 17-18                  | 48Vdc COSEL SMPS 1 output voltage                                        |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vCurrent                        | 19                     | 48Vdc COSEL SMPS output current                                          |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vTemperatures                   | 20-21                  | Thermistors mounted on the COSEL SMPS base plate                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PanelTemperature                     | 22                     | *NOT IMPLEMENTED IN HARDWARE*                                            |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FncbTemperature                      | 23                     | Field Node Controller Board temperature                                  | 
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FncbHumidity                         | 24                     | Field Node Controller Board humidity (%)                                 |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PasdStatus                           | 25                     | FNDH System status (see below)                                           |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| LedPattern                           | 26                     | Status of the service and status LEDs                                    |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| CommsGatewayTemperature              | 27                     | Thermistor mounted on the external surface of the Comms Gateway          |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PowerModuleTemperature               | 28                     | Thermistor mounted on the external surface of the Power Module enclosure |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| OutsideTemperature                   | 29                     | Thermistor mounted on the floor of the FNDH EP Enclosure                 |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| InternalAmbientTemperature           | 30                     | Thermistor mounted on the roof of the FNDH EP Enclosure                  |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortForcings                         | 36-64                  | Port forcing status for each port ("ON", "OFF", or "NONE")               |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortsDesiredPowerOnline              | 36-64                  | Desired state of each port when FNPC is ONLINE ("OFF, "ON" or "DEFAULT") |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortsDesiredPowerOffline             | 36-64                  | Desired state of each port when FNPC is OFFLINE ("OFF, "ON" or "DEFAULT")|
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortsPowerSensed                     | 36-64                  | Power sensed status for each port (True or False)                        |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortsPowerControl                    | 36-64                  | Power control line ON/OFF status (True if port can be turned on)         |                                                              
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vVoltage1Thresholds             | 1001-1004              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vVoltage2Thresholds             | 1005-1008              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vCurrentThresholds              | 1009-1012              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vTemperature1Thresholds         | 1013-1016              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Psu48vTemperature2Thresholds         | 1017-1020              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PanelTemperatureThresholds           | 1021-1024              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FncbTemperatureThresholds            | 1025-1028              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| HumidityThresholds                   | 1029-1032              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| CommsGatewayTemperatureThresholds    | 1033-1036              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PowerModuleTemperatureThresholds     | 1037-1040              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| OutsideTemperatureThresholds         | 1041-1044              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| InternalAmbientTemperatureThresholds | 1045-1048              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| WarningFlags                         | 10129                  | List of sensors outside their warning thresholds                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| AlarmFlags                           | 10131                  | List of sensors outside their alarm thresholds                           |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+

The FNDH ``PasdStatus`` attribute should be interpreted as follows:

+---------------------------------+--------------------------------------------------+
| *PasdStatus* attribute value    | Meaning                                          |
+=================================+==================================================+
| OK                              | Initialised, system health OK                    |
+---------------------------------+--------------------------------------------------+
| WARNING                         | Initialised, and at least one sensor in WARNING  |
+---------------------------------+--------------------------------------------------+
| ALARM                           | Initialised, and at least one sensor in ALARM    |
+---------------------------------+--------------------------------------------------+
| RECOVERY                        | Initialised, and at least one sensor in RECOVERY |
+---------------------------------+--------------------------------------------------+
| UNINITIALISED                   | Not initialised, regardless of sensor states     |
+---------------------------------+--------------------------------------------------+
| POWERUP                         | Local tech initiated powerup sequence            |
+---------------------------------+--------------------------------------------------+

FNDH commands
-------------
The FNDH device supports the following commands:

+------------------------+-------------------------------------+-------------------------------------------------------------------+
| Command name           | Arguments                           | Description                                                       |
+========================+=====================================+===================================================================+
| PowerOnPort            | Port number                         | Request to power on the specified port                            |                   
+------------------------+-------------------------------------+-------------------------------------------------------------------+
| PowerOffPort           | Port number                         | Request to power off the specified port                           |                    
+------------------------+-------------------------------------+-------------------------------------------------------------------+
| SetPortPowers          | See: `Setting Port Powers`_         | Initialise the FNDH and request the specified port power statuses |
+------------------------+-------------------------------------+-------------------------------------------------------------------+                    


Alarm recovery procedure
------------------------
When the FNDH ``PasdStatus`` attribute indicates an ALARM, WARNING or RECOVERY state, the
``WarningFlags`` and ``AlarmFlags`` attributes can be interrogated to find out which
sensors have gone outside their threshold values. These registers need to be manually
cleared by issuing the ``ResetFndhAlarms()`` and ``ResetFndhWarnings()`` commands after
reading.

The PaSD automatically transitions to the RECOVERY state when the relevant
sensor values return to within their alarm thresholds. To return the FNDH to an operational
state after such an event, the ``initialiseFNDH()`` command should be executed.

---------------------
Smartboxes
---------------------
The Smartbox Tango devices reflect the state of the individual FNSC (Field Node Smartbox
Controller) devices, including FEM port power status. The following attributes are exposed;
note all attributes are read-only with the exception of the alarm and warning thresholds,
and all temperatures are in deg C:

+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Tango Attribute name                 | Register address(es)   | Register description                                                     |
+======================================+========================+==========================================================================+
| ModbusRegisterMapRevisionNumber      | 1                      | Modbus FNPC register map revision number, fixed at firmware compile time |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PcbRevisionNumber                    | 2                      | FNCB revision number, fixed at firmware compile time                     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| CpuId                                | 3-4                    | Microcontroller device ID                                                |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| ChipId                               | 5-12                   | Microcontroller unique device ID                                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FirmwareVersion                      | 13                     | Firmware revision number, fixed at compile time                          |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Uptime                               | 14-15                  | Time, in seconds, since FNPC boot                                        |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| SysAddress                           | 16                     | Modbus address                                                           |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| InputVoltage                         | 17                     | Incoming 48Vdc voltage                                                   |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PowerSupplyOutputVoltage             | 18                     | PSU output voltage                                                       |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PowerSupplyTemperature               | 19                     | PSU temperature                                                          |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PcbTemperature                       | 20                     | PCB temperature                                                          |   
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FemAmbientTemperature                | 21                     | Thermistor mounted on sensor board in the FEM package                    |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PasdStatus                           | 22                     | Smartbox system status                                                   |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| LedPattern                           | 23                     | Status of the service and status LEDs                                    |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FemCaseTemperatures                  | 24-25                  | Thermistors mounted on top and bottom of FEM case                        |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FemHeatsinkTemperatures              | 26-27                  | Thermistors mounted on heatsink                                          |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortForcings                         | 36-47                  | Port forcing status for each port ("ON", "OFF", or "NONE")               |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortBreakersTripped                  | 36-47                  | Firmware circuit breaker status for each port (True if trip has occurred)|
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortsDesiredPowerOnline              | 36-47                  | Desired state of each port when FNSC is ONLINE ("OFF, "ON" or "DEFAULT") |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortsDesiredPowerOffline             | 36-47                  | Desired state of each port when FNSC is OFFLINE ("OFF, "ON" or "DEFAULT")|
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortsPowerSensed                     | 36-47                  | Power sensed status for each port (True or False)                        |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PortsCurrentDraw                     | 48-59                  | List of FEM current measurements (mA)                                    |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| InputVoltageThresholds               | 1001-1004              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PowerSupplyOutputVoltageThresholds   | 1005-1008              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PowerSupplyTemperatureThresholds     | 1009-1012              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| PcbTemperatureThresholds             | 1013-1016              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FemAmbientTemperatureThresholds      | 1017-1020              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FemCaseTemperature1Thresholds        | 1021-1024              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FemCaseTemperature2Thresholds        | 1025-1028              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FemHeatsinkTemperature1Thresholds    | 1029-1032              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| FemHeatsinkTemperature2Thresholds    | 1033-1036              | High alarm, high warning, low warning and low alarm threshold values     |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Fem1CurrentTripThreshold             | 1069                   | FEM1 current trip threshold (mA)                                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Fem2CurrentTripThreshold             | 1070                   | FEM2 current trip threshold (mA)                                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Fem3CurrentTripThreshold             | 1071                   | FEM3 current trip threshold (mA)                                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Fem4CurrentTripThreshold             | 1072                   | FEM4 current trip threshold (mA)                                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Fem5CurrentTripThreshold             | 1073                   | FEM5 current trip threshold (mA)                                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Fem6CurrentTripThreshold             | 1074                   | FEM6 current trip threshold (mA)                                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Fem7CurrentTripThreshold             | 1075                   | FEM7 current trip threshold (mA)                                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Fem8CurrentTripThreshold             | 1076                   | FEM8 current trip threshold (mA)                                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Fem9CurrentTripThreshold             | 1077                   | FEM9 current trip threshold (mA)                                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Fem10CurrentTripThreshold            | 1078                   | FEM10 current trip threshold (mA)                                        |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Fem11CurrentTripThreshold            | 1079                   | FEM11 current trip threshold (mA)                                        |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| Fem12CurrentTripThreshold            | 1080                   | FEM12 current trip threshold (mA)                                        |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| WarningFlags                         | 10130                  | List of sensors outside their warning thresholds                         |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+
| AlarmFlags                           | 10132                  | List of sensors outside their alarm thresholds                           |
+--------------------------------------+------------------------+--------------------------------------------------------------------------+

The Smartbox ``PasdStatus`` attribute should be interpreted as follows:

+---------------------------------+--------------------------------------------------+
| *PasdStatus* attribute value    | Meaning                                          |
+=================================+==================================================+
| OK                              | Initialised, system health OK                    |
+---------------------------------+--------------------------------------------------+
| WARNING                         | Initialised, and at least one sensor in WARNING  |
+---------------------------------+--------------------------------------------------+
| ALARM                           | Initialised, and at least one sensor in ALARM    |
+---------------------------------+--------------------------------------------------+
| RECOVERY                        | Initialised, and at least one sensor in RECOVERY |
+---------------------------------+--------------------------------------------------+
| UNINITIALISED                   | Not initialised, regardless of sensor states     |
+---------------------------------+--------------------------------------------------+
| POWERDOWN                       | Local tech initiated power-down sequence         |
+---------------------------------+--------------------------------------------------+

Smartbox commands
-----------------
The Smartbox devices support the following commands:

+------------------------+-------------------------------------+-----------------------------------------------------------------------+
| Command name           | Arguments                           | Description                                                           |
+========================+=====================================+=======================================================================+
| PowerOnPort            | Port number                         | Request to power on the specified FEM port                            |                   
+------------------------+-------------------------------------+-----------------------------------------------------------------------+
| PowerOffPort           | Port number                         | Request to power off the specified FEM port                           |                    
+------------------------+-------------------------------------+-----------------------------------------------------------------------+
| SetPortPowers          | See: `Setting Port Powers`_         | Initialise the Smartbox and request the specified port power statuses |
+------------------------+-------------------------------------+-----------------------------------------------------------------------+                    

Alarm recovery procedure
------------------------
When the Smartbox ``PasdStatus`` attribute indicates an ALARM, WARNING or RECOVERY state, the
``WarningFlags`` and ``AlarmFlags`` attributes can be interrogated to find out which
sensors have gone outside their threshold values. These registers need to be manually
cleared by issuing the ``ResetSmartboxAlarms(<smartbox_number>)`` and
``ResetSmartboxWarnings(<smartbox_number>)`` commands after reading.

Smartboxes automatically transition to the RECOVERY state when the relevant
sensor values return to within their alarm thresholds. To return a Smartbox to an operational
state after such an event, the ``initialiseSmartbox(<smartbox_number>)`` command should
be executed.

---------------------
FNCC
---------------------
The FNCC Tango device reflects the state of the Field Node Communications
Controller. The following read-only attributes are exposed:

+---------------------------------+------------------------+--------------------------------------------------------------------------+
| Tango Attribute name            | Register address(es)   | Register description                                                     |
+=================================+========================+==========================================================================+
| ModbusRegisterMapRevisionNumber | 1                      | Modbus FNCC register map revision number, fixed at firmware compile time |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| PcbRevisionNumber               | 2                      | FNCB revision number, fixed at firmware compile time                     |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| CpuId                           | 3-4                    | Microcontroller device ID                                                |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| ChipId                          | 5-12                   | Microcontroller unique device ID                                         |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| FirmwareVersion                 | 13                     | Firmware revision number, fixed at compile time                          |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| Uptime                          | 14-15                  | Time, in seconds, since FNCC boot                                        |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| SysAddress                      | 16                     | Modbus address                                                           |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| PasdStatus                      | 17                     | Communications status (see below)                                        |
+---------------------------------+------------------------+--------------------------------------------------------------------------+
| FieldNodeNumber                 | 18                     | Field node unique ID (set using rotary switch)                           |
+---------------------------------+------------------------+--------------------------------------------------------------------------+

The FNCC ``PasdStatus`` attribute should be interpreted as follows:

+---------------------------------+-------------------------------------------------+
| *PasdStatus* attribute value    | Meaning                                         |
+=================================+=================================================+
| OK                              | System operating normally, all comms links open |
+---------------------------------+-------------------------------------------------+
| RESET                           | WIZNet converter being reset                    |
+---------------------------------+-------------------------------------------------+
| FRAME_ERROR                     | UART3 framing error                             |
+---------------------------------+-------------------------------------------------+
| MODBUS_STUCK                    | Timer circuit on FNCB tripped                   |
+---------------------------------+-------------------------------------------------+
| FRAME_ERROR_MODBUS_STUCK        | Both framing error and timeout have occurred    |
+---------------------------------+-------------------------------------------------+

After an error has occurred, the status register can be reset by issuing the ``ResetFnccStatus()`` command on the MccsPasdBus.
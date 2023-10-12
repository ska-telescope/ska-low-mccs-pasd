=========
Deploying
=========

As a component of the MCCS subsystem,
ska-low-mccs-pasd would not normally be deployed directly,
except for development purposes.
This guidance is aimed at developers,
and should be read in conjunction with the MCCS subsystem documentation
on deploying the MCCS subsystem as a whole.

``ska-low-mccs-pasd`` uses helmfile to configure helm values files.

---------------------
Deploy using helmfile
---------------------
To deploy ``ska-low-mccs-pasd`` onto a k8s cluster, use the command
``helmfile --environment <environment_name> sync``.
To see what environments are supported,
see the ``environments`` section of ``helmfile.d/helmfile.yaml``.

(Although helmfile supports k8s context switching, this has not yet
been set up. You must manually set your k8s context for the platform
you are targetting, before running the above command.)

To tear down a release that has been deployed by helmfile,
use the command ``helmfile <same arguments> destroy``.
It is important that the arguments to the ``destroy`` command
be the same as those used with the ``sync`` command.
For example, if the release was deployed with ``helmfile --environment gmrt sync``,
then it must be torn down with ``helmfile --environment gmrt destroy``.
If arguments are omitted from the ``helmfile destroy`` command,
the release may not be fully torn down.

--------------------------------
Deploy using the .make submodule
--------------------------------
The ``ska-low-mccs-pasd`` repo includes the ``ska-cicd-makefile`` submodule,
and thus supports the SKA-standard ``make install-chart`` and ``make uninstall-chart`` targets.
When using this approach,
use the ``K8S_HELMFILE_ENV``environment variable to specify the environment.
For example, ``make K8S_HELMFILE_ENV=aavs3 install-chart`` and
``make K8S_HELMFILE_ENV=aavs3 uninstall-chart``.

------------
How it works
------------
The ``environments`` section of ``helmfile.d/helmfile.yaml`` specifies
a sequence of helmfile values files for each environment.
The first file will generally be a specification of the target platform.
This file should only change when the platform itself changes.

For example, the platform specification for AAVS3 specifies an array
with a single station cluster containing a single station.
The specification for that station contains a ``pasd`` key as follows:

.. code-block:: yaml

   pasd:
     fndh:
       gateway:
           host: 10.137.0.129
           port: 502
           timeout: 10.0
       controller:
           modbus_id: 101
       smartboxes:
       "1":
           fndh_port: 1
           modbus_id: 1
       "2":
           fndh_port: 2
           modbus_id: 2
       "3":
           fndh_port: 3
           modbus_id: 3
       "4":
           fndh_port: 4
           modbus_id: 4
       "5":
           fndh_port: 5
           modbus_id: 5
       "6":
           fndh_port: 6
           modbus_id: 6
       "7":
           fndh_port: 7
           modbus_id: 7
       "8":
           fndh_port: 8
           modbus_id: 8
       "9":
           fndh_port: 9
           modbus_id: 9
       "10":
           fndh_port: 10
           modbus_id: 10
       "11":
           fndh_port: 11
           modbus_id: 11
       "12":
           fndh_port: 12
           modbus_id: 12
       "13":
           fndh_port: 13
           modbus_id: 13
       "14":
           fndh_port: 14
           modbus_id: 14
       "15":
           fndh_port: 15
           modbus_id: 15
       "16":
           fndh_port: 16
           modbus_id: 16
       "17":
           fndh_port: 17
           modbus_id: 17
       "18":
           fndh_port: 18
           modbus_id: 18
       "19":
           fndh_port: 19
           modbus_id: 19
       "20":
           fndh_port: 20
           modbus_id: 20
       "21":
           fndh_port: 21
           modbus_id: 21
       "22":
           fndh_port: 22
           modbus_id: 22
       "23":
           fndh_port: 23
           modbus_id: 23
       "24":
           fndh_port: 24
           modbus_id: 24

Subsequent files specify default values and overrides.
There are two keys:

* The ``defaults`` key specifies default values that are
  available to all helmfile templates.
  Currently the only supported default value is ``logging_level_default``.
  For example, to specify that the ``LoggingLevelDefault`` property
  of all Tango devices should be ``DEBUG`` (``5``):

  .. code-block:: yaml

     defaults:
       logging_level_default: 5

* The ``overrides`` key allows to set and override values
  at any place in the platform specification.
  It follows the structure of the platform specification,
  but with values to override or augment that specification.
  For example, to set the ``logging_level_default`` for a single smartbox:

  .. code-block:: yaml

     overrides:
       array:
         station_clusters:
           "p1":
             stations:
               "1":
                 pasd:
                   smartboxes:
                     "10":
                       logging_level_default: 5

  Two special keys are supported:

  * The ``enabled`` key can be applied to any device instance,
    to enable or disable deployment of that device.
    For example, to disable deployment of a smartbox:

    .. code-block:: yaml

     overrides:
       array:
         station_clusters:
           "p1":
             stations:
               "1":
                 pasd:
                   smartboxes:
                     "10":
                       enabled: false

    One can also disable an entire station, and then enable only certain
    devices:

    .. code-block:: yaml

       overrides:
         array:
           station_clusters:
             "p1":
               stations:
                 "1":
                   enabled: false
                   pasd:
                     fndh:
                       enabled: true
                     smartboxes:
                       "1":
                         enabled: true

  * The ``simulated`` key indicates that devices should run against a simulator,
    or should simulate their interactions with hardware.
    It is not possible to simulate the FNDH or individual smartboxes,
    but the PaSD as a whole can be simulated,
    by setting the PaSD communication gateway in simulated mode:

    .. code-block:: yaml

       overrides:
         array:
           station_clusters:
             "p1":
               stations:
                 "1":
                   pasd:
                     fndh:
                       gateway:
                         simulated: true

--------------------------------
Direct deployment of helm charts
--------------------------------
It is possible to deploy helm charts directly.
However note that platform-specific chart configuration is handled by helmfile,
so the helm chart values files are expected to provide
a deterministic, fully-configured specification
of what devices and simulators should be deployed.
For example:

.. code-block:: yaml

   deviceServers:
     fieldstations:
       ci-1:
         low-mccs/fieldstation/ci-1:
           fndh_name: low-mccs/fndh/ci-1
           smartbox_names:
           - low-mccs/smartbox/ci-1-01
           outsideTemperature_root_attribute: low-mccs/fndh/ci-1/outsideTemperature
           logging_level_default: 5
     fndhs:
       ci-1:
         low-mccs/fndh/ci-1:
           pasdbus_name: low-mccs/pasdbus/ci-1
           logging_level_default: 5
           modbusRegisterMapRevisionNumber_root_attribute: low-mccs/pasdbus/ci-1/fndhModbusRegisterMapRevisionNumber
           pcbRevisionNumber_root_attribute: low-mccs/pasdbus/ci-1/fndhPcbRevisionNumber
           cpuId_root_attribute: low-mccs/pasdbus/ci-1/fndhCpuId
           chipId_root_attribute: low-mccs/pasdbus/ci-1/fndhChipId
           firmwareVersion_root_attribute: low-mccs/pasdbus/ci-1/fndhFirmwareVersion
           uptime_root_attribute: low-mccs/pasdbus/ci-1/fndhUptime
           sysAddress_root_attribute: low-mccs/pasdbus/ci-1/fndhSysAddress
           fndhStatus_root_attribute: low-mccs/pasdbus/ci-1/fndhFndhStatus
           ledPattern_root_attribute: low-mccs/pasdbus/ci-1/fndhLedPattern
           psu48vVoltages_root_attribute: low-mccs/pasdbus/ci-1/fndhPsu48vVoltages
           psu48vCurrent_root_attribute: low-mccs/pasdbus/ci-1/fndhPsu48vCurrent
           psu48vTemperatures_root_attribute: low-mccs/pasdbus/ci-1/fndhPsu48vTemperatures
           panelTemperature_root_attribute: low-mccs/pasdbus/ci-1/fndhPanelTemperature
           fncbTemperature_root_attribute: low-mccs/pasdbus/ci-1/fndhFncbTemperature
           fncbHumidity_root_attribute: low-mccs/pasdbus/ci-1/fndhFncbHumidity
           commsGatewayTemperature_root_attribute: low-mccs/pasdbus/ci-1/fndhCommsGatewayTemperature
           powerModuleTemperature_root_attribute: low-mccs/pasdbus/ci-1/fndhPowerModuleTemperature
           outsideTemperature_root_attribute: low-mccs/pasdbus/ci-1/fndhOutsideTemperature
           internalAmbientTemperature_root_attribute: low-mccs/pasdbus/ci-1/fndhInternalAmbientTemperature
           # portForcings_root_attribute: low-mccs/pasdbus/ci-1/fndhPortForcings
           portsDesiredPowerOnline_root_attribute: low-mccs/pasdbus/ci-1/fndhPortsDesiredPowerOnline
           portsDesiredPowerOffline_root_attribute: low-mccs/pasdbus/ci-1/fndhPortsDesiredPowerOffline
           portsPowerSensed_root_attribute: low-mccs/pasdbus/ci-1/fndhPortsPowerSensed
           warningFlags_root_attribute: low-mccs/pasdbus/ci-1/fndhWarningFlags
           alarmFlags_root_attribute: low-mccs/pasdbus/ci-1/fndhAlarmFlags
           psu48vVoltage1Thresholds_root_attribute: low-mccs/pasdbus/ci-1/fndhPsu48vVoltage1Thresholds
           psu48vVoltage2Thresholds_root_attribute: low-mccs/pasdbus/ci-1/fndhPsu48vVoltage2Thresholds
           psu48vCurrentThresholds_root_attribute: low-mccs/pasdbus/ci-1/fndhPsu48vCurrentThresholds
           psu48vTemperature1Thresholds_root_attribute: low-mccs/pasdbus/ci-1/fndhPsu48vTemperature1Thresholds
           psu48vTemperature2Thresholds_root_attribute: low-mccs/pasdbus/ci-1/fndhPsu48vTemperature2Thresholds
           panelTemperatureThresholds_root_attribute: low-mccs/pasdbus/ci-1/fndhPanelTemperatureThresholds
           fncbTemperatureThresholds_root_attribute: low-mccs/pasdbus/ci-1/fndhFncbTemperatureThresholds
           humidityThresholds_root_attribute: low-mccs/pasdbus/ci-1/fndhHumidityThresholds
           outsideTemperatureThresholds_root_attribute: low-mccs/pasdbus/ci-1/fndhOutsideTemperatureThresholds
           commsGatewayTemperatureThresholds_root_attribute: low-mccs/pasdbus/ci-1/fndhCommsGatewayTemperatureThresholds
           powerModuleTemperatureThresholds_root_attribute: low-mccs/pasdbus/ci-1/fndhPowerModuleTemperatureThresholds
           internalAmbientTemperatureThresholds_root_attribute: low-mccs/pasdbus/ci-1/fndhInternalAmbientTemperatureThresholds
     smartboxes:
       ci-1-01:
         low-mccs/smartbox/ci-1-01:
           smartbox_number: 1
           fndh_name: low-mccs/fndh/ci-1
           fndh_port: 1
           pasdbus_name: low-mccs/pasdbus/ci-1
           logging_level_default: 5
           alarmFlags_root_attribute: low-mccs/pasdbus/aavs3/smartbox1alarmFlags
           chipId_root_attribute: low-mccs/pasdbus/aavs3/smartbox1chipId
           cpuId_root_attribute: low-mccs/pasdbus/aavs3/smartbox1cpuId
           fem1CurrentTripThreshold_root_attribute: low-mccs/pasdbus/aavs3/smartbox1fem1CurrentTripThreshold
           fem2CurrentTripThreshold_root_attribute: low-mccs/pasdbus/aavs3/smartbox1fem2CurrentTripThreshold
           fem3CurrentTripThreshold_root_attribute: low-mccs/pasdbus/aavs3/smartbox1fem3CurrentTripThreshold
           fem4CurrentTripThreshold_root_attribute: low-mccs/pasdbus/aavs3/smartbox1fem4CurrentTripThreshold
           fem5CurrentTripThreshold_root_attribute: low-mccs/pasdbus/aavs3/smartbox1fem5CurrentTripThreshold
           fem6CurrentTripThreshold_root_attribute: low-mccs/pasdbus/aavs3/smartbox1fem6CurrentTripThreshold
           fem7CurrentTripThreshold_root_attribute: low-mccs/pasdbus/aavs3/smartbox1fem7CurrentTripThreshold
           fem8CurrentTripThreshold_root_attribute: low-mccs/pasdbus/aavs3/smartbox1fem8CurrentTripThreshold
           fem9CurrentTripThreshold_root_attribute: low-mccs/pasdbus/aavs3/smartbox1fem9CurrentTripThreshold
           fem10CurrentTripThreshold_root_attribute: low-mccs/pasdbus/aavs3/smartbox1fem10CurrentTripThreshold
           fem11CurrentTripThreshold_root_attribute: low-mccs/pasdbus/aavs3/smartbox1fem11CurrentTripThreshold
           fem12CurrentTripThreshold_root_attribute: low-mccs/pasdbus/aavs3/smartbox1fem12CurrentTripThreshold
           femAmbientTemperature_root_attribute: low-mccs/pasdbus/aavs3/smartbox1femAmbientTemperature
           femAmbientTemperatureThresholds_root_attribute: low-mccs/pasdbus/aavs3/smartbox1femAmbientTemperatureThresholds
           femCaseTemperature1Thresholds_root_attribute: low-mccs/pasdbus/aavs3/smartbox1femCaseTemperature1Thresholds
           femCaseTemperature2Thresholds_root_attribute: low-mccs/pasdbus/aavs3/smartbox1femCaseTemperature2Thresholds
           femCaseTemperatures_root_attribute: low-mccs/pasdbus/aavs3/smartbox1femCaseTemperatures
           femHeatsinkTemperature1Thresholds_root_attribute: low-mccs/pasdbus/aavs3/smartbox1femHeatsinkTemperature1Thresholds
           femHeatsinkTemperature2Thresholds_root_attribute: low-mccs/pasdbus/aavs3/smartbox1femHeatsinkTemperature2Thresholds
           femHeatsinkTemperatures_root_attribute: low-mccs/pasdbus/aavs3/smartbox1femHeatsinkTemperatures
           firmwareVersion_root_attribute: low-mccs/pasdbus/aavs3/smartbox1firmwareVersion
           inputVoltage_root_attribute: low-mccs/pasdbus/aavs3/smartbox1inputVoltage
           inputVoltageThresholds_root_attribute: low-mccs/pasdbus/aavs3/smartbox1inputVoltageThresholds
           ledPattern_root_attribute: low-mccs/pasdbus/aavs3/smartbox1ledPattern
           modbusRegisterMapRevisionNumber_root_attribute: low-mccs/pasdbus/aavs3/smartbox1modbusRegisterMapRevisionNumber
           pcbRevisionNumber_root_attribute: low-mccs/pasdbus/aavs3/smartbox1pcbRevisionNumber
           pcbTemperature_root_attribute: low-mccs/pasdbus/aavs3/smartbox1pcbTemperature
           pcbTemperatureThresholds_root_attribute: low-mccs/pasdbus/aavs3/smartbox1pcbTemperatureThresholds
           portBreakersTripped_root_attribute: low-mccs/pasdbus/aavs3/smartbox1portBreakersTripped
           # portForcings_root_attribute: low-mccs/pasdbus/aavs3/smartbox1portForcings
           portsCurrentDraw_root_attribute: low-mccs/pasdbus/aavs3/smartbox1portsCurrentDraw
           portsDesiredPowerOffline_root_attribute: low-mccs/pasdbus/aavs3/smartbox1portsDesiredPowerOffline
           portsDesiredPowerOnline_root_attribute: low-mccs/pasdbus/aavs3/smartbox1portsDesiredPowerOnline
           portsPowerSensed_root_attribute: low-mccs/pasdbus/aavs3/smartbox1portsPowerSensed
           powerSupplyOutputVoltage_root_attribute: low-mccs/pasdbus/aavs3/smartbox1powerSupplyOutputVoltage
           powerSupplyOutputVoltageThresholds_root_attribute: low-mccs/pasdbus/aavs3/smartbox1powerSupplyOutputVoltageThresholds
           powerSupplyTemperature_root_attribute: low-mccs/pasdbus/aavs3/smartbox1powerSupplyTemperature
           powerSupplyTemperatureThresholds_root_attribute: low-mccs/pasdbus/aavs3/smartbox1powerSupplyTemperatureThresholds
           smartboxStatus_root_attribute: low-mccs/pasdbus/aavs3/smartbox1Status
           sysAddress_root_attribute: low-mccs/pasdbus/aavs3/smartbox1sysAddress
           uptime_root_attribute: low-mccs/pasdbus/aavs3/smartbox1uptime
           warningFlags_root_attribute: low-mccs/pasdbus/aavs3/smartbox1warningFlags

     pasdbuses:
       ci-1:
         low-mccs/pasdbus/ci-1:
           host: pasd-simulator-ci-1
           port: 502
           timeout: 10
           logging_level_default: 5
   simulators:
     pasdbuses:
       ci-1:
         host: pasd-simulator-ci-1
         port: 502
         config:
           pasd:
             smartboxes:
               "1":
                 fndh_port: 1
           antennas:
             "100":
               smartbox: "1"
               smartbox_port: 5
             "113":
               smartbox: "1"
               smartbox_port: 7
             "121":
               smartbox: "1"
               smartbox_port: 4
             "134":
               smartbox: "1"
               smartbox_port: 6
             "155":
               smartbox: "1"
               smartbox_port: 3
             "168":
               smartbox: "1"
               smartbox_port: 8
             "189":
               smartbox: "1"
               smartbox_port: 2
             "202":
               smartbox: "1"
               smartbox_port: 9
             "223":
               smartbox: "1"
               smartbox_port: 10
             "244":
               smartbox: "1"
               smartbox_port: 1

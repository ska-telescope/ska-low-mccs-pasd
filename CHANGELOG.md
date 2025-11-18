# Version History

## Unreleased

## 3.5.1

* [LOW-1853] Provide attribute thresholds in ska-tango-devices as `classProperties` rather than `deviceDefaults`, so that they are applied in the Tango DB once rather than being applied individually to each device.
* [THORN-262] Add timeout to pytest configuration. This should be set to slightly less than the pipeline timeout so that test reports are generated before the job is killed.

## 3.5.0

* [SKB-455] Add new optional device property 'SmartboxIDs' to pasdBus. When set,
  only smartboxes which are powered on are polled.
* [THORN-253] Populate attribute alarm configuration from tmdata.
* [THORN-268] MccsSmartbox healthstate is now an aggregate of attribute alarms.
  The attributes used in health are:
  * InputVoltage
  * PowerSupplyOutputVoltage
  * PowerSupplyTemperature
  * PcbTemperature
  * FemAmbientTemperature
  * FemCaseTemperature1
  * FemCaseTemperature2
  * FemHeatsinkTemperature1
  * FemHeatsinkTemperature2
* [THORN-268] MccsSmartbox.numberOfPortBreakersTripped added.
* [THORN-268] MccsFndh healthstate is now an aggregate of attribute alarms.
  The attributes used in health are:
  * Psu48vVoltage1
  *  Psu48vVoltage2
  *  Psu48vCurrent
  *  Psu48vTemperature1
  *  Psu48vTemperature2
  *  PanelTemperature
  *  FncbTemperature
  *  FncbHumidity
  *  CommsGatewayTemperature
  *  PowerModuleTemperature
  *  OutsideTemperature
  *  InternalAmbientTemperature
* [THORN-268] MccsFndh.numberOfStuckOnSmartboxPorts, MccsFndh.numberOfStuckOffSmartboxPorts added.

## 3.4.2

* [THORN-305] Prevent unhandled exception when handling errors from write requests.
* [SKB-455] Re-create the Modbus client after a failed poll to workaround the connection issues.

## 3.4.1

* [THORN-284] Only power on/off ports with smartboxes attached.

* [LOW-1745] Bump ska-tango-devices to 0.10.0, with support for suppressing the deployment of check-dependencies initContainers that wait for databaseDS, when deploying to a persistent platform.

## 3.4.0

* [SKB-1021] Add device property SBInputVoltageThresholds to override firmware values.

## 3.3.0

* [THORN-248] Update ska-low-mccs-common dependency to use refactored MccsCommandProxy.

## 3.2.1

* [LOW-1593] Update to latest ska-tango-devices, thus removing dependency on bitnami image.
* [THORN-232] Update README file.

## 3.2.0

* [THORN-142] Incorporate status registers and FEM breaker trips into healthState.

## 3.1.3

* [THORN-220] Update dependencies, add cleanup methods for component managers and proxies.

## 3.1.2

* [THORN-225] Fix health rediscovery after adminMode cycle.

## 3.1.1

* [THORN-212] Add tests for fieldStation health aggregation and reconfigure.
* [THORN-71] Update PASD to include command schemas in docs

## 3.1.0
* [THORN-212] Allow fieldStation healthThresholds to be reconfigurable.

## 3.0.1
* [SKB-876] Fix strategy for re-requesting 'read once' attributes if the h/w is unavailable at startup.

## 3.0.0

* [THORN-129] Make pytest pipeline parallel
* [SKB-455] Add delay before reconnecting after failed poll.
* [LOW-1296] Breaking changes to helm chart values schema.
  The `ska-low-mccs-pasd` helm chart now uses `ska-tango-devices`
  to configure and deploy its Tango devices.
  For details, see the "Direct deployment of helm charts" section of the
  "Deploying" page in the documentation.

## 2.0.0

* [THORN-136] Refactor port configuration to be deploy-time instead of run-time. The PaSD configuration server has been removed, and has instead been replaced with 4 device properties to be populated at deployment: MccsFNDH.PortsWithSmartbox, MccsSmartbox.FndhPort, MccsSmartbox.PortsWithAntennas, MccsSmartbox.AntennaNames.
* [THORN-139] Add Fieldstation docs.

## 1.1.1

* Update ska-tango-base 1.3.1 -> 1.3.2 (https://gitlab.com/ska-telescope/ska-tango-base/-/releases)
* [THORN-121] Add deploy stage to pipeline.
* [THORN-116] Prune log messages.

## 1.1.0

* [THORN-86] FieldStation now uses the CommunicationManager from ska-low-mccs-common to manage it's communication status, this should flush out issues with rapid changes of adminmode.
* [THORN-85] Update devices to serialise their events through the EventSerialiser. This should have no operational
changes, but an attribute EventHistory is now available on all devices to debug which events this device received,
where they came from, the order they came in, and what callbacks were executed with those events. It is a json-ified list of lists.

## 1.0.0

* [THORN-17] 1.0.0 release - all MCCS repos

## 0.17.0

* [THORN-20] Update to use MccsBaseDevice for mode inheritance.

## 0.16.1

* [THORN-61] Update pasd simulator to cope with no antennas in deployment.

## 0.16.0

* [MCCS-2330] Update pytango to 10.0.0
* [SKB-713]: Remove not implemented health monitoring points from rollup.

## 0.15.2

* [SKB-713]: Fix attribute useNewHealthRules.
* [THORN-48]: Update deployment to use local telmodel.

## 0.15.1

* [THORN-55]: Fix python package build bug that prevented publication of
  python wheel for v0.15.0

## 0.15.0

* [THORN-51]: Helm chart support for multi-device-class device servers

## 0.14.0

* [THORN-1]: Multi-class device server endpoint
* [WOM-486]: Add FemCurrentTripThreshold device property
* [THORN-37]: Update DeviceComponentManager to use DevSource.DEV
* [MCCS-2245]: Correct docs formatting

## 0.13.0

* [LOW-1131]: Expose Field station as LoadBalancer

## 0.12.1

* [MCCS-2324]: MccsSmartbox power commands can get stuck in infinite loop
* [MCCS-2245]: Add configuration to FNDH

## 0.12.0

* [MCCS-2309]: allow setting arbitrary Tango properties via Helm chart values
* [MCCS-2140]: implement STANDBY mode in FieldStation, and improve related health state handling

## 0.11.1

* [SKB-480]: Fix FNDH stuck in UNKNOWN
* [MCCS-2140]: Add MccsSmartbox.portMask
* [WOM-497]: Update charts to fix dependencies
* [WOM-420]: Fix alarm/warning reset functionality
* [WOM-426]: Fix minor chart bug
* [SKB-455]: Automatically reset the connection when a poll fails

## 0.11.0

* [MCCS-2141]: Update ska-tango-base to 1.0.0
* [MCCS-2115]: Update field station to use new antenna mappings

## 0.10.1

* [LOW-952]: Point at ska-low-tmdata for AA0.5 telmodel data
* [MCCS-2216]: Support nulls in values schemas
* [WOM-370]: Faster, more reliable tests

## 0.10.0

* [WOM-147]: Add metadata to the Tango attributes
* [WOM-144]: Synchronize Tango alarm config with threshold values
* [WOM-361]: Change FEM current trip threshold attributes to an array
* [WOM-384]: Fix misleading messages
* [WOM-217]: Use YAML to define the mapping between Tango attributes and device registers
* [WOM-374]: Enforce init order of device servers
* [WOM-385]: Remove redundant archive events from pasdbus device

## 0.9.0

* [MCCS-2175]: Add HealthState to FieldStation
* [MCCS-2153]: Add MCCS schemas to TelModel
* [WOM-381]: Always push change events from pasdbus
* [MCCS-2029]: Pull TMData to pasd
* [MCCS-2107]: Remove deprecated environments
* [WOM-276]: Only poll deployed smartboxes
* [WOM-331]: Remove resetFndhPortBreakers cmd

## 0.8.0

* [WOM-244]: Support for reading the FNCC registers
* [WOM-249,WOM-317]: User documentation
* [WOM-112]: Mark attributes as invalid when a device doesn't respond
* [MCCS-1978]: infra-managed Low ITF credentials
* [MCCS-1963]: Change backoff to exponential
* [MCCS-1995]: Chart values schema
* [MCCS-2070]: String keys
* [MCCS-2083]: use HTTP for PaSD config server
* [MCCS-2091]: refactor configuration server
* [MCCS-2093]: one PaSD config server
* [MCCS-2090]: Remove placeholder code, causing incorrect health reporting
* [MCCS-2094]: remove unused access
* [WOM-326]: Delays in executing commands
* [WOM-329]: Change in attribute quality does not push change event
* [WOM-318]: Make threshold attributes writeable
* [MCCS-1968]: Fix manual config commands
* [MCCS-2081]: Fix empty port power change event bug
* [MCCS-2060]: Add eda_config.yaml with all pasd attributes

## 0.7.0

* [WOM-183] Update error log message for modbus exception responses
* [MCCS-1957] Support namespace override
* [WOM-240] Remove default logger and ensure correct object used
* [WOM-184] Refactor functional and smartbox integration tests
* [WOM-165] Add command to set sensors' low-pass filter cutoff frequency
* [WOM-149] Add support for setting multiple port powers in a single modbus command
* [WOM-246] Indicate modbus address in all error messages and refactor request exceptions
* [MCCS-1966] use infra-issued credentials for AAVS3
* [MCCS-1973] Update MccsPasdBUs to update SimulationConfig on device creation
* [MCCS-1963] Add backoff retry for connection to configuration server

## 0.6.0

* [MCCS-1751] FieldStation Dashboard
* [MCCS-1745] - Add FieldStation antenna mapping
* [WOM-119] Improve MODBUS API test coverage
* [WOM-159] Request to re-read the static info and thresholds
* [MCCS-1745] Smartbox Mapping
* [WOM-167] Fix simulator server and uptime conversion
* [MCCS-1861] Parameterise MccsSmartbox property FieldStationName
* [MCCS-1859] helm values
* [LOW-637] use correct dev image in dev chart builds
* [MCCS-1939] AAVS3 staging on Low ITF
* [MCCS-1944] Check in Chart.lock
* [MCCS-1957] Support namespace override
* [MCCS-1871] Allow configuarble PaSDBus Polling rates.
* [WOM-161] Update port register parsing
* [WOM-110] Update attributes immediately after writing
* [MCCS-1848] - Convert OutsideTemperature to attribute.
* [MCCS-1857] refactor helmfile templates
* [MCCS-1813] MccsSmartbox is pushing change events with malformed attribute names
* [MCCS-1864] Update FieldStation attribute to optional.
* [MCCS-1868] Update FieldStation to derive state from antenna states.
* [MCCS-1937] Update pasd-configuration-server to deploy when interfacing with hardware.
* [MCCS-1938] Prevent MccsSmartbox from turning on ports on other smartboxes.
* [MCCS-1870] Antenna power command bug
* [MCCS-1849] Fix incorrect exception handle type in fieldstation.
* [MCCS-1869] Fix FieldStation On command Bug.
* [MCCS-1939] more tweaks
* [MCCS-1837] Speed up python-test
* [MCCS-1855] Update CODEOWNERS
* [WOM-157] Partially revert merge and update simulator
* [MCCS-1947] Support platform spec without pasd


## 0.5.0

* [WOM-157] Update set led pattern commands
* [WOM-107] Implement FNDH port state registers PWRSENSE & POWER
* [MCCS-1846] Support disabling PaSD
* [WOM-111] Handle bad responses more robustly
* [WOM-162] Fix bug in SmartBoxComponentManager and its PasdBusProxy
* [MCCS-1745] : Add antenna powers attribute to FieldStation
* [MCCS-1753] Modify PaSD Bus Simulator to use Modbus API rather than JSON API
* [MCCS-1755] Fieldstation ON/OFF
* [WOM-156] Make timeout setting in values.yaml take effect
* [WOM-140] Smarboxes depend on attached FNDH ports in functional and integration tests
* [WOM-150] Add warning/alarm flags to FNDH and SMART box polling loop
* [MCCS-1814] Simplify smartbox
* [MCCS-1801] Poll management
* [MCCS-1807] Filter by device
* [WOM-108] - Alarm thresholds
* [MCCS-1800] set port powers
* [MCCS-1794] defer connecting
* [MCCS-1788] Refactor test harness
* [MCCS-1787] TurnAllPortsOn
* [WOM-113] Removed ports_connected attribute from FNDH/smartbox.
* [MCCS-1784] field station configure


## 0.4.0

* [MCCS-1769] Update to pytango 9.4.2
* [MCCS-1697] Support using platform-service tangodb instead of always deploying our own.
* [MCCS-1694] Fix bug in use of "enabled" key to control what gets deployed

## 0.3.0

* [MCCS-1685] remove ska-tango-base
* [MCCS-1680] platform dependent configuration
* [WOM-103] [WOM-104] Smartbox simulator instances depend on FNDH ports' power state.
  Uptime tracked from instantiation.
* [MCCS-1679] external PaSD configuration
* [WOM-59] [WOM-46] FNDH/smartbox attributes and simulator updates
* Implementation of PaSD commands
* [MCCS-1646] Remove xfail from fieldStation device.
* [MCCS-1636] Use ska-ser-sphinx-theme
* [MCCS-1633] Update /docs/src/_static/img/ in MCCS repos
* [MCCS-1482] Implement solution to "attribute requested before first Poll" error.
* [WOM-43] Implement read_attributes part of Modbus client API
* [MCCS-1619] MccsFNDH does not subscribe to state or adminMode changes on MccsPaSDBus
* [MCCS-1622] Transport logging
* [MCCS-1503] fndh functional test
* [MCCS-1618] Update proxy callbacks in MccsSmartbox
* [MCCS-1569] Add FieldStation device with forwarded attribute outsideTemperature
* [MCCS-1613] Add version logging to device init
* [MCCS-1356] Update state changed callback to use kwargs
* [WOM-30] skeleton Modbus API

## 0.2.1

* MCCS-1526 - Fix broken docs.
* MCCS-1500 - Fix broken umbrella chart.
* MCCS-764  - Fix some minor bugs in Smartbox/FNDH.
* MCCS-1528 - Fix charts to not publish umbrella.

## 0.2.0

* MCCS-1345 - Update ska-low-mccs-pasd to use ska-tango-testing
* MCCS-1445 - Modify configuration file path, update pasdbus entry point
* MCCS-1403 - Create standalone PaSD simulator
* MCCS-1404 - Helm chart update for PaSD simulator
* MCCS-1454 - Add log statements to the PASD simulator
* MCCS-1470 - Rewrite PaSD simulator and driver to address one PaSD device at a time.
* MCCS-1461 - Create Xray tickets and dummy implementation for PASD test set
* MCCS-1475 - Reimplement PaSD bus component manager as a poller.
* MCCS-768  - Implement Smartbox device
* MCCS-764  - Implement FNDH device

## 0.1.0

* MCCS-1209 - Use ska_tango_testing.mock
* MCCS-1196 - enable k8s-test
* MCCS-1111 - Update license with copyright
* MCCS-1156 - Fix linting & static type checking in ska-low-mccs-pasd

Initial release

* MCCS-1151 - initial creation

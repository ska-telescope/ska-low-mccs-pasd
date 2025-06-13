==================================
MccsFNDH UpdateHealthParams schema
==================================

Schema for MccsFndh's UpdateHealthParams

**********
Properties
**********

* **failed_percent_uncontrolled_smartbox** (integer): Percentage of Smartboxes configured without PDOC control should be considered as FAILED. Minimum: 0. Maximum: 100.

* **degraded_percent_uncontrolled_smartbox** (integer): Percentage of Smartboxes configured without PDOC control should be considered as DEGRADED. Minimum: 0. Maximum: 100.

* **psu48vvoltage1** (array): See https://developer.skao.int/projects/ska-low-mccs-pasd/en/latest/user/fndh.html. Length must be equal to 4.

  * **Items** (number): Minimum: 0.

* **psu48vcurrent** (array): See https://developer.skao.int/projects/ska-low-mccs-pasd/en/latest/user/fndh.html. Length must be equal to 4.

  * **Items** (number)

* **psu48vtemperature1** (array): See https://developer.skao.int/projects/ska-low-mccs-pasd/en/latest/user/fndh.html. Length must be equal to 4.

  * **Items** (number)

* **psu48vtemperature2** (array): See https://developer.skao.int/projects/ska-low-mccs-pasd/en/latest/user/fndh.html. Length must be equal to 4.

  * **Items** (number)

* **fncbtemperature** (array): See https://developer.skao.int/projects/ska-low-mccs-pasd/en/latest/user/fndh.html. Length must be equal to 4.

  * **Items** (number)

* **fncbhumidity** (array): See https://developer.skao.int/projects/ska-low-mccs-pasd/en/latest/user/fndh.html. Length must be equal to 4.

  * **Items** (integer)

* **commsgatewaytemperature** (array): See https://developer.skao.int/projects/ska-low-mccs-pasd/en/latest/user/fndh.html. Length must be equal to 4.

  * **Items** (number)

* **powermoduletemperature** (array): See https://developer.skao.int/projects/ska-low-mccs-pasd/en/latest/user/fndh.html. Length must be equal to 4.

  * **Items** (number)

* **outsidetemperature** (array): See https://developer.skao.int/projects/ska-low-mccs-pasd/en/latest/user/fndh.html. Length must be equal to 4.

  * **Items** (number)

* **internalambienttemperature** (array): See https://developer.skao.int/projects/ska-low-mccs-pasd/en/latest/user/fndh.html. Length must be equal to 4.

  * **Items** (number)


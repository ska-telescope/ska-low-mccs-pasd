========================================
MccsPasdBus SetSmartboxPortPowers schema
========================================

Schema for MccsPasdBus's SetSmartboxPortPowers command

**********
Properties
**********

* **smartbox_number** (integer): Number of the smartbox being addressed. Minimum: 1. Maximum: 24.

* **port_powers** (array): The desired power of each port. Length must be equal to 12.

  * **Items** (['boolean', 'null'])

* **stay_on_when_offline** (boolean): Whether to stay on when M&C is offline.


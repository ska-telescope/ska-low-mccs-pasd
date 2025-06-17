====================================
MccsPasdBus SetFndhPortPowers schema
====================================

Schema for MccsPasdBus's SetFndhPortPowers command

**********
Properties
**********

* **port_powers** (array): The desired power of each port. Length must be equal to 28.

  * **Items** (['boolean', 'null'])

* **stay_on_when_offline** (boolean): Whether to stay on when M&C is offline.


============================================
MccsPasdBus SetSmartboxLowPassFilters schema
============================================

Schema for MccsPasdBus's SetSmartboxLowPassFilters command

**********
Properties
**********

* **smartbox_number** (integer): Number of the smartbox being addressed. Minimum: 1. Maximum: 24.

* **cutoff** (number): Cut-off frequency to set for the low-pass filtering. Minimum: 0.1. Maximum: 1000.0.

* **extra_sensors** (boolean): Write the filter constant to the extra sensors' registers after the LED status register.


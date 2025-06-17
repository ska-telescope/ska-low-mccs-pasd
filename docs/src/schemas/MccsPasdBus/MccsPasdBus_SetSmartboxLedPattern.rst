========================================
MccsPasdBus SetSmartboxLedPattern schema
========================================

Schema for MccsPasdBus's SetSmartboxLedPattern command

**********
Properties
**********

* **smartbox_number** (integer): Number of the smartbox being addressed. Minimum: 1. Maximum: 24.

* **pattern** (string): Name of the service LED pattern. Must be one of: ["OFF", "ON", "VFAST", "FAST", "SLOW", "VSLOW"].


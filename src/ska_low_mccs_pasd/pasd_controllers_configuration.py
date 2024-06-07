# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Module provides utilities to read and validate PaSD controllers configuration."""
from pathlib import Path
from pprint import pprint  # TODO

import yaml
from cerberus import Validator  # type: ignore[import-untyped]

# Define the schemas
REGISTER_SCHEMA = {
    "type": "list",
    "required": True,
    "schema": {
        "type": "dict",
        "schema": {
            "name": {
                "type": "string",
                "required": True,
                "regex": "^[a-z0-9]+(?:_[a-z12]+)*$",
            },
            "address": {
                "type": "integer",
                "required": True,
                "min": 0,
                "max": 65535,
            },
            "data_type": {
                "type": "string",
                "required": True,
                "allowed": [
                    "int",
                    "float",
                    "str",
                    "bool",
                    "DesiredPowerEnum",
                ],
            },
            "size": {
                "type": "integer",
                "default": 1,
                "min": 1,
                "max": 253,
            },
            "tango_dim_x": {
                "type": "integer",
                "default": 1,
                "min": 1,
                "max": 253,
            },
            "conversion_function": {
                "type": "string",
                "default": "default_conversion",
                "regex": "^[a-z]+(?:_[a-z,0-9]+)*$",
            },
            "writable": {"type": "boolean", "default": False},
            "class": {
                "type": "string",
                "default": "PasdBusAttribute",
                "allowed": [
                    "PasdBusAttribute",
                    "PasdBusPortAttribute",
                ],
            },
            "tango_attr_name": {
                "type": "string",
                "regex": "^([A-Z][a-z0-9]+)+$",
            },
            "desired_info": {
                "type": "string",
                "allowed": [
                    "DSON",
                    "DSOFF",
                    "TO",
                    "PWRSENSE_BREAKER",
                    "POWER",
                ],
            },
            "default_thresholds": {
                "type": "dict",
                "schema": {
                    "high_alarm": {"type": "integer"},
                    "high_warning": {"type": "integer"},
                    "low_warning": {"type": "integer"},
                    "low_alarm": {"type": "integer"},
                },
            },
        },
    },
}

CONTROLLER_SCHEMA = {
    "type": "dict",
    "schema": {
        "full_name": {"type": "string"},
        "prefix": {
            "type": "string",
            "required": True,
            "allowed": ["fncc", "fndh", "smartbox"],
        },
        "modbus_address": {"type": "integer", "min": 0, "max": 255},
        "number_of_ports": {"type": "integer"},
        "registers": REGISTER_SCHEMA,
    },
}

CONFIGURATION_SCHEMA = {
    "PaSD_controllers": {
        "type": "dict",
        "schema": {
            "base_firmware": {
                "type": "dict",
                "required": True,
                "schema": {
                    "FNCC": {
                        "type": "dict",
                        "required": True,
                        "schema": CONTROLLER_SCHEMA["schema"],
                    },
                    "FNPC": {
                        "type": "dict",
                        "required": True,
                        "schema": CONTROLLER_SCHEMA["schema"],
                    },
                    "FNSC": {
                        "type": "dict",
                        "required": True,
                        "schema": CONTROLLER_SCHEMA["schema"],
                    },
                },
            },
            "firmware_revisions": {
                "type": "dict",
                "required": False,
                "keysrules": {"type": "string", "regex": "v([2-9]\\b|[1-9][0-9]+)"},
                "valuesrules": {
                    "type": "dict",
                    "keysrules": {
                        "type": "string",
                        "allowed": ["FNCC", "FNPC", "FNSC"],
                    },
                    "valuesrules": {
                        "type": "dict",
                        "schema": {"registers": REGISTER_SCHEMA},
                    },
                },
            },
        },
    }
}


class PasdControllersConfig:
    """Read and validate PaSD controller configuration from YAML."""

    @staticmethod
    def _load_configuration_yaml() -> dict:
        """
        Load and process the configuration YAML file.

        :returns: unvalidated configuration dictionary.
        """
        file_path = "ska_low_mccs_pasd/pasd_controllers_configuration.yaml"
        src_dir = Path(__file__).resolve()
        while not (src_dir / "ska_low_mccs_pasd").exists():
            src_dir = src_dir.parent
        with open(src_dir / file_path, "r", encoding="UTF-8") as file:
            config: dict = yaml.safe_load(file)

        def _snake_to_pascal_case(snake_string: str) -> str:
            return "".join(word.capitalize() for word in snake_string.split("_"))

        for name in config["PaSD_controllers"]["base_firmware"]:
            controller = config["PaSD_controllers"]["base_firmware"][name]
            if isinstance(controller["registers"][0], list):
                controller["registers"] = [
                    *controller["registers"][0],
                    *controller["registers"][1:],
                ]
            for regs in controller["registers"]:
                if "tango_attr_name" not in regs:
                    regs["tango_attr_name"] = _snake_to_pascal_case(regs["name"])

        del config["common_registers"]
        return config

    @staticmethod
    def _validate_configuration(config: dict) -> dict:
        """
        Validate and apply defaults to the given PaSD controller's configuration.

        :param config: dictionary of PaSD controller to validate.
        :return: validated configuration dictionary.
        :raises ValueError: if there are validation errors.
        """
        # Create a Validator instance
        v = Validator(CONFIGURATION_SCHEMA)
        # Validate the data and apply defaults, else raise an exception
        if v.validate(config):
            return v.normalized(config)["PaSD_controllers"]
        raise ValueError(f"PaSD controllers' config validation errors: {v.errors}")

    @staticmethod
    def get_all() -> dict:
        """
        Get all PaSD controllers' configuration.

        :return: validated configuration dictionary.
        """
        config = PasdControllersConfig._load_configuration_yaml()
        validated = PasdControllersConfig._validate_configuration(config)
        return validated["base_firmware"]

    @staticmethod
    def get_fncc() -> dict:
        """
        Get the Field Node Communications Controller configuration.

        :return: validated configuration dictionary.
        """
        config = PasdControllersConfig._load_configuration_yaml()
        validated = PasdControllersConfig._validate_configuration(config)
        return validated["base_firmware"]["FNCC"]

    @staticmethod
    def get_fndh() -> dict:
        """
        Get the Field Node Peripheral Controller (or FNDH) configuration.

        :return: validated configuration dictionary.
        """
        config = PasdControllersConfig._load_configuration_yaml()
        validated = PasdControllersConfig._validate_configuration(config)
        return validated["base_firmware"]["FNPC"]

    @staticmethod
    def get_smartbox() -> dict:
        """
        Get the Field Node SMART Box Controller configuration.

        :return: validated configuration dictionary.
        """
        config = PasdControllersConfig._load_configuration_yaml()
        validated = PasdControllersConfig._validate_configuration(config)
        return validated["base_firmware"]["FNSC"]

    @staticmethod
    def get_firmware_revisions() -> dict | None:
        """
        Get all PaSD controllers' firmware revisions changes.

        :return: validated configuration dictionary.
        """
        config = PasdControllersConfig._load_configuration_yaml()
        validated = PasdControllersConfig._validate_configuration(config)
        return validated.get("firmware_revisions")


if __name__ == "__main__":
    print("Validated configurations with defaults applied:")
    pprint(PasdControllersConfig.get_all())
    print("Validated firmware revisions with defaults applied:")
    pprint(PasdControllersConfig.get_firmware_revisions())

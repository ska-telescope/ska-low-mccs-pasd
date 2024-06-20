# -*- coding: utf-8 -*-
#
# This file is part of the SKA Low MCCS project
#
#
# Distributed under the terms of the BSD 3-clause new license.
# See LICENSE for more info.
"""Module provides utilities to read and validate PaSD controllers configuration."""
from pathlib import Path
from pprint import pprint
from typing import Final, TypedDict

import yaml
from cerberus import Validator  # type: ignore[import-untyped]


class RegisterDict(TypedDict, total=False):
    """TypedDict that must match REGISTER_SCHEMA."""

    address: int
    data_type: str
    size: int
    tango_dim_x: int
    conversion_function: str
    writable: bool
    modbus_class: str
    tango_attr_name: str
    desired_info: str
    default_thresholds: dict[str, int]


REGISTER_SCHEMA: Final = {
    "type": "dict",
    "required": True,
    "keysrules": {"type": "string", "regex": "^[a-z0-9]+(?:_[a-z12]+)*$"},
    "valuesrules": {
        "type": "dict",
        "schema": {
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
            "static": {"type": "boolean"},
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
            "modbus_class": {
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
            "default_value": {"type": "integer"},
            "default_thresholds": {
                "type": "dict",
                "schema": {
                    "high_alarm": {"type": "integer", "required": True},
                    "high_warning": {"type": "integer", "required": True},
                    "low_warning": {"type": "integer", "required": True},
                    "low_alarm": {"type": "integer", "required": True},
                },
            },
        },
    },
}


class ControllerDict(TypedDict, total=False):
    """TypedDict that must match CONTROLLER_SCHEMA."""

    full_name: str
    prefix: str
    modbus_address: int
    pasd_number: int
    number_of_ports: int
    registers: dict[str, RegisterDict]


CONTROLLER_SCHEMA: Final = {
    "type": "dict",
    "schema": {
        "full_name": {"type": "string"},
        "prefix": {
            "type": "string",
            "required": True,
            "allowed": ["fncc", "fndh", "smartbox"],
        },
        "modbus_address": {"type": "integer", "min": 0, "max": 255},
        "pasd_number": {"type": "integer", "min": 0, "max": 255},
        "number_of_ports": {"type": "integer"},
        "registers": REGISTER_SCHEMA,
    },
}

CONFIGURATION_SCHEMA: Final = {
    "PaSD_controllers": {
        "type": "dict",
        "schema": {
            "base_register_maps": {
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
            "register_map_revisions": {
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

    AllCtrllrsDict = dict[str, ControllerDict]
    RegMapRevsDict = dict[str, AllCtrllrsDict]
    LoadedYaml = dict[str, RegMapRevsDict]

    @staticmethod
    def _load_configuration_yaml() -> LoadedYaml:
        """
        Load and process the configuration YAML file.

        :returns: unvalidated configuration dictionary.
        """
        file_path = "ska_low_mccs_pasd/pasd_controllers_configuration.yaml"
        src_dir = Path(__file__).resolve()
        while not (src_dir / "ska_low_mccs_pasd").exists():
            src_dir = src_dir.parent
        with open(src_dir / file_path, "r", encoding="UTF-8") as file:
            config: PasdControllersConfig.LoadedYaml = yaml.safe_load(file)

        def _snake_to_pascal_case(snake_string: str) -> str:
            return "".join(word.capitalize() for word in snake_string.split("_"))

        for controller in config["PaSD_controllers"]["base_register_maps"].values():
            for name, info in controller["registers"].items():
                if "tango_attr_name" not in info:
                    info["tango_attr_name"] = _snake_to_pascal_case(name)

        del config["common_registers"]
        return config

    @staticmethod
    def _validate_configuration(config: LoadedYaml) -> RegMapRevsDict:
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

    @classmethod
    def get_all(cls) -> AllCtrllrsDict:
        """
        Get all PaSD controllers' configuration.

        :return: validated configuration dictionary.
        """
        config = cls._load_configuration_yaml()
        validated = cls._validate_configuration(config)
        return validated["base_register_maps"]

    @classmethod
    def get_fncc(cls) -> ControllerDict:
        """
        Get the Field Node Communications Controller configuration.

        :return: validated configuration dictionary.
        """
        config = cls._load_configuration_yaml()
        validated = cls._validate_configuration(config)
        return validated["base_register_maps"]["FNCC"]

    @classmethod
    def get_fndh(cls) -> ControllerDict:
        """
        Get the Field Node Peripheral Controller (or FNDH) configuration.

        :return: validated configuration dictionary.
        """
        config = cls._load_configuration_yaml()
        validated = cls._validate_configuration(config)
        return validated["base_register_maps"]["FNPC"]

    @classmethod
    def get_smartbox(cls) -> ControllerDict:
        """
        Get the Field Node SMART Box Controller configuration.

        :return: validated configuration dictionary.
        """
        config = cls._load_configuration_yaml()
        validated = cls._validate_configuration(config)
        return validated["base_register_maps"]["FNSC"]

    @classmethod
    def get_register_map_revisions(cls) -> RegMapRevsDict | None:
        """
        Get all PaSD controllers' register map revisions changes.

        :return: validated configuration dictionary.
        """
        config = cls._load_configuration_yaml()
        validated = cls._validate_configuration(config)
        return validated.get("register_map_revisions")  # type: ignore


if __name__ == "__main__":
    CONFIG_BASE = PasdControllersConfig.get_all()
    CONFIG_REVISIONS = PasdControllersConfig.get_register_map_revisions()
    print("Validated configurations with defaults applied:")
    pprint(CONFIG_BASE)
    print("Validated register map revisions with defaults applied:")
    pprint(CONFIG_REVISIONS)

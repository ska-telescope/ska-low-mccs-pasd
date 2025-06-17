import io
import json
import os
import re
import sys
from optparse import OptionParser
from typing import Optional, Sequence, Union
from urllib.parse import quote


class Parser:
    """
    JSON Schema to Markdown parser.

    Examples
    --------
    >>> import jsonschema2md
    >>> parser = jsonschema2md.Parser()
    >>> md_lines = parser.parse_schema(json.load(input_json))
    """

    tab_size = 2

    def _construct_description_line(
        self, obj: dict, add_type: bool = False
    ) -> Sequence[str]:
        """Construct description line of property, definition, or item."""
        description_line = []

        if "description" in obj:
            ending = "" if re.search(r"[.?!;]$", obj["description"]) else "."
            description_line.append(f"{obj['description']}{ending}")
        if add_type:
            if "type" in obj:
                description_line.append(f"Must be of type {obj['type']}.")
        if "minimum" in obj:
            description_line.append(f"Minimum: {obj['minimum']}.")
        if "exclusiveMinimum" in obj:
            description_line.append(f"Exclusive minimum: {obj['exclusiveMinimum']}.")
        if "maximum" in obj:
            description_line.append(f"Maximum: {obj['maximum']}.")
        if "multipleOf" in obj:
            description_line.append(f"Must be a multiple of: {obj['multipleOf']}.")
        if "exclusiveMaximum" in obj:
            description_line.append(f"Exclusive maximum: {obj['exclusiveMaximum']}.")
        if "minItems" in obj or "maxItems" in obj:
            length_description = "Length must be "
            if "minItems" in obj and "maxItems" not in obj:
                length_description += f"at least {obj['minItems']}."
            elif "maxItems" in obj and "minItems" not in obj:
                length_description += f"at most {obj['maxItems']}."
            elif obj["minItems"] == obj["maxItems"]:
                length_description += f"equal to {obj['minItems']}."
            else:
                length_description += (
                    f"between {obj['minItems']} and {obj['maxItems']} (inclusive)."
                )
            description_line.append(length_description)
        if "enum" in obj:
            description_line.append(f"Must be one of: {json.dumps(obj['enum'])}.")
        if "additionalProperties" in obj:
            if obj["additionalProperties"]:
                description_line.append("Can contain additional properties.")
            else:
                description_line.append("Cannot contain additional properties.")
        if "$ref" in obj:
            description_line.append(
                f"Refer to *[{obj['$ref']}](#{quote(obj['$ref'][2:])})*."
            )
        if "default" in obj:
            description_line.append(f"Default: {json.dumps(obj['default'])}.")
        if "pattern" in obj:
            description_line.append(f"Must match pattern ``/{obj['pattern']}/``.")

        # Only add start colon if items were added
        if description_line:
            description_line.insert(0, ":")

        return description_line

    def _construct_examples(
        self, obj: dict, indent_level: int = 0, add_header: bool = True
    ) -> Sequence[str]:
        def dump_json_with_line_head(obj, line_head, **kwargs):
            result = [
                line_head + line
                for line in io.StringIO(json.dumps(obj, **kwargs)).readlines()
            ]
            return "".join(result)

        example_lines = []
        if "examples" in obj:
            example_indentation = " " * self.tab_size * (indent_level + 1)
            if add_header:
                example_lines.append(f"\n{example_indentation}Examples:\n")
            for example in obj["examples"]:
                lang = "json"
                dump_fn = dump_json_with_line_head
                example_str = dump_fn(example, line_head=example_indentation, indent=4)
                example_lines.append(
                    f"{example_indentation}```{lang}\n{example_str}\n{example_indentation}```\n\n"
                )
        return example_lines

    def _parse_object(
        self,
        obj: Union[dict, list],
        name: Optional[str],
        output_lines: Optional[list[str]] = None,
        indent_level: int = 0,
        path: Optional[list[str]] = None,
        required: bool = False,
    ) -> list[str]:

        if not output_lines:
            output_lines = []

        indentation = " " * self.tab_size * indent_level
        indentation_items = " " * self.tab_size * (indent_level + 1)

        if isinstance(obj, list):
            output_lines.append(f"{indentation}**{name}**:\n")

            for element in obj:
                output_lines = self._parse_object(
                    element,
                    None,
                    output_lines=output_lines,
                    indent_level=indent_level + 2,
                )
            return output_lines

        if not isinstance(obj, dict):
            raise TypeError(
                f"Non-object type found in properties list: `{name}: {obj}`."
            )

        # Construct full description line
        description_line_base = self._construct_description_line(obj)
        description_line = list(
            map(
                lambda line: line.replace("\n\n", "<br>" + indentation_items),
                description_line_base,
            )
        )

        # Add full line to output
        description_line = " ".join(description_line)
        optional_format = f", format: {obj['format']}" if "format" in obj else ""
        if name is None:
            obj_type = f"{obj['type']}{optional_format}" if "type" in obj else ""
            name_formatted = ""
        else:
            required_str = ", **required**" if required else ""
            obj_type = (
                f" ({obj['type']}{optional_format}{required_str})"
                if "type" in obj
                else ""
            )
            name_formatted = f"**{name}**"
        anchor = f"<a id=\"{quote('/'.join(path))}\"></a>" if path else ""
        output_lines.append(
            f"{indentation}{anchor}* {name_formatted}{obj_type}{description_line}\n"
        )

        # Recursively parse subschemas following schema composition keywords
        schema_composition_keyword_map = {
            "allOf": "All of",
            "anyOf": "Any of",
            "oneOf": "One of",
        }
        for key, label in schema_composition_keyword_map.items():
            if key in obj:
                output_lines.append("\n")
                output_lines.append(f"{indentation_items}**{label}**\n")
                for child_obj in obj[key]:
                    output_lines = self._parse_object(
                        child_obj,
                        None,
                        output_lines=output_lines,
                        indent_level=indent_level + 2,
                    )

        # Recursively add items and definitions
        for property_name in ["items", "definitions", "$defs"]:
            if property_name in obj:
                output_lines.append("\n")
                output_lines = self._parse_object(
                    obj[property_name],
                    property_name.capitalize(),
                    output_lines=output_lines,
                    indent_level=indent_level + 1,
                )

        # Recursively add additional child properties
        if "additionalProperties" in obj and isinstance(
            obj["additionalProperties"], dict
        ):
            output_lines = self._parse_object(
                obj["additionalProperties"],
                "Additional Properties",
                output_lines=output_lines,
                indent_level=indent_level + 1,
            )

        has_children = False
        # Recursively add child properties
        for property_name in ["properties", "patternProperties"]:
            if property_name in obj:
                for property_name, property_obj in obj[property_name].items():
                    output_lines.extend("\n")
                    output_lines = self._parse_object(
                        property_obj,
                        property_name,
                        output_lines=output_lines,
                        indent_level=indent_level + 1,
                        required=property_name in obj.get("required", []),
                    )
        # Add examples
        output_lines.extend("\n")
        output_lines.extend(self._construct_examples(obj, indent_level=indent_level))
        return output_lines

    def parse_schema(self, schema_object: dict) -> list[str]:
        """Parse JSON Schema object to markdown text."""
        output_lines = []

        # Add title and description
        if "title" in schema_object:
            title = schema_object["title"]
        else:
            title = "JSON Schema"
        output_lines.append(f"{'=' * len(title)}\n")
        output_lines.append(f"{title}\n")
        output_lines.append(f"{'=' * len(title)}\n\n")

        if "description" in schema_object:
            output_lines.append(f"{schema_object['description']}\n")
            output_lines.append("\n")

        # Add items
        if "items" in schema_object:
            title = "Items"
            output_lines.append(f"{'*' * len(title)}\n")
            output_lines.append(f"{title}\n")
            output_lines.append(f"{'*' * len(title)}\n\n")
            output_lines.extend(self._parse_object(schema_object["items"], "Items"))
            output_lines.append("\n")

        # Add additional properties
        if "additionalProperties" in schema_object and isinstance(
            schema_object["additionalProperties"], dict
        ):
            title = "Additional Properties"
            output_lines.append(f"{'*' * len(title)}\n")
            output_lines.append(f"{title}\n")
            output_lines.append(f"{'*' * len(title)}\n\n")
            output_lines.extend(
                self._parse_object(
                    schema_object["additionalProperties"],
                    "Additional Properties",
                )
            )
            output_lines.append("\n")

        # Add pattern properties
        if "patternProperties" in schema_object:
            title = "Pattern Properties"
            output_lines.append(f"{'*' * len(title)}\n")
            output_lines.append(f"{title}\n")
            output_lines.append(f"{'*' * len(title)}\n\n")
            for obj_name, obj in schema_object["patternProperties"].items():
                output_lines.extend(self._parse_object(obj, obj_name))
            output_lines.append("\n")

        # Add properties
        if "properties" in schema_object:
            title = "Properties"
            output_lines.append(f"{'*' * len(title)}\n")
            output_lines.append(f"{title}\n")
            output_lines.append(f"{'*' * len(title)}\n\n")
            for obj_name, obj in schema_object["properties"].items():
                output_lines.extend(self._parse_object(obj, obj_name))
            output_lines.append("\n")

        # Add definitions / $defs
        for name in ["definitions", "$defs"]:
            if name in schema_object:
                title = "Definitions"
                output_lines.append(f"{'*' * len(title)}\n")
                output_lines.append(f"{title}\n")
                output_lines.append(f"{'*' * len(title)}\n\n")
                for obj_name, obj in schema_object[name].items():
                    output_lines.extend(
                        self._parse_object(obj, obj_name, path=[name, obj_name])
                    )
                output_lines.append("\n")

        # Add examples
        if "examples" in schema_object:
            title = "Examples"
            output_lines.append(f"{'*' * len(title)}\n")
            output_lines.append(f"{title}\n")
            output_lines.append(f"{'*' * len(title)}\n\n")
            output_lines.extend(
                self._construct_examples(
                    schema_object, indent_level=0, add_header=False
                )
            )
            output_lines.append("\n")

        return output_lines


# pylint: disable=too-many-locals
def main(checking: bool) -> int:
    """
    Update auto-generated schema docs.

    :param checking: if we are running in checking mode.

    :returns: exit code
    """
    parser = Parser()
    schemas_dir = "src/ska_low_mccs_pasd/schemas"
    base_files = os.listdir(schemas_dir)

    dirs_to_check = [schemas_dir] + [
        f"{schemas_dir}/{folder}" for folder in base_files if "." not in folder
    ]
    for directory in dirs_to_check:
        schemas = [
            f"{directory}/{file}"
            for file in os.listdir(directory)
            if file.endswith(".json")
        ]

        for schema in schemas:
            rst_file_folders = []
            rst_file = schema.replace(".json", ".rst").split("/")[-1]
            rst_file_folder = "docs/src/schemas/" + rst_file.split("_")[0] + "/"
            rst_file_folders.append(rst_file_folder)
            rst_file_path = rst_file_folder + rst_file

            with open(schema, encoding="utf-8") as file:
                lines = file.readlines()

            text = ""
            rest: list[str] = []
            for line in lines:
                text += line
            schema_dict = json.loads(text)
            rest = parser.parse_schema(schema_dict)
            last_line = "not_empty"
            trimmed_rest = []
            for line in rest:
                if last_line.strip() != "" or line.strip() != "":
                    trimmed_rest.append(line)
                last_line = line
            if checking:
                if not os.path.isdir(rst_file_folder):
                    print(f"{rst_file_folder} does not exist!")
                    return 1
                if (
                    len(
                        [
                            schema_file
                            for schema_file in os.listdir(directory)
                            if schema_file.endswith(".json")
                        ]
                    )
                    != len(os.listdir(rst_file_folder)) - 1
                ):
                    print(
                        f"{rst_file_folder} does not have the same amount of docs as schemas in {directory}!"
                    )
                    return 1
                with open(rst_file_path, "r", encoding="utf-8") as file:
                    if "".join(trimmed_rest) != "".join(file.readlines()):
                        print(f"{rst_file} is out of date!")
                        return 1
            else:
                os.makedirs(rst_file_folder, exist_ok=True)
                with open(rst_file_path, "w", encoding="utf-8") as file:
                    file.writelines(trimmed_rest)

    docs_schemas_base_dir = "docs/src/schemas"
    docs_schema_dirs = os.listdir(docs_schemas_base_dir)

    if checking:
        docs_count = len(
            [
                docs_schema_dir
                for docs_schema_dir in docs_schema_dirs
                if os.path.isdir(docs_schemas_base_dir + "/" + docs_schema_dir)
            ]
        )
        schema_count = len(
            [
                schema_folder
                for schema_folder in base_files
                if os.path.isdir(schemas_dir + "/" + schema_folder)
                and not schema_folder.startswith("__")
            ]
        )
        if any([schema_folder.endswith(".json") for schema_folder in base_files]):
            schema_count += 1
        if docs_count != schema_count:
            print(f"{docs_schema_dirs} has too many folders, maybe for old device.")
            return 1

    device_schema_list = [
        f"{docs_schemas_base_dir}/{device_schemas}"
        for device_schemas in docs_schema_dirs
        if "." not in device_schemas
    ]
    for device_schema_folder_path in device_schema_list:
        with open(
            f"{device_schema_folder_path}/index.rst", "w", encoding="utf-8"
        ) as file:
            device_name = device_schema_folder_path.split("/")[-1]
            title = device_name + " Schemas"

            file.write("".join(["=" for _ in range(len(title))]) + "\n")
            file.write(title + "\n")
            file.write("".join(["=" for _ in range(len(title))]) + "\n\n")
            file.write(f"These schemas are for use with {device_name} commands\n\n")
            file.write(".. toctree::\n")
            file.write(f"  :caption: {device_name} Schemas\n")
            file.write("  :maxdepth: 2\n\n")

            for schema in sorted(os.listdir(device_schema_folder_path)):
                if schema == "index.rst":
                    continue
                file.write(f"  {schema.split('.')[0]}\n")

    return 0


if __name__ == "__main__":
    cli_parser = OptionParser()
    cli_parser.add_option(
        "-c", "--check", dest="check", action="store_true", default=False
    )
    checking = vars(cli_parser.parse_args()[0])["check"]
    result = main(checking)

    if result == 0:
        print("Docs script executed successfuly")
        sys.exit(0)
    if result == 1:
        print("Current docs schemas out of date, run make python-format")
        sys.exit(1)

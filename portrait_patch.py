"""
Stardew Valley HD Portrait Patcher by purplexpresso
    Last Modified 10/4/22
    Converts PyTK based HD Portrait mods for Stardew Valley into HD Portraits compatible mod
    See usage with portrait_patch.py --help
    Licensed under GPLv3.0
"""
__version__ = "1.4.0"

import argparse
from enum import Enum, auto
from collections import defaultdict
import pathlib
import re as regex
from copy import deepcopy
from typing import Any, Dict, Final, List, DefaultDict, Callable
from functools import partial

import json5


def _clone_dir_tree(source: pathlib.Path, destination: pathlib.Path) -> None:
    import shutil

    shutil.copytree(
        source.resolve(),
        destination.resolve(),
        ignore=lambda directory, files: [
            file for file in files if (pathlib.Path(directory) / file).is_file()
        ],
        dirs_exist_ok=not (source.name in destination.parts),  # prevent recursion
    )


def _get_variant_metadata_file(
    portrait_file: pathlib.Path, variant: str | None, VARIANT_SEPARATOR: str
) -> pathlib.Path:
    return portrait_file.with_name(
        portrait_file.stem
        if variant is None or portrait_file.stem.endswith(variant)
        else f"{portrait_file.stem}{VARIANT_SEPARATOR}{variant}"
    ).with_suffix(".json")


def _get_copy_dir(
    copy_dir: pathlib.Path | None,
    copy_mode: bool,
    main_directory: pathlib.Path,
    subdirectory: pathlib.Path,
) -> pathlib.Path | None:
    return (
        (copy_dir if copy_dir is not None else main_directory / "Patched HD Portraits")
        / subdirectory.stem
        if copy_mode
        else None
    )


def _valid_dir(path: str) -> pathlib.Path:
    directory = pathlib.Path(path)
    if directory.is_dir():
        return directory
    else:
        raise argparse.ArgumentTypeError(f"{directory.resolve()} is not a directory")


def _get_file_or_backup(file: pathlib.Path) -> pathlib.Path:
    backup_file = file.with_suffix(".bak")
    return backup_file if backup_file.is_file() else file


def _write_and_backup(
    file: pathlib.Path,
    json_data: Dict[str, Any],
    main_dir: pathlib.Path,
    copy_dir: pathlib.Path | None,
    force_rewrite=False,
) -> None:
    backup_file = file.with_suffix(".bak")
    if not (force_rewrite or copy_dir or backup_file.is_file()):
        file.rename(backup_file)
    with (
        file if copy_dir is None else copy_dir / file.relative_to(main_dir)
    ).with_suffix(".json").open("w+") as new_file:
        json5.dump(json_data, new_file, quote_keys=True, indent=4)


def update_dependencies(manifest_file: pathlib.Path) -> Dict[str, Any]:
    with manifest_file.open("r") as manifest:
        manifest_dict: DefaultDict[str, Any] = defaultdict(list, json5.load(manifest)) # type: ignore

    PYTK_DEPENDENCY: Final = {"UniqueID": "Platonymous.Toolkit"}
    HD_PORTRAITS_DEPENDENCY: Final = {"UniqueID": "tlitookilakin.HDPortraits"}

    dependencies: List[Dict[str, str]] = manifest_dict["Dependencies"]
    if HD_PORTRAITS_DEPENDENCY not in dependencies:
        dependencies.append(HD_PORTRAITS_DEPENDENCY)
    try:
        dependencies.remove(PYTK_DEPENDENCY)
    except ValueError:
        pass
    
    manifest_dict["GeneratedBy"] = f"Generated by Portrait Patcher {__version__}, by purplexpresso. Licensed under GPLv3."

    return dict(manifest_dict)


def create_metadata_json(
    portrait_file: pathlib.Path, target_name: str
) -> Dict[str, Any] | None:
    try:
        with portrait_file.with_suffix(".pytk.json").open("r") as pytk_file:
            pytk_dict: Dict[str, Any] = json5.load(pytk_file) # type: ignore
    except FileNotFoundError:
        return None

    STARDEW_PORTRAIT_SIZE: Final[int] = 64

    sprite_size = int(pytk_dict["Scale"]) * STARDEW_PORTRAIT_SIZE
    asset_dict = {
        "Size": sprite_size,
        "Portrait": target_name,
    }
    # if "Animation" in pytk_dict:
    #     pytk_animation: Dict[str, int] = pytk_dict["Animation"]
    #     asset_dict["Animation"] = {
    #         "HFrames": int(
    #             pytk_animation.get("FrameWidth", sprite_size) / sprite_size
    #         ),
    #         "VFrames": int(
    #             pytk_animation.get("FrameHeight", sprite_size) / sprite_size
    #         ),
    #         "Speed": int(1000 / pytk_animation.get("FPS", 30)),
    #     }
    return asset_dict


def shop_tile_framework_portraits(
    content_patch_dir: pathlib.Path,
    copy_dir: pathlib.Path,
    hd_portraits: pathlib.PurePath,
    hd_portraits_patch: pathlib.PurePath,
) -> None:
    return


class FileParsed(Enum):
    INDIVIDUAL = auto()
    GLOBBED = auto()


def content_patcher_portraits(
    content_patch_dir: pathlib.Path,
    copy_dir: pathlib.Path | None,
    hd_portraits: pathlib.PurePath,
    hd_portraits_patch: pathlib.PurePath,
) -> None:
    CP_WILDCARD: Final[str] = "*"
    VARIANT_SEPARATOR: Final[str] = "_"

    if copy_dir is not None:
        _clone_dir_tree(content_patch_dir, copy_dir)
    content_file: Final = _get_file_or_backup(content_patch_dir / "content.json")

    content_patcher_token: Final = regex.compile(r"\{\{[a-zA-Z0-9_./]+\}\}")
    with content_file.open("r") as content:
        content_dict: Dict[str, Any] = json5.load(content) # type: ignore

    parsed_metadata_files: Dict[pathlib.Path, FileParsed] = {}
    metadata_item: Dict[str, Any]
    for index, metadata_item in enumerate(content_dict["Changes"].copy()):
        portrait_name: Final = pathlib.PurePath(metadata_item["Target"])
        if portrait_name.parent.stem != "Portraits":
            continue

        target_variant: str | None = (
            VARIANT_SEPARATOR.join(portrait_name.stem.split(VARIANT_SEPARATOR)[1:])
            or None
        )

        portrait_file: Final = content_patch_dir / pathlib.PurePath(
            metadata_item["FromFile"]
        )
        metadata_file: Final = _get_variant_metadata_file(
            portrait_file, target_variant, VARIANT_SEPARATOR
        )

        hd_portraits_target_path: Final = hd_portraits / portrait_name.stem
        hd_portraits_patch_target_path: Final = hd_portraits_patch / portrait_name.stem

        metadata_item.pop("PatchMode", None)

        portrait_item = deepcopy(metadata_item)

        metadata_item["Action"] = "Load"
        metadata_item["Target"] = hd_portraits_target_path.as_posix()
        metadata_item["FromFile"] = metadata_file.relative_to(
            content_patch_dir
        ).as_posix()

        portrait_item["Action"] = "EditImage"
        portrait_item["Target"] = hd_portraits_patch_target_path.as_posix()
        portrait_item["FromFile"] = portrait_file.relative_to(
            content_patch_dir
        ).as_posix()

        content_dict["Changes"].insert(2 * index, portrait_item)

        if content_patcher_token.search(portrait_file.stem):
            glob_string: str = regex.sub(
                content_patcher_token,
                CP_WILDCARD,
                str(portrait_file.relative_to(content_patch_dir)),
            )
            for globbed_portrait_file in content_patch_dir.glob(glob_string):
                globbed_metadata_file = _get_variant_metadata_file(
                    globbed_portrait_file, target_variant, VARIANT_SEPARATOR
                )

                if globbed_metadata_file.resolve() in parsed_metadata_files:
                    continue

                parsed_metadata_files[
                    globbed_metadata_file.resolve()
                ] = FileParsed.GLOBBED

                globbed_metadata_json = create_metadata_json(
                    globbed_portrait_file, hd_portraits_patch_target_path.as_posix()
                )
                if globbed_metadata_json is None:
                    continue

                _write_and_backup(
                    globbed_metadata_file,
                    globbed_metadata_json,
                    content_patch_dir,
                    copy_dir,
                    force_rewrite=True,
                )
        elif portrait_file.is_file():
            if (
                parsed_metadata_files.get(metadata_file.resolve())
                is FileParsed.INDIVIDUAL
            ):
                continue

            parsed_metadata_files[metadata_file.resolve()] = FileParsed.INDIVIDUAL
            metadata_json = create_metadata_json(
                portrait_file, hd_portraits_patch_target_path.as_posix()
            )
            if metadata_json is None:
                continue

            _write_and_backup(
                metadata_file,
                metadata_json,
                content_patch_dir,
                copy_dir,
                force_rewrite=True,
            )
    
    content_dict["Format"] = "1.28.0"

    _write_and_backup(
        content_file,
        content_dict,
        content_patch_dir,
        copy_dir,
    )

    manifest_file: Final = _get_file_or_backup(content_patch_dir / "manifest.json")
    manifest_dict: Final = update_dependencies(manifest_file)

    _write_and_backup(
        manifest_file,
        manifest_dict,
        content_patch_dir,
        copy_dir,
    )


ModTypeFunctions = Callable[
    [pathlib.Path, pathlib.Path | None, pathlib.PurePath, pathlib.PurePath], None
]


class ModType(Enum):
    CONTENT_PATCHER: ModTypeFunctions = partial(content_patcher_portraits)  # type: ignore
    SHOP_TILE_FRAMEWORK: ModTypeFunctions = partial(shop_tile_framework_portraits)  # type: ignore

    @classmethod
    def identify_folder(cls, directory: pathlib.Path):
        if (directory / "content.json").is_file():
            return ModType.CONTENT_PATCHER
        elif (directory / "shops.json").is_file():
            return ModType.SHOP_TILE_FRAMEWORK
        else:
            return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Converts PyTK based HD Portrait mods for Stardew Valley into HD Portraits compatible mod",
    )
    parser.add_argument(
        "--path",
        "-p",
        required=True,
        type=_valid_dir,
        help="Path to directory containing mod folders, or a single mod folder",
    )
    parser.add_argument(
        "--mode",
        "-m",
        default="internal",
        type=str,
        choices=["internal", "copy"],
        help="Mode of operation. [internal] changes the files inside the folder, while [copy] creates a new folder structure entirely, most useful with a VFS",
    )
    parser.add_argument(
        "--copy_dir",
        nargs="?",
        type=_valid_dir,
        help="Sets directory where copied files are outputed. Only valid if --mode copy is specified",
    )
    parser.add_argument(
        "--prefix",
        default="HDPortraitsPatch",
        type=str,
        help="Prefix on generated Targets. Do not touch unless you know what you're doing.",
    )
    args = parser.parse_args()

    directory: Final[pathlib.Path] = args.path
    copy_mode: Final[bool] = args.mode == "copy"
    copy_dir: Final[pathlib.Path] | None = args.copy_dir

    hd_portraits: Final = pathlib.PurePath("Mods/HDPortraits")
    hd_portraits_patch: Final = pathlib.PurePath(f"Mods/{args.prefix}")

    if directory.parts[-2:] == ("Stardew Valley", "Mods"):
        print(
            "Please do not run this script in your Stardew Valley/Mods folder! This script will modify every Content Pack you have installed. Could be scary! Please point to a specific mod"
        )
        return

    main_folder_type: ModType | None = ModType.identify_folder(directory)
    if main_folder_type is not None:
        main_folder_type.value(
            directory,
            _get_copy_dir(copy_dir, copy_mode, directory, directory),
            hd_portraits,
            hd_portraits_patch,
        )
    else:
        for subdirectory in directory.iterdir():
            if not subdirectory.is_dir():
                continue
            subdirectory_type: ModType | None = ModType.identify_folder(subdirectory)
            if subdirectory_type is not None:
                subdirectory_type.value(
                    subdirectory,
                    _get_copy_dir(copy_dir, copy_mode, directory, subdirectory),
                    hd_portraits,
                    hd_portraits_patch,
                )

    return


if __name__ == "__main__":
    main()

import logging
import re
from typing import List, Set

from . import languages
from .settings import args, config
from .sub_block import SubBlock, ParsingException
from libs import langdetect
from pathlib import Path

logger = logging.getLogger("subtitle")


class Subtitle:
    blocks: List[SubBlock]
    ad_blocks: Set[SubBlock]
    warning_blocks: Set[SubBlock]
    language: str
    file: Path
    short_path: Path

    def __init__(self, subtitle_file: Path) -> None:
        self.file = subtitle_file
        self.blocks = []
        self.ad_blocks = set()
        self.warning_blocks = set()

        file_content = read_file(self.file)
        try:
            self._parse_file_content(file_content)
        except ParsingException as e:
            e.subtitle_file = self.file
            raise e
        try:
            self.short_path = self.file.relative_to(config.relative_base)
        except ValueError:
            self.short_path = self.file

        if not self:
            raise SubtitleContentException(self.file)

        if args.language:
            self.language = args.language
        else:
            self.determine_language()

        if not self.language_is_correct():
            logger.warning(f"the language within the file does not match the file label: '{self.language}'")

        if args.destroy_list:
            self.mark_blocks_for_deletion(args.destroy_list)

    def warn(self, block: SubBlock):
        if block not in self.ad_blocks:
            self.warning_blocks.add(block)

    def ad(self, block: SubBlock):
        try:
            self.warning_blocks.remove(block)
        except KeyError:
            pass
        self.ad_blocks.add(block)

    def _parse_file_content(self, file_content: str) -> None:
        file_content = re.sub(r'\n\s*\n', '\n', file_content)
        file_content = file_content.replace("—", "--")
        self._breakup_block(file_content.split("\n"))

    def _breakup_block(self, raw_blocks: [str]) -> None:
        last_break = 0
        for i in range(2, len(raw_blocks)):
            if "-->" in raw_blocks[i] and raw_blocks[i - 1].isnumeric():
                block = SubBlock("\n".join(raw_blocks[last_break:i - 1]))
                last_break = i - 1
                if block.content:
                    self.blocks.append(block)

    def mark_blocks_for_deletion(self, purge_list: List[int]) -> None:
        for index in purge_list:
            if index-1 >= len(self.blocks):
                continue
            self.blocks[index-1].regex_matches = 3

    def language_is_correct(self) -> bool:
        if self.language == "und":
            return True  # unknown language.
        language_code_2 = languages.get_2letter_code(self.language)

        if not language_code_2:
            return True  # unknown language.

        sub_content: str = ""
        for block in self.blocks:
            sub_content += block.content

        if len(sub_content) < 500:
            return True  # not enough content to estimate language.
        detected_language = langdetect.detect_langs(sub_content)[0]

        return detected_language.lang == language_code_2 and detected_language.prob > 0.8

    def determine_language(self) -> None:
        if config.default_language:
            self.language = config.default_language
            return

        self.language = "und"

        for suffix in self.file.suffixes[-3:-1]:
            parsed_lang = suffix.replace(":", "-").replace("_", "-").split("-")[0][1:]
            if languages.is_language(parsed_lang):
                self.language = parsed_lang
                return

        sub_content: str = ""
        for block in self.blocks:
            sub_content += block.content
        if len(sub_content) < 500:
            return
        detected_language = langdetect.detect_langs(sub_content)[0]
        if detected_language.prob > 0.9:
            self.language = detected_language.lang

    def to_content(self) -> str:
        content = ""
        for block in self.blocks:
            content += f"{block.current_index}\n" \
                       f"{block}\n" \
                       f"\n"
        return content[:-1]

    def get_warning_indexes(self) -> List[str]:
        l: List[str] = []
        for block in self.warning_blocks:
            l.append(str(block.current_index))
        return l

    def reindex(self):
        index = 1
        for block in self.blocks:
            block.current_index = index
            index += 1

    def __str__(self) -> str:
        return str(self.file)

    def __len__(self) -> int:
        return len(self.blocks)

    def __bool__(self) -> bool:
        for block in self.blocks:
            if block.content:
                return True
        return False


class SubtitleContentException(Exception):
    subtitle_file: str

    def __init__(self, subtitle_file):
        self.subtitle_file = subtitle_file

    def __str__(self) -> str:
        return f"File {self.subtitle_file} is empty."


def read_file(file: Path) -> str:
    file_content: str

    try:
        with file.open("r", encoding="utf-8") as opened_file:
            file_content = opened_file.read()
    except UnicodeDecodeError:
        with file.open("r", encoding="cp1252") as opened_file:
            file_content = opened_file.read()

    return file_content

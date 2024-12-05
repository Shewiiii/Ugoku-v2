import json
from pathlib import Path


class PitchAccent:
    def __init__(self) -> None:
        self.path: Path = Path('bot') / 'jpdb' / 'pitch_accent'
        self.pitch_list = []

        for file_path in self.path.iterdir():
            if file_path.is_file():
                with file_path.open(encoding='UTF-8') as f:
                    self.pitch_list.extend(json.load(f))

    def get(self, word: str) -> str:
        for pitch in self.pitch_list:
            if word in pitch:
                pitch_type = pitch[2]['pitches'][0]['position']
                reading = pitch[2]['reading']
                word_len = len(reading)

                if pitch_type == 0:
                    str_pitch = 'L' + 'H' * (word_len - 1)
                elif pitch_type == 1:
                    str_pitch = 'H' + 'L' * (word_len - 1)
                else:
                    str_pitch = 'L' + 'H' * \
                        (pitch_type - 1) + 'L' * (word_len - pitch_type)
                    if pitch_type == word_len:
                        str_pitch += '(L)'

                return str_pitch

        return ''


pa = PitchAccent()

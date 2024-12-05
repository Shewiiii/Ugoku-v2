import pandas as pd
from pathlib import Path


class ExSentences:
    def __init__(self) -> None:
        self.path: Path = Path('bot') / 'jpdb'
        mono_data = pd.read_csv(self.path / 'jp_sentences.tsv', sep='\t',)
        duo_data = pd.read_csv(self.path / 'jp_eng_sentences.tsv', sep='\t',)
        self.mono_sentences = mono_data['jp_sentence'].tolist()
        self.duo_sentences = dict(
            zip(duo_data['jp_sentence'], duo_data['en_sentence']))

    @staticmethod
    def highlight_word(sentence: str, word: str) -> str:
        return sentence.replace(word, f"**{word}**")

    @staticmethod
    def is_kanji(word: str) -> bool:
        return all(not (12354 <= ord(char) <= 12538) for char in word)

    def is_relevant(self, word: str, jp: str, en: str = '') -> bool:
        i = jp.find(word)
        if len(jp) > 70 or len(en) > 140:
            return False

        # If the word is a kanji, but not alone in the sentence, return False
        # Example of irrelevant case: word: 生, word in sentence: 高校生.
        if self.is_kanji(word):
            if (i > 0 and self.is_kanji(jp[i - 1])) or \
                    (i + len(word) < len(jp) and self.is_kanji(jp[i + len(word)])):
                return False

        # Particles before and after the word
        pre_particles = {
            'は', 'が', 'に', 'の', 'へ', 'を', 'と', 'や', 'ど', 'も',
            'ら', 'り', 'い', 'で', 'う', 'か', 'も', 'い', '、', '。',
            '　', '？', '！'
        }
        post_particles = {
            'だ', 'で', 'の', 'は', 'が', 'と', 'い', 'し', 'ば',
            'よ', '、', '。', '　', '？', '！'
        }

        # If the letter before/after is not a kanji nor a particle, return False
        # Example: これは*ペン*だ is valid, かわいい*ペン*ギンだね is not.
        if i > 0 and not (self.is_kanji(jp[i - 1]) or jp[i - 1] in pre_particles):
            return False
        if (i + len(word) < len(jp)
                and not (self.is_kanji(jp[i + len(word)]) or jp[i + len(word)] in post_particles)):
            return False

        return True

    def get(self, word: str, shortest: bool = True) -> dict:
        examples = {'jp': '', 'en': ''}
        min_jp_len = float('inf')

        # Search a bilingual sentence
        for jp_sentence, en_sentence in self.duo_sentences.items():
            if word in jp_sentence and self.is_relevant(word, jp_sentence, en_sentence):
                current_len = len(jp_sentence)
                if current_len < min_jp_len:
                    examples['jp'] = jp_sentence
                    examples['en'] = en_sentence
                    min_jp_len = current_len
                    if not shortest:
                        break

        # Search a monolingual sentence
        if not examples['jp']:
            for jp_sentence in self.mono_sentences:
                if word in jp_sentence and self.is_relevant(word, jp_sentence):
                    current_len = len(jp_sentence)
                    if current_len < min_jp_len:
                        examples['jp'] = jp_sentence
                        min_jp_len = current_len
                        if not shortest:
                            break

        # Highlight the word in sentence
        for key in ['jp', 'en']:
            examples[key] = self.highlight_word(examples[key], word)

        return examples


sentence = ExSentences()

from pathlib import Path
import re

from app.core.config import Settings
from app.schemas.dream import ClarificationQuestion, DreamSymbols, ExtractionResult
from app.services.aliyun import AliyunModels


PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_symbols.txt"

SCENE_WORDS = ["森林", "学校", "家里", "房间", "城市", "街道", "海边", "海里", "山上", "天空", "车站", "医院", "电梯", "楼顶", "公园"]
CHARACTER_WORDS = ["妈妈", "母亲", "爸爸", "父亲", "朋友", "同学", "老师", "孩子", "陌生人", "老人", "猫", "狗", "蛇", "鸟", "鹿"]
EXPLICIT_PERSON_WORDS = [
    "外婆", "外公", "奶奶", "爷爷", "姥姥", "姑姑", "叔叔", "舅舅",
    "妈妈", "母亲", "爸爸", "父亲", "朋友", "同学", "老师", "孩子", "陌生人", "老人",
]
PERSON_STATE_PREFIXES = (
    ("已经去世的", "已经去世"),
    ("已经过世的", "已经过世"),
    ("去世的", "已经去世"),
    ("过世的", "已经过世"),
    ("已故的", "已故"),
    ("已故", "已故"),
    ("失联的", "失联"),
    ("年幼的", "年幼"),
)
OBJECT_WORDS = ["门", "钥匙", "镜子", "手机", "车", "火车", "船", "雨伞", "鞋", "书", "花", "水", "火", "月亮", "星星", "行李"]
# These concrete nouns are copied from the user input only into the visible,
# editable confirmation fields.  They are not sent straight to retrieval and
# take effect only after the user confirms the extracted dream symbols.
EXPLICIT_OBJECT_WORDS = ["行李", "旅行箱", "背包"]
ACTION_WORDS = ["奔跑", "跑", "追赶", "追", "飞", "坠落", "掉下", "游泳", "游", "躲", "寻找", "哭", "喊", "打开", "关上", "走"]
EMOTION_WORDS = ["害怕", "恐惧", "焦虑", "紧张", "难过", "悲伤", "开心", "高兴", "平静", "孤独", "愤怒", "困惑", "安心"]
REALITY_CONTEXT_MARKERS = ("最近", "近期", "现实中", "现实生活", "工作上", "工作中", "清醒时")


class DreamExtractor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def extract(self, dream_text: str) -> ExtractionResult:
        if self.settings.model_mode == "mock":
            result = self._mock_extract(dream_text)
        elif self.settings.model_mode == "aliyun":
            result = self._aliyun_extract(dream_text)
        else:
            raise RuntimeError("不支持的模型模式")
        result = self._ensure_explicit_objects(dream_text, result)
        result = self._ensure_explicit_person_states(dream_text, result)
        result = self._ensure_reality_context(dream_text, result)
        # Retain explicit narrator transformations even if extraction omits them.
        narrative = re.sub(r'“[^”]*”|「[^」]*」|"[^"\n]*"', "。", dream_text)
        for match in re.finditer(r"(?:^|[，。！？；\n])\s*(?:我梦见)?(?:梦中的我|我自己|自己|我)(?:在梦里|在梦中)?变成(?:了)?([^，。！？；\n]{1,70})", narrative):
            form = match.group(1).strip()
            if form not in result.symbols.dreamer:
                result.symbols.dreamer.append(form)
        result.symbols = DreamSymbols.model_validate(result.symbols.model_dump())
        return self._ensure_emotion_clarification(result)

    def _mock_extract(self, dream_text: str) -> ExtractionResult:
        symbols = DreamSymbols(
            scenes=self._matches(dream_text, SCENE_WORDS),
            characters=self._matches(dream_text, CHARACTER_WORDS),
            objects=self._matches(dream_text, OBJECT_WORDS),
            actions=self._matches(dream_text, ACTION_WORDS),
            emotions=self._matches(dream_text, EMOTION_WORDS),
            relationships=[],
            reality_context=self._reality_sentences(dream_text),
            uncertain_fields=[] if any(word in dream_text for word in EMOTION_WORDS) else ["梦中的主要情绪"],
        )
        if not any(symbols.model_dump().values()):
            symbols.uncertain_fields = ["场景", "人物", "动作", "情绪"]
        clarification = None
        if not symbols.emotions:
            clarification = ClarificationQuestion(
                question="你在这个梦里最接近哪种感受？",
                options=["紧张或害怕", "平静或放松", "开心或兴奋", "记不清"],
            )
        return ExtractionResult(symbols=symbols, clarification=clarification)

    def _aliyun_extract(self, dream_text: str) -> ExtractionResult:
        return AliyunModels(self.settings).chat_json(
            self.settings.qwen_extract_model,
            PROMPT_PATH.read_text(encoding="utf-8"),
            dream_text,
            ExtractionResult,
        )

    @staticmethod
    def _ensure_explicit_objects(dream_text: str, result: ExtractionResult) -> ExtractionResult:
        explicit_objects = DreamExtractor._matches(dream_text, EXPLICIT_OBJECT_WORDS)
        result.symbols.objects = list(dict.fromkeys([*result.symbols.objects, *explicit_objects]))
        return result

    @staticmethod
    def _reality_sentences(dream_text: str) -> list[str]:
        sentences = [item.strip() for item in re.split(r"[。！？!?\n]+", dream_text) if item.strip()]
        return [
            sentence for sentence in sentences
            if any(marker in sentence for marker in REALITY_CONTEXT_MARKERS)
        ][:5]

    @staticmethod
    def _ensure_reality_context(
        dream_text: str, result: ExtractionResult
    ) -> ExtractionResult:
        explicit_context = DreamExtractor._reality_sentences(dream_text)
        result.symbols.reality_context = list(dict.fromkeys([
            *result.symbols.reality_context,
            *explicit_context,
        ]))[:5]
        return result

    @staticmethod
    def _ensure_explicit_person_states(
        dream_text: str, result: ExtractionResult
    ) -> ExtractionResult:
        """Retain explicit identity state that a model may strip from a person label."""
        people = list(result.symbols.characters)
        people.extend(
            person
            for person in EXPLICIT_PERSON_WORDS
            if person in dream_text and person not in people
        )
        enriched_people: list[str] = []
        relationships = list(result.symbols.relationships)
        for person in people:
            enriched = person
            for original_prefix, normalized_state in PERSON_STATE_PREFIXES:
                phrase = f"{original_prefix}{person}"
                if phrase in dream_text:
                    enriched = phrase
                    relationship = f"{person}{normalized_state}"
                    if relationship not in relationships:
                        relationships.append(relationship)
                    break
            if enriched not in enriched_people:
                enriched_people.append(enriched)
        result.symbols.characters = enriched_people
        result.symbols.relationships = relationships
        return result

    @staticmethod
    def _ensure_emotion_clarification(result: ExtractionResult) -> ExtractionResult:
        """Do not interpret an ambiguous dream before its felt tone is known.

        The extraction model may decide that an emotion question is optional.
        For dream interpretation, however, the same surreal image can mean very
        different things when it felt comforting, curious, tense, or frightening.
        Keep the product's single-question limit and deterministically spend it
        on felt tone whenever the user did not state one.
        """
        if result.symbols.emotions:
            return result
        if "梦中的主要情绪" not in result.symbols.uncertain_fields:
            result.symbols.uncertain_fields.append("梦中的主要情绪")
        result.clarification = ClarificationQuestion(
            question="你在这个梦里最接近哪种感受？",
            options=["紧张或害怕", "好奇或期待", "平静或安心", "难过或失落", "记不清"],
        )
        return result

    @staticmethod
    def _matches(text: str, words: list[str]) -> list[str]:
        matches: list[str] = []
        for word in words:
            if word in text and not any(word != found and word in found for found in matches):
                matches.append(word)
        return matches[:12]

"""The learning path: chapters in order.

Each game names its chapter (``Game.chapter``) and position
(``Game.order``). The gallery shows chapter -> family -> game, and the
unlock path walks the chapters in the order below and the games by
``order`` inside each chapter. Draft games and the ``workbench`` chapter
sit outside the path and are always open.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chapter:
    id: str
    title: str
    subtitle: str
    #: Accent color token used by the frontend (``--c-<color>``).
    color: str
    icon: str
    #: Two or three sentences shown when the chapter opens.
    intro: str
    #: The big question the chapter answers.
    question: str

    def to_json(self) -> dict:
        return dict(self.__dict__)


CHAPTERS: tuple[Chapter, ...] = (
    Chapter(
        "chance", "Chance", "Luck you can count", "amber", "dice",
        "Dice have no memory and no plan, but they follow rules you can count. "
        "Probability tells you how often, expected value tells you how much, "
        "entropy tells you how surprised to be.",
        "When does a decision beat the dice?",
    ),
    Chapter(
        "trees", "Game Trees", "Think ahead", "teal", "tree",
        "Without dice, every position has a true value: win, draw or loss with "
        "best play. Follow the tree of moves back from the end and you can find it.",
        "Who wins if nobody makes a mistake?",
    ),
    Chapter(
        "dice-and-choice", "Luck Meets Skill", "Dice and decisions", "orange", "race",
        "Most family games mix both: you choose, then the dice answer. A good "
        "policy does not win every game. It wins more of them over many games.",
        "How much of winning is skill?",
    ),
    Chapter(
        "outguess", "Outguess", "Moving at the same time", "violet", "hands",
        "When both players choose at once, there is no best move, only a best mix. "
        "Nash equilibrium: no one gains by changing their strategy alone.",
        "How do you play well against someone who reads you?",
    ),
    Chapter(
        "hidden", "Hidden Cards", "What you cannot see", "rose", "cards",
        "Cards in hand are private. You decide on what you know, guess the rest "
        "from what others do, and sometimes make them guess wrong.",
        "How do you decide without seeing everything?",
    ),
    Chapter(
        "learning", "Learning Machines", "Trial, error, reward", "lime", "brain",
        "Reinforcement learning finds a strategy without being told the rules: "
        "try, collect reward, update. The trick is balancing trying new things "
        "against using what already works.",
        "Can a program find the best strategy by itself?",
    ),
    Chapter(
        "society", "Many Players", "Trade and negotiate", "sky", "people",
        "With more than two players, helping a rival can hurt the leader. "
        "Trades, alliances and timing become part of the strategy.",
        "When should you help an opponent?",
    ),
    Chapter(
        "workbench", "Workbench", "Your drafts", "slate", "wrench",
        "Games you are building. Always unlocked. Edit the Python file, save, "
        "and the board updates while you play.",
        "What game will you add next?",
    ),
)

PATH_CHAPTERS = tuple(c.id for c in CHAPTERS if c.id != "workbench")


def chapter(chapter_id: str) -> Chapter:
    for c in CHAPTERS:
        if c.id == chapter_id:
            return c
    return CHAPTERS[-1]

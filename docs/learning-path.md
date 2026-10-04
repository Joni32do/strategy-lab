# The learning path

Games are ordered into chapters, each answering one question:

| Chapter | Question | Ideas |
| --- | --- | --- |
| Chance | When does a decision beat the dice? | probability, expected value, entropy |
| Game Trees | Who wins if nobody makes a mistake? | game tree, minimax, symmetry |
| Luck Meets Skill | How much of winning is skill? | expectimax, risk |
| Outguess | How do you play well against someone who reads you? | Nash equilibrium, mixed strategies |
| Hidden Cards | How do you decide without seeing everything? | information sets, beliefs, bluffing |
| Learning Machines | Can a program find the best strategy by itself? | MDPs, value functions, Q-learning |
| Many Players | When should you help an opponent? | negotiation, multi-agent play |

## Unlocks, stars, concept cards

Defined in {mod}`strategy_lab.learn.progress`, all derived from your history:

- Inside a chapter, a game opens once the one before it was finished.
- A chapter opens when two games of the previous chapter are finished.
- Challenges ({class}`~strategy_lab.core.game.Challenge`) earn stars:
  finish, win or draw against a named bot, reach a score, open a lens, or
  build a card stack that reaches a win rate in simulation.
- Finishing a game adds its concepts to your cheatsheet.

The full card text is in [Concept cards](generated/concepts.md).

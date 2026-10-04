"""Long-form texts of the concept cards (merged into :mod:`concepts`).

Each entry: ``body`` (short Markdown, inline math in ``$...$``),
``formula`` (LaTeX, no ``$``), ``example`` and ``related`` concept ids.
"""

TEXTS = {
    # ------------------------------------------------------------------ lab
    "policy": dict(
        body="A policy answers one question for every situation you can meet: *what do I do here?* "
             "It can be a lookup table, a stack of rules, a search procedure or a neural network.\n\n"
             "A **deterministic** policy always picks the same action in a state; a **stochastic** "
             "policy picks with probabilities. Everything in this lab is a way to find a better policy.",
        formula=r"\pi(a \mid s) = P(\text{play } a \text{ in state } s)",
        example="In Pig, *hold as soon as the turn total reaches 20* is a complete policy.",
        related=("rule-cards", "mdp", "mixed-strategy"),
    ),
    "rule-cards": dict(
        body="A rule card is one readable idea: *Finish it*, *Block the win*, *Hold at 20*. "
             "A stack of cards, read top to bottom, is a policy. **PICK** cards choose an action; "
             "**AVOID** cards veto actions for the cards below, but never the last one left.\n\n"
             "Card order matters: the same cards in another order are another strategy.",
        example="Tic-Tac-Toe is played perfectly by: win, block, fork, smother forks, center, "
                "mirror corner, corner, edge.",
        related=("policy", "simulation"),
    ),
    "simulation": dict(
        body="One game tells you little; luck can hide a good strategy for a while. Play a "
             "strategy hundreds of times and count: the win rate becomes a reliable measurement.\n\n"
             "Seats rotate every game so neither side keeps the first-move advantage.",
        formula=r"\hat p = \frac{\text{wins}}{n}, \qquad \text{error} \approx \sqrt{\frac{\hat p(1-\hat p)}{n}}",
        example="With 100 games and a true win rate of 50%, the measured rate lands between "
                "40% and 60% about 95% of the time.",
        related=("law-of-large-numbers", "variance"),
    ),
    # --------------------------------------------------------------- chance
    "probability": dict(
        body="A probability is a number between 0 (never) and 1 (always). With equally likely "
             "outcomes, count: favorable outcomes divided by all outcomes.\n\n"
             "Probabilities of all outcomes add up to 1. The chance that something does **not** "
             "happen is $1 - p$.",
        formula=r"P(A) = \frac{\#\text{favorable}}{\#\text{possible}}",
        example="A fair die shows a 1 with probability $1/6$. In Pig that is your risk on every roll.",
        related=("independence", "expected-value"),
    ),
    "independence": dict(
        body="Two events are independent when one tells you nothing about the other. "
             "Then their joint probability is the product.\n\n"
             "Dice are independent across rolls. After three 6s in a row, the next roll is still "
             "a 6 with probability $1/6$: believing otherwise is the *gambler's fallacy*.",
        formula=r"P(A \cap B) = P(A)\,P(B)",
        example="In Pig, the chance to survive 5 rolls in a row is $(5/6)^5 \\approx 40\\%$.",
        related=("probability",),
    ),
    "expected-value": dict(
        body="The expected value is the long-run average: each outcome weighted by its "
             "probability. Decisions that maximize it win over many repetitions, even if they "
             "lose single games.",
        formula=r"E[X] = \sum_x x \, P(X = x)",
        example="In Pig with turn total $t$, one more roll changes it on average by "
                "$\\tfrac{5}{6}\\cdot 4 - \\tfrac{1}{6}\\, t$. That is positive while $t < 20$: "
                "the reason behind *Hold at 20*.",
        related=("variance", "risk", "law-of-large-numbers"),
    ),
    "variance": dict(
        body="Variance measures how far single results scatter around the average. Two "
             "strategies can have the same expected value and very different variance: "
             "one is steady, the other swings.\n\n"
             "The standard deviation $\\sigma$ is its square root, in the same units as the results.",
        formula=r"\operatorname{Var}(X) = E\big[(X - E[X])^2\big]",
        example="A Snakes & Ladders game can take 20 turns or 120: huge variance from tiny decisions.",
        related=("expected-value", "risk"),
    ),
    "law-of-large-numbers": dict(
        body="The average of many independent tries settles near the expected value. The "
             "error shrinks like $1/\\sqrt{n}$: four times as many games halve it.",
        formula=r"\frac{1}{n}\sum_{i=1}^{n} X_i \;\xrightarrow{\;n\to\infty\;}\; E[X]",
        example="That is why the lab simulates 100 games instead of 5.",
        related=("simulation", "expected-value"),
    ),
    "distribution-of-sums": dict(
        body="With two dice there are 36 equally likely combinations but only 11 sums. "
             "Many combinations give 7, only one gives 2 or 12: middle sums are common, "
             "extreme sums rare.",
        formula=r"P(\text{sum} = s) = \frac{6 - |s - 7|}{36}, \quad s = 2,\dots,12",
        example="In Qwixx the 7 comes up 6 times in 36 white-dice rolls, the 2 and the 12 only "
                "once. Skipping a 7 is cheap; skipping toward a 12 is expensive.",
        related=("probability", "entropy"),
    ),
    "entropy": dict(
        body="Entropy is the average surprise of a random event, measured in **bits**. "
             "A fair coin has 1 bit; a fair die about 2.58 bits; a coin that always lands "
             "heads has 0.\n\n"
             "Entropy is highest when all outcomes are equally likely: that is maximal "
             "uncertainty. The surprise of one outcome is $-\\log_2 p$.",
        formula=r"H(X) = -\sum_x p(x)\,\log_2 p(x)",
        example="A rolled 1 in Pig ($p = 1/6$) carries $\\log_2 6 \\approx 2.58$ bits of surprise. "
                "In Rock-Paper-Scissors, a player with entropy below $\\log_2 3$ bits is predictable.",
        related=("probability", "policy-entropy", "mixed-strategy"),
    ),
    # ---------------------------------------------------------------- trees
    "game-tree": dict(
        body="Start with the current position as the root. Every legal move is a branch to "
             "a new position, and so on until the game ends. The leaves carry the results.\n\n"
             "A complete game tree contains every possible game.",
        example="Tic-Tac-Toe has 255,168 complete games but only 5,478 distinct positions: "
                "many paths lead to the same board.",
        related=("branching-factor", "minimax", "backward-induction"),
    ),
    "branching-factor": dict(
        body="The average number of moves per position. A tree with branching factor $b$ "
             "and depth $d$ has about $b^d$ leaves, which explodes quickly.",
        formula=r"\text{leaves} \approx b^{\,d}",
        example="Chess: $b \\approx 35$ and $d \\approx 80$ plies, so about $10^{123}$ games. "
                "Connect Four: $b \\le 7$, still about $4.5 \\cdot 10^{12}$ positions.",
        related=("game-tree", "heuristic"),
    ),
    "backward-induction": dict(
        body="Solve from the end. In a final position the result is known. One move earlier, "
             "the player to move picks the best result for themselves. Repeat back to the start.",
        example="In Nim, positions with nim-sum 0 are lost for the player to move: every move "
                "leads to nim-sum not 0, from which the opponent can restore 0.",
        related=("minimax", "winning-position"),
    ),
    "minimax": dict(
        body="In a two-player zero-sum game, assume the opponent always answers with the move "
             "that is worst for you. Pick the move whose worst case is best.",
        formula=r"V(s) = \max_{a} \min_{b} V(s_{a,b})",
        example="The minimax value of the empty Tic-Tac-Toe board is 0: a draw.",
        related=("game-tree", "solved-game", "expectimax"),
    ),
    "winning-position": dict(
        body="A position is **winning** (N-position) if some move leads to a losing position for "
             "the opponent, and **losing** (P-position) if every move leads to a winning one.\n\n"
             "Knowing which positions are which is a complete strategy.",
        formula=r"\text{Nim: lost for the mover} \iff h_1 \oplus h_2 \oplus \dots \oplus h_k = 0",
        example="Heaps 1, 2, 3: $1 \\oplus 2 \\oplus 3 = 0$, so whoever moves first loses with perfect play.",
        related=("backward-induction", "solved-game"),
    ),
    "symmetry": dict(
        body="If a rotation or mirror turns one position into another, both have the same value. "
             "Folding symmetric positions together shrinks the tree without losing anything.",
        example="On the empty Tic-Tac-Toe board, 9 moves are really 3 decisions: center, corner, "
                "edge. Folding by rotations and mirrors turns 5,478 positions into 765.",
        related=("game-tree", "markov-property"),
    ),
    "solved-game": dict(
        body="A game is **solved** when the result under perfect play is known. *Weakly solved*: "
             "a strategy reaching it from the start is known. *Strongly solved*: for every position.",
        example="Tic-Tac-Toe: draw. Connect Four: first player wins (1988). Checkers: draw (2007). "
                "Chess: unknown.",
        related=("minimax", "winning-position"),
    ),
    "heuristic": dict(
        body="When the tree is too big to search to the end, stop at some depth and *estimate* "
             "the position with an evaluation function. Search quality then depends on depth "
             "and on how good the estimate is.",
        example="Connect Four bots here count open lines: three in a row with a free fourth cell "
                "scores high.",
        related=("branching-factor", "minimax"),
    ),
    # ------------------------------------------------------- dice and choice
    "expectimax": dict(
        body="Minimax with chance nodes: you maximize, the opponent minimizes, and at dice "
             "rolls you take the probability-weighted average.",
        formula=r"V(s) = \sum_{o} P(o)\, V(s_o) \quad \text{at chance nodes}",
        example="Backgammon programs evaluate a move by averaging over all 21 possible next rolls.",
        related=("minimax", "expected-value"),
    ),
    "risk": dict(
        body="A risky choice has a wide spread of outcomes. Whether to take it depends on the "
             "situation: when you are behind, a gamble with lower average can still raise your "
             "chance to win.",
        example="In Pig, Keep-pace Kai rolls longer when behind and holds earlier when ahead.",
        related=("variance", "expected-value"),
    ),
    "luck-vs-skill": dict(
        body="Compare two policies over many games. If the better one wins 52%, the game is "
             "mostly luck; if it wins 95%, mostly skill.\n\n"
             "One game proves nothing; the win rate over many does.",
        example="In Snakes & Ladders even the best die choice only nudges the odds; in "
                "Tic-Tac-Toe the perfect policy never loses.",
        related=("simulation", "variance"),
    ),
    # ------------------------------------------------------------- outguess
    "zero-sum": dict(
        body="The payoffs of all players add up to zero (or a constant): every gain is someone "
             "else's loss. There is no reason to cooperate.",
        formula=r"u_1(a, b) + u_2(a, b) = 0",
        example="Rock-Paper-Scissors and Matching Pennies are zero-sum; the Prisoner's Dilemma is not.",
        related=("minimax", "nash-equilibrium"),
    ),
    "best-response": dict(
        body="Fix the opponent's strategy. Your best response is the strategy that earns you the "
             "most against it. Against a predictable opponent, the best response exploits them.",
        formula=r"BR(\sigma_2) = \arg\max_{\sigma_1} u_1(\sigma_1, \sigma_2)",
        example="Against someone who plays Rock half the time, Paper is the best response.",
        related=("nash-equilibrium", "exploitability"),
    ),
    "dominant-strategy": dict(
        body="A strategy that is better than every alternative no matter what the opponent does. "
             "A rational player always plays it, and a dominated strategy never.",
        example="In the Prisoner's Dilemma, defecting earns more whether the other cooperates "
                "(5 > 3) or defects (1 > 0).",
        related=("social-dilemma", "best-response"),
    ),
    "nash-equilibrium": dict(
        body="A strategy for each player such that nobody gains by changing their own strategy "
             "alone: each one is a best response to the others.\n\n"
             "Every finite game has at least one, possibly in mixed strategies (Nash, 1950).",
        formula=r"u_i(\sigma_i^*, \sigma_{-i}^*) \ge u_i(\sigma_i, \sigma_{-i}^*) \quad \forall i, \sigma_i",
        example="Rock-Paper-Scissors: both play each move with probability 1/3.",
        related=("best-response", "mixed-strategy", "exploitability"),
    ),
    "mixed-strategy": dict(
        body="Randomize on purpose. If any fixed pattern can be read and punished, the safe "
             "choice is a probability mix that makes the opponent indifferent.",
        formula=r"\sigma = (p_1, \dots, p_n), \quad \sum_i p_i = 1",
        example="In Matching Pennies, 50/50 is the only strategy a mind reader cannot beat.",
        related=("nash-equilibrium", "entropy"),
    ),
    "exploitability": dict(
        body="How much a perfect opponent who knows your strategy would win against it. "
             "A Nash equilibrium strategy in a zero-sum game has exploitability 0.",
        formula=r"\text{expl}(\sigma_1) = \max_{\sigma_2} u_2(\sigma_1, \sigma_2) - v",
        example="Playing Rock 50% in RPS: the Paper answer wins on average 0.25 per round.",
        related=("best-response", "nash-equilibrium"),
    ),
    "regret": dict(
        body="After a round, regret is how much better another action would have done. "
             "*Regret matching* plays each action with probability proportional to its "
             "accumulated positive regret. In self-play its average strategy approaches a "
             "Nash equilibrium.",
        formula=r"R_T(a) = \sum_{t=1}^{T} \big(u(a, b_t) - u(a_t, b_t)\big)",
        example="The Nash lens plots regret matching in RPS spiraling toward (1/3, 1/3, 1/3).",
        related=("nash-equilibrium", "exploration"),
    ),
    "social-dilemma": dict(
        body="Each player's individually best choice produces a result that is worse for "
             "everyone than cooperation would be. The equilibrium is not efficient.\n\n"
             "In repeated play, strategies like Tit-for-Tat can sustain cooperation.",
        example="Prisoner's Dilemma: both defect and get 1 each, although both cooperating "
                "would give 3 each.",
        related=("dominant-strategy", "nash-equilibrium"),
    ),
    "coordination": dict(
        body="A game with several equilibria where players want to match. The difficulty is not "
             "conflict but agreeing on *which* equilibrium.",
        example="Stag Hunt: hunting the stag together pays most, but hunting hare alone is safe. "
                "Both (stag, stag) and (hare, hare) are equilibria.",
        related=("nash-equilibrium", "social-dilemma"),
    ),
    # --------------------------------------------------------------- hidden
    "imperfect-information": dict(
        body="Some parts of the state are hidden from some players: cards in hand, a sealed bid. "
             "Players must decide on what they can observe.",
        example="In Kuhn Poker you see your own card, never the opponent's until showdown.",
        related=("information-set", "belief"),
    ),
    "information-set": dict(
        body="All game states a player cannot tell apart. A policy must choose the same "
             "action in every state of one information set, because it cannot know which "
             "one it is in.",
        example="Holding the Queen in Kuhn Poker, the opponent's Jack and King are one information set.",
        related=("imperfect-information", "belief"),
    ),
    "belief": dict(
        body="A probability distribution over the hidden part of the state, updated with every "
             "observation by Bayes' rule.",
        formula=r"P(h \mid o) = \frac{P(o \mid h)\, P(h)}{P(o)}",
        example="When a Doppelkopf player plays a club queen, everyone updates who is on the Re team.",
        related=("information-set", "bluffing"),
    ),
    "bluffing": dict(
        body="Betting with a weak hand so the opponent cannot read your bets. In equilibrium "
             "a bluff is not a trick but a necessary frequency: never bluffing makes strong bets "
             "easy to fold against.",
        example="In the Kuhn Poker equilibrium, the first player bets the Jack with probability "
                "$\\alpha \\in [0, 1/3]$ and the King with probability $3\\alpha$.",
        related=("mixed-strategy", "nash-equilibrium"),
    ),
    # ------------------------------------------------------------- learning
    "mdp": dict(
        body="A Markov decision process describes a task by states $S$, actions $A$, transition "
             "probabilities $P(s' \\mid s, a)$ and rewards $R$. Reinforcement learning searches "
             "for a policy that maximizes the expected return.",
        formula=r"(S, A, P, R, \gamma)",
        example="FrozenLake: 16 cells, 4 moves, slippery transitions, reward 1 at the goal.",
        related=("markov-property", "reward-return", "value-function"),
    ),
    "markov-property": dict(
        body="The future depends on the present state only, not on how you got there. "
             "Choosing what goes into the state decides whether this holds.",
        formula=r"P(s_{t+1} \mid s_t, a_t) = P(s_{t+1} \mid s_0, a_0, \dots, s_t, a_t)",
        example="A chess board alone is not Markov: castling rights and repetitions live in the "
                "history. The Model lens lists such choices for every game.",
        related=("mdp", "symmetry"),
    ),
    "reward-return": dict(
        body="A reward is the score of one step. The return is the (discounted) sum of rewards "
             "from now until the episode ends; it is what the agent maximizes.",
        formula=r"G_t = \sum_{k=0}^{\infty} \gamma^k R_{t+k+1}",
        example="Cliff Walking: -1 per step, -100 for falling, so the return favors short safe paths.",
        related=("discount", "value-function"),
    ),
    "discount": dict(
        body="The discount factor $\\gamma$ between 0 and 1 makes later rewards count less. "
             "Close to 1: far-sighted. Close to 0: greedy for immediate reward.",
        formula=r"G_t = R_{t+1} + \gamma\, G_{t+1}",
        example="With $\\gamma = 0.9$, a reward 10 steps away counts $0.9^{10} \\approx 0.35$.",
        related=("reward-return", "bellman"),
    ),
    "value-function": dict(
        body="$V^\\pi(s)$ is the expected return starting in $s$ and following policy $\\pi$. "
             "$Q^\\pi(s, a)$ is the same after first taking action $a$. Acting greedily on $Q$ "
             "gives a better policy.",
        formula=r"V^\pi(s) = E_\pi[G_t \mid s_t = s]",
        example="The Learn lens paints $V(s)$ on the FrozenLake grid: cells near the goal glow.",
        related=("bellman", "q-learning"),
    ),
    "bellman": dict(
        body="The value of a state equals the expected immediate reward plus the discounted "
             "value of the next state. *Value iteration* applies this update until nothing changes.",
        formula=r"V^*(s) = \max_a \sum_{s'} P(s' \mid s, a)\,\big[R(s, a, s') + \gamma V^*(s')\big]",
        example="Value iteration solves FrozenLake 4x4 in a few dozen sweeps.",
        related=("value-function", "discount"),
    ),
    "exploration": dict(
        body="To find the best action you must try actions that currently look worse. "
             "Too little exploration locks in early mistakes; too much wastes reward.\n\n"
             "Common recipes: $\\varepsilon$-greedy, optimism (UCB), softmax with a temperature.",
        formula=r"\text{UCB}(a) = \bar x_a + \sqrt{\frac{2 \ln t}{n_a}}",
        example="In the bandit game, pulling only the first lucky arm often misses a better one.",
        related=("regret", "policy-entropy", "q-learning"),
    ),
    "q-learning": dict(
        body="Learn $Q(s, a)$ from experience alone, without knowing the transition probabilities. "
             "After every step, move the estimate toward the reward plus the best next value.",
        formula=r"Q(s,a) \leftarrow Q(s,a) + \alpha\,\big[r + \gamma \max_{a'} Q(s',a') - Q(s,a)\big]",
        example="On Cliff Walking, Q-learning finds the short path along the cliff edge.",
        related=("value-function", "exploration", "bellman"),
    ),
    "policy-entropy": dict(
        body="The entropy of a policy's action distribution. Early in learning high entropy "
             "means exploring; a converged greedy policy has entropy near 0.\n\n"
             "A softmax policy's temperature sets it: hot is random, cold is greedy.",
        formula=r"\pi(a \mid s) = \frac{e^{Q(s,a)/T}}{\sum_b e^{Q(s,b)/T}}",
        example="The Learn lens plots policy entropy falling as the agent becomes sure.",
        related=("entropy", "exploration"),
    ),
    # -------------------------------------------------------------- society
    "multi-agent": dict(
        body="With three or more players, strategy includes everyone else's interactions. "
             "Hurting the leader can help you even if it costs you something.",
        example="In Catan, refusing trades with a player close to 10 points is often right.",
        related=("negotiation", "nash-equilibrium"),
    ),
    "negotiation": dict(
        body="A trade helps both sides or nobody would agree. The question is *who it helps more*. "
             "A trade that helps a stronger rival more than you can be a loss.",
        formula=r"\text{net} = \text{my gain} - \lambda(\text{their strength}) \cdot \text{their gain}",
        example="The Catan trading policy raises $\\lambda$ as the partner gets close to winning.",
        related=("multi-agent",),
    ),
    "repeated-game": dict(
        body="Play the same stage game for many rounds and strategies can depend on the past. "
             "Threats and rewards become credible: defect now, and lose cooperation later.",
        formula=r"U = \sum_{t=1}^{T} \delta^{t-1} u(a_t, b_t)",
        example="Ten rounds of the Prisoner's Dilemma reward Tit-for-Tat far more than one round does.",
        related=("tit-for-tat", "social-dilemma"),
    ),
    "tit-for-tat": dict(
        body="Nice (never defects first), retaliating (answers a defection), forgiving (returns "
             "to cooperation) and simple. It won Robert Axelrod's computer tournaments in 1980.",
        example="Against Tit-for-Tat Tess in the Prisoner's Dilemma, cooperating every round pays 3 per round.",
        related=("repeated-game", "social-dilemma"),
    ),
    "value-iteration": dict(
        body="Start with all values at 0. Sweep over every state and apply the Bellman update. "
             "The values converge to the optimal ones; acting greedily on them is an optimal policy. "
             "It needs the model: the transition probabilities.",
        formula=r"V_{k+1}(s) = \max_a \sum_{s'} P(s' \mid s,a)\,[R + \gamma V_k(s')]",
        example="The Learn lens solves FrozenLake with value iteration in a few milliseconds.",
        related=("bellman", "q-learning"),
    ),
    "ucb": dict(
        body="Add a bonus to every estimate that shrinks the more often an action was tried. "
             "Rarely tried actions look optimistic and get explored; the bonus fades as evidence grows.",
        formula=r"a_t = \arg\max_a \Big(\bar x_a + \sqrt{\tfrac{2\ln t}{n_a}}\Big)",
        example="Upper-bound Ursula in the bandit game plays UCB1.",
        related=("exploration", "regret"),
    ),
    "monte-carlo": dict(
        body="When exact calculation is too hard, simulate. Play the position out many times "
             "with some rollout policy and average the results. The estimate improves like "
             "$1/\\sqrt{n}$ and works for any game with rules you can run.",
        formula=r"\hat V(s) = \frac{1}{n}\sum_{i=1}^{n} G^{(i)}",
        example="The Odds lens plays every legal move, then finishes the game 80 times at random.",
        related=("law-of-large-numbers", "mcts"),
    ),
    "mcts": dict(
        body="Monte Carlo tree search repeats four steps: **select** a path down the tree "
             "favoring good and rarely tried moves, **expand** one new node, **simulate** a "
             "random playout, **back up** the result. The most visited move is played.",
        formula=r"\text{UCT}(a) = \bar Q_a + c\sqrt{\frac{\ln N}{n_a}}",
        example="Monte the MCTS bot plays chess and backgammon without any chess knowledge.",
        related=("monte-carlo", "ucb", "game-tree"),
    ),
}

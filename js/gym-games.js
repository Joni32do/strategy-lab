/* ============================================================
 * The explorable-game catalog: entries for the MDP registry.
 * Each game ships SEVERAL candidate MDPs — picking the state
 * space is a design decision, and this file makes it visible.
 * See js/mdp.js for the schema.
 * ============================================================ */
(function () {
  'use strict';

  /* Tic-Tac-Toe — the reference entry. Also a playable card-stack
   * game (playable: true), so the play-mode RL lens embeds this
   * same panel. Everything is Markov here; the interesting choice
   * is raw vs symmetry-folded. */
  MDP.register({
    id: 'tictactoe',
    name: 'Tic-Tac-Toe',
    icon: '⭕',
    genre: 'classic',
    players: 2,
    backend: 'js',
    envId: 'tictactoe (local JS engine); open_spiel: tic_tac_toe',
    playable: true,
    blurb: 'The hello world of MDPs: tiny, fully observable, and genuinely memoryless — '
      + 'the board alone determines everything that can still happen.',
    history: 'nowhere — the current board is a complete summary of the past. That is why '
      + 'this game is the baseline: every other entry in the catalog breaks this property '
      + 'somewhere, and the broken spot is where the interesting strategy lives.',
    defaultMdp: 'folded',
    mdps: [
      {
        id: 'raw', name: 'Raw board', markov: true,
        state: 'the 3x3 board from the mover\'s perspective',
        stateSize: '5478 reachable states',
        actions: 'the empty squares (9 at most)',
        transition: 'your mark lands (deterministic), then the opponent replies - from '
          + 'your seat the opponent is part of the environment',
        reward: '+1 win / 0 draw / -1 loss at the end; gamma = 1',
        note: 'honest and simple, but the agent re-learns every rotation and mirror of '
          + 'the same position eight times over.',
      },
      {
        id: 'folded', name: 'Symmetry-folded board', markov: true,
        state: 'the canonical representative of the board under the dihedral group D4 '
          + '(rotations + mirrors)',
        stateSize: '765 states — a 7x compression',
        actions: 'one move per symmetry-equivalence class (opening: 3, not 9 - center, corner, edge)',
        reward: '+1 win / 0 draw / -1 loss at the end; gamma = 1',
        note: 'same game, 7x fewer states to visit: the fold is free generalisation. '
          + 'The play-mode RL lens shows this fold live on every position.',
      },
    ],
    rulebook: {
      summary: 'Two players, X and O, take turns marking a 3x3 grid.',
      steps: [
        { title: 'The board', text: 'A 3x3 grid of empty squares. X moves first, then '
          + 'players alternate placing their mark on any empty square.' },
        { title: 'Winning', text: 'The first player to line up three of their marks in a '
          + 'row, column or diagonal wins immediately.' },
        { title: 'Draw', text: 'If all nine squares fill with no three-in-a-row, the game '
          + 'is a draw. With perfect play from both sides it always is.' },
      ],
    },
  });

  /* Chess — perfect information, but the board alone is not the state.
   * Castling rights, en passant, and threefold repetition all live
   * outside "what the pieces look like right now"; only the third
   * MDP below (FEN + position history) is what a rules-correct
   * engine actually needs. */
  MDP.register({
    id: 'chess',
    name: 'Chess',
    icon: '♟️',
    genre: 'board',
    players: 2,
    backend: 'open_spiel',
    envId: 'chess',
    play: { kind: 'spiel', game: 'chess' },
    blurb: 'Perfect information, huge tree: the board looks like the whole state, but '
      + 'castling rights, en passant, and repetition draws are invisible unless you '
      + 'also carry the history that produced the position.',
    history: 'a position tells you almost everything - except whether you may still '
      + 'castle, capture en passant, or are about to draw by repetition; all three '
      + 'live in the history.',
    defaultMdp: 'fen-history',
    mdps: [
      {
        id: 'board-only', name: 'Board + side to move', markov: false,
        state: 'the 8x8 piece placement plus whose turn it is',
        stateSize: '~10^43 reachable positions',
        actions: 'legal moves from the board alone (about 35 on average, up to 218)',
        reward: '+1 win / 0 draw / -1 loss at the end; gamma = 1',
        note: 'the naive encoding - cheap to represent, but you cannot legally '
          + 'generate castling or en passant moves, and you cannot detect a '
          + 'repetition draw, without more than the board.',
      },
      {
        id: 'fen', name: 'FEN (board + rights + ep + clock)', markov: 'approx',
        state: 'board + side to move + castling rights + en-passant square + '
          + 'halfmove clock',
        actions: 'legal moves (about 35 on average, up to 218)',
        reward: '+1 win / 0 draw / -1 loss at the end; gamma = 1',
        note: 'Markov for check, checkmate, and the 50-move rule, but threefold '
          + 'repetition still needs to know which earlier positions recurred - '
          + 'FEN alone cannot see that.',
      },
      {
        id: 'fen-history', name: 'FEN + position history', markov: true,
        state: 'FEN plus the set of positions reached since the last irreversible '
          + 'move (pawn move or capture)',
        actions: 'legal moves (about 35 on average, up to 218); open_spiel / AlphaZero '
          + 'encode a fixed 4672-action space',
        reward: '+1 win / 0 draw / -1 loss at the end; gamma = 1',
        note: 'what engines actually track - fully Markov, including repetition '
          + 'claims, at the cost of carrying a growing position list until the '
          + 'next capture or pawn move resets it.',
      },
    ],
    rulebook: {
      summary: 'The classic two-player board game; White moves first.',
      steps: [
        { title: 'The goal', text: 'Checkmate the opposing king - attack it so that it '
          + 'cannot escape capture on the next move. Stalemate (no legal move but not in '
          + 'check) and several other conditions are draws.' },
        { title: 'The pieces', text: 'Each side has a king, queen, two rooks, two bishops, '
          + 'two knights and eight pawns, each moving in its own way. Pawns promote on '
          + 'reaching the far rank.' },
        { title: 'Special rules', text: 'Castling, en passant capture, and the threefold-'
          + 'repetition and fifty-move draw rules all depend on history the board alone '
          + 'does not show - which is exactly what the MDP panel above is about.' },
      ],
    },
  });

  /* Tetris — single-player, but the "physics" (gravity, falling motion)
   * and the piece randomizer (7-bag) are both invisible to a single
   * static frame or a single board snapshot. */
  MDP.register({
    id: 'tetris',
    name: 'Tetris',
    icon: '🧩',
    genre: 'atari',
    players: 1,
    backend: 'gymnasium',
    envId: 'ALE/Tetris-v5',
    blurb: 'Looks like a puzzle over a static board, but the pixels hide motion and '
      + 'the piece randomizer hides its own memory: the modern 7-bag generator is '
      + 'not i.i.d., so what you have already seen changes what comes next.',
    history: 'the next piece looks random only if you forget the bag - the 7-bag '
      + 'randomizer deals a shuffled set of the 7 pieces before repeating, so '
      + 'remembering which of the current bag have already appeared narrows the '
      + 'distribution of what is left; a memoryless board state throws that away.',
    defaultMdp: 'board-bag',
    mdps: [
      {
        id: 'frame', name: 'Single pixel frame', markov: false,
        state: 'one 210x160 RGB frame from the Atari emulator',
        stateSize: '210x160x3 pixels',
        actions: 'joystick actions - left, right, rotate, down, noop',
        reward: 'score delta from the env',
        note: 'zero game-specific parsing needed, but a single frame cannot show '
          + 'gravity or the piece already in motion; the standard Atari fix is to '
          + 'stack 4 consecutive frames.',
      },
      {
        id: 'board-piece', name: 'Board grid + current piece', markov: 'approx',
        state: '20x10 board occupancy grid plus the current piece and its rotation',
        stateSize: '20x10 binary grid',
        actions: 'joystick actions, or one action per reachable (column, rotation) '
          + 'at the placement level',
        reward: 'shaped lines-cleared reward',
        note: 'compact and easy to reason about, but ignores the next-piece queue, '
          + 'so the agent cannot plan a placement around what is coming.',
      },
      {
        id: 'board-bag', name: 'Board + piece + next queue + 7-bag memory', markov: true,
        state: 'board occupancy grid + current piece + next-piece preview queue + '
          + 'which pieces the active 7-bag has already dealt',
        actions: 'one action per reachable (column, rotation) at the placement level',
        reward: 'score delta from the env, or shaped lines-cleared',
        note: 'the honest formulation - tracking the bag turns a seemingly random '
          + 'next piece into a narrowing, predictable distribution, at the cost of '
          + 'a bigger state. (7-bag is guideline Tetris; the Atari 2600 version '
          + 'behind ALE/Tetris-v5 predates it and its next piece is close to '
          + 'i.i.d. - same board, different MDP.)',
      },
    ],
  });

  /* Skat — imperfect information is the whole game. Your own hand and
   * the table in front of you are a sliver of what has actually
   * happened; card counting closes part of the gap, but only the
   * full observed history is the game-theoretic state open_spiel
   * operates on. */
  MDP.register({
    id: 'skat',
    name: 'Skat',
    icon: '🃏',
    genre: 'card',
    players: 3,
    backend: 'open_spiel',
    envId: 'skat',
    play: { kind: 'spiel', game: 'skat' },
    blurb: 'A 3-player trick-taking card game where the real state is not the cards '
      + 'in your hand but everything you can infer about the two hands you cannot '
      + 'see - bidding, declaration, and every card played so far.',
    history: 'your hand and the current trick say nothing about which cards are '
      + 'still out there, who bid what during the auction, or who is void in a '
      + 'suit - card counting and inference over play order live entirely in the '
      + 'history.',
    defaultMdp: 'info-set',
    mdps: [
      {
        id: 'hand-trick', name: 'Own hand + current trick', markov: false,
        state: 'your own hand plus the cards currently on the table in this trick',
        actions: 'legal cards to play (must follow suit if you can)',
        reward: 'card points -> game value won or lost per Skat scoring, credited '
          + 'to declarer vs defenders',
        note: 'cheap to track, but blind to the game: you cannot count points or '
          + 'tell who has already run out of a suit.',
      },
      {
        id: 'hand-trick-played', name: 'Own hand + trick + all cards played', markov: 'approx',
        state: 'own hand + current trick + every card played in earlier tricks '
          + 'this deal (card counting)',
        actions: 'legal cards to play (must follow suit if you can)',
        reward: 'card points -> game value won or lost per Skat scoring, credited '
          + 'to declarer vs defenders',
        note: 'lets you count remaining points and cards, but still drops who '
          + 'played which card and the bidding, so it cannot fully use inference '
          + 'about the hidden hands.',
      },
      {
        id: 'info-set', name: 'Full information set (bidding + play history)', markov: true,
        state: 'the entire observed history - the auction, the declaration (game '
          + 'type and any hand/schneider/schwarz calls), the skat pickup if any, '
          + 'and every card played in order and by whom',
        actions: 'bids and declarations during the auction, then one legal card '
          + 'per trick',
        reward: 'card points -> game value won or lost per Skat scoring rules, '
          + 'declarer vs defenders',
        note: 'this is the information state open_spiel actually operates on - '
          + 'large and growing through the deal, but it is the only formulation '
          + 'for which optimal imperfect-information play is well defined.',
      },
    ],
    rulebook: {
      summary: 'A three-player German trick game: one declarer against two defenders.',
      steps: [
        { title: 'Deal and auction', text: 'Each player gets ten cards; two go face down '
          + 'in the skat. Players bid for the right to be declarer, naming how high a game '
          + 'they will play.' },
        { title: 'Declaration', text: 'The declarer picks the game type (a trump suit, '
          + 'grand, or null), optionally taking the skat first, and plays alone against '
          + 'the other two.' },
        { title: 'Winning', text: 'Follow suit if you can. The declarer needs 61 of the 120 '
          + 'card points to win the hand; the two defenders share the rest and win by '
          + 'holding the declarer under 61.' },
      ],
    },
  });

  /* Doppelkopf — a 4-player partnership trick game, imperfect
   * information twice over: you cannot see the other hands AND you do
   * not even know for sure who your partner is until a club queen
   * shows. The vendored python_doppelkopf OpenSpiel game (./doppelkopf)
   * powers live play; two special rules are toggleable below. */
  MDP.register({
    id: 'doppelkopf',
    name: 'Doppelkopf',
    icon: '\u{1F0CA}',            // playing card ten of hearts (the "Dulle")
    genre: 'card',
    players: 4,
    backend: 'open_spiel',
    envId: 'python_doppelkopf',
    play: {
      kind: 'spiel',
      game: 'python_doppelkopf',
      // Rule toggles forwarded as OpenSpiel game parameters. Defaults
      // match scoring.Rules; see the rulebook's "Additional rules".
      options: [
        {
          key: 'second_dulle', default: true,
          label: 'Second 10H beats the first',
          note: 'With two Dullen in a trick, the later-played one wins.',
        },
        {
          key: 'karlchen', default: true,
          label: 'Karlchen',
          note: 'Winning the last trick with a JC scores a bonus point.',
        },
      ],
    },
    blurb: 'A 4-player partnership trick game where imperfect information cuts twice: '
      + 'you cannot see the other three hands, and you do not even know for certain '
      + 'who your partner is - the two players holding a queen of clubs are the hidden '
      + 'Re team, revealed only as the queens are played.',
    history: 'your own hand and the current trick hide two different things: the 46 '
      + 'cards you cannot see, and the team split. Who has played a club queen, who '
      + 'failed to follow a suit, and which points have already been captured all live '
      + 'in the history - a memoryless agent cannot tell friend from foe.',
    defaultMdp: 'info-set',
    mdps: [
      {
        id: 'hand-trick', name: 'Own hand + current trick', markov: false,
        state: 'your own hand plus the cards on the table in the current trick',
        actions: 'legal cards to play (follow the led trump or suit if you can)',
        reward: 'card points -> game value for Re vs Kontra at the end of the deal',
        note: 'blind to the whole game: you cannot count captured points and, worse, '
          + 'you cannot tell which seats are your partners.',
      },
      {
        id: 'hand-trick-counted',
        name: 'Own hand + trick + cards played + known teams', markov: 'approx',
        state: 'own hand + current trick + every card played so far + points captured '
          + 'per seat + which seats have shown a club queen',
        actions: 'legal cards to play (follow the led class if you can)',
        reward: 'card points -> game value for Re vs Kontra',
        note: 'lets you count points and read revealed teams, but still drops the '
          + 'exact order of play that inference about the two hidden hands needs.',
      },
      {
        id: 'info-set', name: 'Full information set (ordered play history)', markov: true,
        state: 'the entire observed history - every card played, in order and by whom, '
          + 'the club queens seen (team reveals), and your own dealt hand',
        actions: 'one legal card per turn, twelve tricks in all',
        reward: 'Re wins with 121+ card points; game value adds no-90/60/30, schwarz, '
          + '"against the queens" and the special points below, tripled for a lone Re',
        note: 'this is the information state OpenSpiel operates on - the only formulation '
          + 'in which optimal imperfect-information play is well defined.',
      },
    ],
    rulebook: {
      summary: 'The German four-player trick-taking classic. You sit South against three '
        + 'bots; card notation matches the observation panel (10H = ten of hearts, '
        + 'QC = queen of clubs, AD = ace of diamonds).',
      steps: [
        {
          title: 'The deck (48 cards, 240 points)',
          text: 'A doubled 24-card deck: 9, 10, J, Q, K, A in clubs, spades, hearts and '
            + 'diamonds, every card present twice. Card points: A=11, 10=10, K=4, Q=3, '
            + 'J=2, 9=0, for 240 points in all. Each of the four players is dealt 12 cards.',
        },
        {
          title: 'Hidden teams: Re vs Kontra',
          text: 'The two players dealt a queen of clubs (QC) form the Re team; the other '
            + 'two are Kontra. You are not told who your partner is - the teams reveal '
            + 'themselves only as the club queens are played. Re wins the deal with 121 '
            + 'of the 240 card points.',
        },
        {
          title: 'Trumps and their order',
          text: 'One big trump suit, strongest first: 10H (the "Dulle"), then QC QS QH QD, '
            + 'then JC JS JH JD, then AD 10D KD 9D. Every diamond is a trump. All clubs, '
            + 'spades and hearts that are not listed above are plain cards, ranked '
            + 'A > 10 > K > 9 within their suit.',
        },
        {
          title: 'Following suit',
          text: 'The first card of a trick sets the led class - either "trump" (any trump, '
            + 'including all diamonds and the Dulle) or a plain suit. You must play a card '
            + 'of the led class if you hold one; only if you are void may you discard or '
            + 'trump in.',
        },
        {
          title: 'Winning a trick',
          text: 'The highest trump in the trick wins it; if no trump was played, the '
            + 'highest card of the led suit wins. Between two otherwise identical cards '
            + 'the first one played wins (but see the Dulle rule below). The winner '
            + 'collects the cards and leads the next trick.',
        },
        {
          title: 'Scoring the deal',
          text: 'The side that took 121+ points wins one game point, plus a point each '
            + 'for holding the loser under 90, under 60, under 30, and to zero tricks '
            + '(schwarz). Kontra winning also scores "against the queens". Extra special '
            + 'points: catching a fox (the other team winning a trick that contains an AD) '
            + 'and a "Doppelkopf" (a single trick worth 40+ points).',
        },
        {
          title: 'Silent wedding',
          text: 'If one player is dealt both club queens they play a silent wedding: alone '
            + 'as Re against the other three, for triple the game value.',
        },
      ],
      additional: [
        {
          title: 'Second 10H beats the first (toggle: second_dulle)',
          text: 'The 10H (Dulle) is normally the single highest trump. Under this common '
            + 'rule, when both Dullen fall in the same trick the later-played one beats '
            + 'the earlier one - so a Dulle can be over-trumped, but only by the other '
            + 'Dulle. Switch it off in the play options to make the first Dulle unbeatable.',
        },
        {
          title: 'Karlchen (toggle: karlchen)',
          text: 'Winning the very last trick of the deal with a jack of clubs (JC) scores '
            + 'one extra game point, the "Karlchen". Off by choice in the options; on by '
            + 'default.',
        },
      ],
    },
  });

  /* Backgammon -- perfect information, but NOT deterministic: every
   * turn starts with a dice roll, and you must know that roll before
   * you can even list your legal moves. The board alone is not the
   * state you act on; the board-plus-current-dice is. Doubling cube
   * and match score add a further layer of history this catalog only
   * notes, since single-game play does not use them. */
  MDP.register({
    id: 'backgammon',
    name: 'Backgammon',
    icon: '\u{1F3B2}',            // game die
    genre: 'board',
    players: 2,
    backend: 'open_spiel',
    envId: 'backgammon',
    play: { kind: 'spiel', game: 'backgammon' },
    blurb: 'Perfect information but not deterministic: both players can always see the '
      + 'whole board, yet every turn opens with a dice roll that you must know before '
      + 'you can even list your legal moves - the pip count and the race-vs-contact '
      + 'shape of the position are what strategy is actually about.',
    history: 'the board position is Markov once you also carry the dice you must play '
      + 'this turn - nothing before that matters. The doubling cube and the match score '
      + '(in a multi-game match) are the exception: whether doubling is currently live, '
      + 'who owns the cube, and the score so far all live outside the single board and '
      + 'change what the correct move even is.',
    defaultMdp: 'board-dice',
    mdps: [
      {
        id: 'checkers-only', name: 'Checker positions only (no dice)', markov: false,
        state: 'the 24 points plus bar and off, with each checker\'s position, but not '
          + 'the roll you have to play',
        actions: 'none can be legally listed - which moves exist depends entirely on '
          + 'the dice',
        reward: '+1/-1 (or +2/+3 for gammon/backgammon) at the end; gamma = 1',
        note: 'looks like the state because it is everything you can see, but it is '
          + 'useless on its own: you cannot enumerate a single legal move without '
          + 'knowing the roll, so this is not actually Markov for the decision problem.',
      },
      {
        id: 'board-dice', name: 'Board + current dice to play', markov: true,
        state: 'checker positions (24 points, bar, off) for both sides plus the dice '
          + 'roll you must move this turn (doubles play as four moves of that number)',
        stateSize: 'roughly 10^20 reachable positions x 21 distinct dice rolls',
        actions: 'legal ways to play the roll - which checkers move, including forced '
          + 'bar re-entry and forced moves when only one die can legally be played',
        reward: '+1 win / -1 loss, doubled for a gammon (opponent bears off none) or '
          + 'tripled for a backgammon (opponent has checkers on the bar or in your '
          + 'home board); gamma = 1. Live play here uses the open_spiel default '
          + 'winloss scoring, so the returns you see are a flat +1/-1',
        note: 'this is the state open_spiel actually operates on for a single game - '
          + 'board plus roll is a complete, self-contained decision point.',
      },
      {
        id: 'cube-match', name: 'Board + dice + doubling cube + match score', markov: true,
        state: 'board + dice to play, plus the doubling cube value and who may double, '
          + 'plus the running score and match length if this is one game of a match',
        actions: 'legal checker plays, plus offering or accepting/declining a double '
          + 'when the cube is live',
        reward: 'match-adjusted equity rather than a flat +-1/2/3 - the same board '
          + 'position can call for a different move near match point than early in '
          + 'a money game',
        note: 'the full tournament formulation. Single-game play (what this catalog '
          + 'plays live) does not need the cube or score, but any serious backgammon '
          + 'engine tracks this - the cube alone roughly doubles the size of the '
          + 'decision problem.',
      },
    ],
    rulebook: {
      summary: 'A two-player race game for 15 checkers each, moved by the roll of two '
        + 'dice; first to bear off all 15 wins.',
      steps: [
        { title: 'The board', text: 'A track of 24 points grouped into four quadrants of '
          + '6. Each side starts with 15 checkers spread over fixed starting points and '
          + 'moves them in opposite directions around the board toward their own home '
          + 'board (the last 6 points).' },
        { title: 'Rolling and moving', text: 'Each turn you roll two dice and move '
          + 'checkers that many points in your direction - one checker per die, or one '
          + 'checker the sum of both, as long as every intermediate point is legal to '
          + 'land on. Rolling doubles (e.g. 5-5) gives four moves of that number instead '
          + 'of two.' },
        { title: 'Landing rules', text: 'You may land on an empty point, a point holding '
          + 'your own checkers, or a point with exactly one enemy checker (a "blot") - '
          + 'landing there hits it. You may never land on a point with two or more enemy '
          + 'checkers.' },
        { title: 'Hitting and the bar', text: 'Hitting a blot sends it to the bar. A '
          + 'checker on the bar must re-enter in the opponent\'s home board before any '
          + 'other checker may move, and re-entry is blocked on points the opponent '
          + 'holds with two or more checkers.' },
        { title: 'Bearing off', text: 'Once all 15 of your checkers are in your home '
          + 'board, you may start bearing them off - removing a checker whose point '
          + 'matches the die exactly, or a lower point if no checker sits on the exact '
          + 'number and the higher points are empty. First to bear off all 15 wins.' },
        { title: 'Scoring', text: 'A normal win scores 1 point. If the loser has borne '
          + 'off no checkers it is a gammon (2 points); if the loser still has a checker '
          + 'on the bar or in the winner\'s home board it is a backgammon (3 points).' },
      ],
      additional: [
        {
          title: 'The doubling cube',
          text: 'Money and match play add a cube marked 2, 4, 8... Either player, before '
            + 'rolling on their turn, may propose doubling the stake; the opponent must '
            + 'accept (and take control of the cube for the next double) or resign the '
            + 'game at the current value. This catalog\'s live play is a single game and '
            + 'does not use the cube - see the board-dice MDP above.',
        },
      ],
    },
  });

  /* FrozenLake — a tiny gridworld, but "tiny" hides a choice: with a
   * known map the cell index alone is Markov (the slipperiness only
   * makes the transition stochastic, not the state incomplete). The
   * interesting case is an unknown map, where which cells you have
   * already found safe or lethal is history that a memoryless agent
   * throws away and re-drowns for. */
  MDP.register({
    id: 'frozenlake',
    name: 'FrozenLake',
    icon: '❄️',
    genre: 'control',
    players: 1,
    backend: 'gymnasium',
    envId: 'FrozenLake-v1',
    play: { kind: 'gym', envId: 'FrozenLake-v1' },
    blurb: 'A 4x4 gridworld from the Gymnasium starter set: walk from S to G without '
      + 'falling into a hole. The default env is "slippery" - you move in your '
      + 'intended direction only 1/3 of the time.',
    history: 'with a KNOWN map the cell index is the whole state - perfectly Markov, '
      + '16 states. The interesting history case is an UNKNOWN map: then which cells '
      + 'you have already seen to be safe or holes is information, and a memoryless '
      + 'agent re-drowns in the same lake.',
    defaultMdp: 'index',
    mdps: [
      {
        id: 'index', name: 'Cell index (known map)', markov: true,
        state: 'your cell index (0..15) with the map known',
        stateSize: '16 states',
        actions: 'left / down / right / up',
        reward: '+1 at the goal, 0 otherwise',
        note: 'slipperiness makes the TRANSITION stochastic, not the state '
          + 'incomplete - still fully Markov.',
      },
      {
        id: 'coords-map', name: 'Coordinates + map layout', markov: true,
        state: '(row, col) plus the hole/goal layout as part of the state',
        actions: 'left / down / right / up',
        reward: '+1 at the goal, 0 otherwise',
        note: 'generalizes across maps at the cost of a much bigger state space.',
      },
      {
        id: 'explored', name: 'Coordinates + explored cells', markov: 'approx',
        state: '(row, col) plus the set of cells observed so far, for the '
          + 'unknown-map setting',
        actions: 'left / down / right / up',
        reward: '+1 at the goal, 0 otherwise',
        note: 'the map knowledge lives in history - this is a POMDP being folded '
          + 'into a belief-ish state.',
      },
    ],
  });

  /* Qwixx — the one gym entry that is OURS: server/qwixx_env.py
   * registers it into the same Gymnasium registry as the vendored
   * submodule (namespace "strategy_lab"), so it plays through the
   * normal /api/env path. The interesting MDP question here is not
   * hidden information (everyone's sheet is face up) but WHICH part of
   * a face-up sheet you keep: a row's cross COUNT scores the game, but
   * only the position of your rightmost cross says what is still legal. */
  MDP.register({
    id: 'qwixx',
    name: 'Qwixx',
    icon: '\u{270F}\u{FE0F}',     // pencil - it is a roll-and-write
    genre: 'dice',
    players: 4,
    backend: 'gymnasium',
    envId: 'strategy_lab/Qwixx-v0',
    play: { kind: 'gym', envId: 'strategy_lab/Qwixx-v0' },
    blurb: 'A roll-and-write where everybody plays every roll: the two white dice are '
      + 'offered to all four players at once, and only the active player gets the second, '
      + 'better choice. Crosses may only ever move right, so every mark you take spends '
      + 'the numbers you skipped over - the whole game is deciding what a cross is worth.',
    history: 'nothing is hidden and nothing is forgotten - the sheet IS the history, which '
      + 'is why your own row is Markov. The catch is which summary of it you keep: the '
      + 'cross COUNT is what scores, but only the POSITION of your rightmost cross says '
      + 'what is still legal, and only the other three sheets say how much game is left '
      + 'before two rows lock and it all stops.',
    defaultMdp: 'table',
    mdps: [
      {
        id: 'counts', name: 'Per-row cross counts + dice', markov: false,
        state: 'how many crosses you have in each of the four rows, your penalties, which '
          + 'rows are locked, and the six dice',
        stateSize: '19 numbers - the most compact honest-looking encoding',
        actions: 'one cross (row, number) or pass - 45 in all',
        reward: 'the change in your own score each step, so the episode return is your '
          + 'final Qwixx score',
        note: 'the counts are exactly what the scoring table eats, so this looks '
          + 'sufficient - and it is not. Five crosses in red can mean "2 3 4 5 6" (nine '
          + 'numbers still open) or "2 3 4 5 11" (only the 12 left). Same count, same '
          + 'score so far, completely different legal moves. Everything in Qwixx is '
          + 'about the frontier, and a count throws the frontier away.',
      },
      {
        id: 'sheet', name: 'Your whole sheet + dice + phase', markov: 'approx',
        state: 'all 44 boxes of your own sheet, your penalties, the locked rows, the six '
          + 'dice, whose turn it is and whether this is the white-sum or the colour step',
        stateSize: '59 numbers; a single sheet has about 2^44 raw configurations, far '
          + 'fewer reachable since crosses only move right (12^4 frontiers x subsets)',
        actions: 'the legal crosses for this roll, or pass - the env masks the rest',
        reward: 'the change in your own score each step',
        note: 'Markov for your own scoring and for every legality question, and this is '
          + 'the formulation most human players actually use. What it cannot see is how '
          + 'close the other three are: whether the row you are saving is about to be '
          + 'locked out from under you, and how many turns are left at all.',
      },
      {
        id: 'table', name: 'All four sheets + dice + phase', markov: true,
        state: 'every player\'s sheet and penalty count, the locked rows, the six dice, '
          + 'the active seat and the phase',
        stateSize: '194 numbers',
        actions: 'the legal crosses for this roll, or pass (45-way, masked)',
        reward: 'the change in your own score, or - switch reward_mode to "margin" - your '
          + 'final score minus the best opponent\'s, which is what winning actually means',
        note: 'fully Markov: dice are rolled fresh each turn, so the four sheets plus the '
          + 'roll determine everything that can still happen, including when the game '
          + 'ends. It also makes the real decision expressible - racing an opponent to a '
          + 'lock is a different game from maximising your own sheet.',
      },
    ],
    rulebook: {
      summary: 'Four players, six dice, one sheet each with a red, yellow, green and blue '
        + 'row. You hold seat 0; the other three are scripted bots. Everybody marks on '
        + 'every roll, so there is no waiting.',
      steps: [
        { title: 'The sheet', text: 'Red and yellow run 2 to 12 from left to right; green '
          + 'and blue run 12 down to 2. Crosses in a row must always be to the RIGHT of '
          + 'your rightmost cross in that row - numbers you skip past are gone for good.' },
        { title: 'The roll', text: 'The active player rolls two white dice and one die per '
          + 'colour. First, EVERY player may cross out the sum of the two white dice in '
          + 'any one row. Then the active player may additionally combine one white die '
          + 'with one coloured die and cross that number in the matching colour row.' },
        { title: 'Penalties', text: 'Nobody is ever forced to mark - but an active player '
          + 'who takes neither the white sum nor a colour combination must cross a penalty '
          + 'box, worth -5. Non-active players pass for free. Four penalties end the game.' },
        { title: 'Locking a row', text: 'To cross a row\'s rightmost number (red/yellow 12, '
          + 'green/blue 2) you must already hold at least five crosses in that row. Doing '
          + 'so also crosses the lock, which counts as one further cross, and closes the '
          + 'row for everybody - its die leaves the game. Because the white sum is offered '
          + 'to everyone at once, several players can lock the same row on the same roll, '
          + 'but each still needs their own five crosses.' },
        { title: 'End and scoring', text: 'The game stops the moment two rows are locked or '
          + 'somebody marks a fourth penalty. A row with n crosses (the lock counting as '
          + 'one) scores n*(n+1)/2: 1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 66, 78. Subtract '
          + '5 per penalty. Highest total wins.' },
      ],
      additional: [
        {
          title: 'Why the crosses are worth n*(n+1)/2',
          text: 'The triangular payout is the whole tension. The first cross in a row is '
            + 'worth 1 point, the tenth is worth 10 - so crosses are only cheap early, and '
            + 'a row you have invested in pays more for every further mark. That is what '
            + 'makes skipping four numbers to grab an 11 a real decision rather than an '
            + 'obvious one, and it is why the bots here are defined purely by how many '
            + 'numbers they will skip (2, 1 and 3 respectively).',
        },
      ],
    },
  });

  /* CartPole — the fruit fly of RL. The full 4-dim state is Markov;
   * drop the two velocities and a single snapshot cannot tell a pole
   * swinging left from one swinging right, because velocity IS
   * compressed one-step history. */
  MDP.register({
    id: 'cartpole',
    name: 'CartPole',
    icon: '⚖️',
    genre: 'control',
    players: 1,
    backend: 'gymnasium',
    envId: 'CartPole-v1',
    play: { kind: 'gym', envId: 'CartPole-v1' },
    blurb: 'The fruit fly of RL: balance a pole on a cart by pushing left or right. '
      + 'Reward +1 per step survived.',
    history: 'the full 4-dim state (position, velocity, angle, angular velocity) is '
      + 'Markov - but drop the two velocities and the remaining snapshot cannot '
      + 'tell a pole swinging left from one swinging right; the velocities ARE '
      + 'compressed history (one-step differences).',
    defaultMdp: 'full',
    mdps: [
      {
        id: 'full', name: 'Position + velocity + angle + angular velocity', markov: true,
        state: '[cart position, cart velocity, pole angle, pole angular velocity], '
          + 'continuous, Box(4)',
        actions: 'push left / push right',
        reward: '+1 per step until the pole falls or the cart leaves the track '
          + '(cap 500)',
      },
      {
        id: 'no-velocity', name: 'Position + angle only', markov: false,
        state: '[cart position, pole angle] only',
        actions: 'push left / push right',
        reward: '+1 per step until the pole falls or the cart leaves the track '
          + '(cap 500)',
        note: 'two snapshots that look identical can be one pole swinging up and '
          + 'one crashing down - the missing velocities are exactly one step of '
          + 'history. This is the cleanest \'history is key\' example in the catalog.',
      },
      {
        id: 'binned', name: 'Discretized (binned) state', markov: 'approx',
        state: 'the 4 dims discretized into coarse bins (classic tabular treatment)',
        actions: 'push left / push right',
        reward: '+1 per step until the pole falls or the cart leaves the track '
          + '(cap 500)',
        note: 'Markov up to discretization error; finer bins buy precision at the '
          + 'cost of a much bigger table.',
      },
    ],
  });
})();

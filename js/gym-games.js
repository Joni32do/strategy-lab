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
  });
})();

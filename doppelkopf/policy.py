"""Feature encoding and a small numpy policy network for Doppelkopf.

The network maps a player's view of the state to a distribution over
the 24 card types (masked to the legal ones). Everything is relative to
the acting player (seats are rotated so "me" is always seat 0), which
lets one network play every seat.

Pure numpy on purpose: the parent venv has no deep-learning framework,
and a two-hidden-layer MLP is plenty for imitating the PIMC search.
"""

import numpy as np

from doppelkopf import cards
from doppelkopf import worlds

# Follow classes indexed for features: trump, clubs, spades, hearts, diamonds.
_CLASS_INDEX = {cards.TRUMP_CLASS: 0, cards.CLUBS: 1, cards.SPADES: 2,
                cards.HEARTS: 3, cards.DIAMONDS: 4}
_NUM_CLASSES = len(_CLASS_INDEX)

NUM_FEATURES = (
    cards.NUM_CARD_TYPES                       # own hand counts
    + cards.NUM_PLAYERS * cards.NUM_CARD_TYPES  # current trick by rel. seat
    + cards.NUM_PLAYERS                        # relative leader
    + cards.NUM_PLAYERS                        # points taken by rel. seat
    + cards.NUM_CARD_TYPES                     # played counts
    + cards.NUM_PLAYERS * _NUM_CLASSES         # voids by rel. seat
    + cards.NUM_PLAYERS                        # known Re by rel. seat
    + 1                                        # I am Re
    + 1                                        # tricks completed
    + 1                                        # points in current trick
    + 1                                        # my cards remaining
)


def encode(state, player):
  """Encodes `player`'s view of `state` as a float32 feature vector.

  Only uses information visible to `player`: own hand, public history,
  and own team membership.
  """
  x = np.zeros(NUM_FEATURES, np.float32)
  i = 0

  def rel(seat):
    return (seat - player) % cards.NUM_PLAYERS

  hand = state.hands[player]
  x[i:i + cards.NUM_CARD_TYPES] = [n / 2.0 for n in hand]
  i += cards.NUM_CARD_TYPES

  for k, c in enumerate(state.current_trick):
    seat = (state.trick_leader + k) % cards.NUM_PLAYERS
    x[i + rel(seat) * cards.NUM_CARD_TYPES + c] = 1.0
  i += cards.NUM_PLAYERS * cards.NUM_CARD_TYPES

  x[i + rel(state.trick_leader)] = 1.0
  i += cards.NUM_PLAYERS

  for seat, pts in enumerate(state.points_taken()):
    x[i + rel(seat)] = pts / cards.TOTAL_POINTS
  i += cards.NUM_PLAYERS

  played = worlds.played_counts(state)
  x[i:i + cards.NUM_CARD_TYPES] = [n / 2.0 for n in played]
  i += cards.NUM_CARD_TYPES

  for seat, void in enumerate(worlds.infer_voids(state)):
    for cls in void:
      x[i + rel(seat) * _NUM_CLASSES + _CLASS_INDEX[cls]] = 1.0
  i += cards.NUM_PLAYERS * _NUM_CLASSES

  known_re = state.known_re_players()
  for seat in known_re:
    x[i + rel(seat)] = 1.0
  i += cards.NUM_PLAYERS

  x[i] = 1.0 if player in state.re_players else 0.0
  i += 1
  x[i] = len(state.tricks) / cards.NUM_TRICKS
  i += 1
  x[i] = sum(cards.card_points(c) for c in state.current_trick) / 40.0
  i += 1
  x[i] = sum(hand) / cards.CARDS_PER_PLAYER
  i += 1
  assert i == NUM_FEATURES
  return x


def legal_mask(legal):
  mask = np.zeros(cards.NUM_CARD_TYPES, bool)
  mask[list(legal)] = True
  return mask


class PolicyNet:
  """MLP with relu hidden layers, masked softmax output, Adam updates."""

  def __init__(self, hidden=(160, 96), seed=0):
    rng = np.random.default_rng(seed)
    sizes = [NUM_FEATURES, *hidden, cards.NUM_CARD_TYPES]
    self.weights = []
    self.biases = []
    for fan_in, fan_out in zip(sizes[:-1], sizes[1:]):
      scale = np.sqrt(2.0 / fan_in)
      self.weights.append(rng.normal(0, scale, (fan_in, fan_out))
                          .astype(np.float32))
      self.biases.append(np.zeros(fan_out, np.float32))
    self._adam_m = [np.zeros_like(w) for w in self._params()]
    self._adam_v = [np.zeros_like(w) for w in self._params()]
    self._adam_t = 0

  def _params(self):
    return self.weights + self.biases

  # --- Inference ---

  def logits(self, x):
    """Forward pass; `x` is (batch, NUM_FEATURES) or (NUM_FEATURES,)."""
    single = x.ndim == 1
    h = x[None, :] if single else x
    for w, b in zip(self.weights[:-1], self.biases[:-1]):
      h = np.maximum(h @ w + b, 0.0)
    out = h @ self.weights[-1] + self.biases[-1]
    return out[0] if single else out

  def probs(self, x, mask):
    """Masked softmax over card types. Shapes follow `logits`."""
    z = self.logits(x)
    z = np.where(mask, z, -np.inf)
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)

  def act(self, state, player, legal, rng=None, temperature=0.0):
    """Picks a legal card: greedy by default, sampled if temperature>0."""
    p = self.probs(encode(state, player), legal_mask(legal))
    if temperature > 0 and rng is not None:
      z = np.log(np.maximum(p, 1e-12)) / temperature
      z -= z.max()
      p = np.exp(z)
      p /= p.sum()
      return rng.choices(range(cards.NUM_CARD_TYPES), p)[0]
    return int(np.argmax(p))

  # --- Training ---

  def train_step(self, x, targets, masks, lr=1e-3):
    """One Adam step of masked cross-entropy on a batch.

    Args:
      x: (batch, NUM_FEATURES) float32.
      targets: (batch,) int card-type labels chosen by the expert.
      masks: (batch, NUM_CARD_TYPES) bool legality masks.
      lr: Adam learning rate.

    Returns:
      Mean cross-entropy loss of the batch (before the update).
    """
    batch = x.shape[0]
    activations = [x]
    h = x
    for w, b in zip(self.weights[:-1], self.biases[:-1]):
      h = np.maximum(h @ w + b, 0.0)
      activations.append(h)
    z = h @ self.weights[-1] + self.biases[-1]

    z = np.where(masks, z, -1e30)
    z_shift = z - z.max(axis=1, keepdims=True)
    e = np.exp(z_shift)
    p = e / e.sum(axis=1, keepdims=True)
    loss = -np.mean(np.log(np.maximum(p[np.arange(batch), targets], 1e-12)))

    dz = p.copy()
    dz[np.arange(batch), targets] -= 1.0
    dz[~masks] = 0.0
    dz /= batch

    grads_w = [None] * len(self.weights)
    grads_b = [None] * len(self.biases)
    delta = dz
    for layer in range(len(self.weights) - 1, -1, -1):
      grads_w[layer] = activations[layer].T @ delta
      grads_b[layer] = delta.sum(axis=0)
      if layer > 0:
        delta = (delta @ self.weights[layer].T) * (activations[layer] > 0)

    self._adam_t += 1
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    params = self._params()
    grads = grads_w + grads_b
    for j, (param, grad) in enumerate(zip(params, grads)):
      self._adam_m[j] = beta1 * self._adam_m[j] + (1 - beta1) * grad
      self._adam_v[j] = beta2 * self._adam_v[j] + (1 - beta2) * grad * grad
      m_hat = self._adam_m[j] / (1 - beta1 ** self._adam_t)
      v_hat = self._adam_v[j] / (1 - beta2 ** self._adam_t)
      param -= lr * m_hat / (np.sqrt(v_hat) + eps)
    return float(loss)

  # --- Persistence ---

  def save(self, path):
    arrays = {}
    for k, w in enumerate(self.weights):
      arrays[f"w{k}"] = w
    for k, b in enumerate(self.biases):
      arrays[f"b{k}"] = b
    np.savez(path, **arrays)

  @classmethod
  def load(cls, path):
    data = np.load(path)
    n_layers = sum(1 for key in data.files if key.startswith("w"))
    if data["w0"].shape[0] != NUM_FEATURES:
      raise ValueError(
          f"checkpoint expects {data['w0'].shape[0]} features, code has "
          f"{NUM_FEATURES}; the feature encoding changed since training")
    net = cls(hidden=tuple(data[f"w{k}"].shape[1]
                           for k in range(n_layers - 1)))
    net.weights = [data[f"w{k}"].astype(np.float32)
                   for k in range(n_layers)]
    net.biases = [data[f"b{k}"].astype(np.float32)
                  for k in range(n_layers)]
    net._adam_m = [np.zeros_like(w) for w in net._params()]
    net._adam_v = [np.zeros_like(w) for w in net._params()]
    net._adam_t = 0
    return net

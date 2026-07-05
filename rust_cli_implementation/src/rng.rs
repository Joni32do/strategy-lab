//! Deterministic RNG (mulberry32), ported from the original Strategy Lab.
//!
//! Every match/game derives its own seed, so any run can be replayed exactly.
//! Hand-rolled on purpose: no `rand` dependency, identical stream on every
//! platform, trivially seedable for reproducible tests.

#[derive(Clone, Debug)]
pub struct Rng {
    state: u32,
}

impl Rng {
    pub fn new(seed: u32) -> Self {
        Rng { state: seed }
    }

    /// Uniform f64 in [0, 1).
    pub fn next_f64(&mut self) -> f64 {
        // mulberry32
        self.state = self.state.wrapping_add(0x6D2B79F5);
        let mut t = self.state;
        t = (t ^ (t >> 15)).wrapping_mul(t | 1);
        t ^= t.wrapping_add((t ^ (t >> 7)).wrapping_mul(t | 61));
        ((t ^ (t >> 14)) as f64) / 4294967296.0
    }

    /// Uniform integer in [0, n).
    pub fn below(&mut self, n: usize) -> usize {
        (self.next_f64() * n as f64) as usize
    }

    /// Pick a uniformly random element of a non-empty slice.
    pub fn choice<'a, T>(&mut self, items: &'a [T]) -> &'a T {
        &items[self.below(items.len())]
    }

    /// A 1..=6 die roll.
    pub fn die(&mut self) -> u8 {
        1 + self.below(6) as u8
    }
}

/// Spread successive game indices far apart in seed-space (prime stride),
/// mirroring the original engine so matches stay reproducible game-by-game.
pub fn game_seed(base: u32, index: usize) -> u32 {
    base.wrapping_add((index as u32).wrapping_mul(7919))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deterministic_for_seed() {
        let a: Vec<f64> = {
            let mut r = Rng::new(42);
            (0..8).map(|_| r.next_f64()).collect()
        };
        let b: Vec<f64> = {
            let mut r = Rng::new(42);
            (0..8).map(|_| r.next_f64()).collect()
        };
        assert_eq!(a, b);
    }

    #[test]
    fn below_in_range() {
        let mut r = Rng::new(7);
        for _ in 0..10_000 {
            let v = r.below(9);
            assert!(v < 9);
        }
    }

    #[test]
    fn roughly_uniform() {
        let mut r = Rng::new(123);
        let mut buckets = [0u32; 6];
        for _ in 0..60_000 {
            buckets[r.below(6)] += 1;
        }
        // Each bucket should be near 10k; allow generous slack.
        for b in buckets {
            assert!(b > 8_500 && b < 11_500, "bucket skew: {:?}", buckets);
        }
    }
}

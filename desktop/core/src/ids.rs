//! Client-side ULID generation.
//!
//! The desktop app assigns an id to a message the moment the user hits enter,
//! so the optimistic bubble in the transcript and the server's stored row
//! share one identity. Monotonic within the process, matching the server's
//! generator, so `ORDER BY id` and local sorting agree.

use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use parking_lot::Mutex;

const CROCKFORD: &[u8; 32] = b"0123456789ABCDEFGHJKMNPQRSTVWXYZ";

static LAST: Mutex<(u64, u128)> = Mutex::new((0, 0));
static COUNTER: AtomicU64 = AtomicU64::new(0);

fn encode(mut value: u128, length: usize) -> String {
    let mut buf = vec![b'0'; length];
    for slot in buf.iter_mut().rev() {
        *slot = CROCKFORD[(value & 0x1f) as usize];
        value >>= 5;
    }
    // Safe: every byte came from CROCKFORD, which is ASCII.
    String::from_utf8(buf).expect("crockford alphabet is ascii")
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        // A clock before the epoch is nonsense; 0 keeps ids valid rather than
        // panicking in a UI thread.
        .unwrap_or(0)
}

fn random_80() -> u128 {
    use rand::RngCore;
    let mut bytes = [0u8; 16];
    rand::thread_rng().fill_bytes(&mut bytes[6..]);
    u128::from_be_bytes(bytes)
}

/// A fresh 26-character ULID.
pub fn new_ulid() -> String {
    let ts = now_ms();
    let randomness = {
        let mut last = LAST.lock();
        if ts > last.0 {
            // Halve the entropy space so a burst inside one millisecond cannot
            // overflow into the next timestamp.
            *last = (ts, random_80() >> 1);
        } else {
            last.1 = last.1.wrapping_add(1);
        }
        last.1
    };
    format!("{}{}", encode(ts as u128, 10), encode(randomness, 16))
}

/// A short opaque id for things that need uniqueness but not ordering
/// (outbox rows, panel sessions, request correlation).
pub fn new_correlation_id() -> String {
    format!(
        "{:x}-{:x}",
        now_ms(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    )
}

/// Extract the embedded millisecond timestamp, or `None` if not a ULID.
pub fn ulid_timestamp_ms(value: &str) -> Option<u64> {
    if value.len() != 26 {
        return None;
    }
    let mut ts: u64 = 0;
    for ch in value[..10].bytes() {
        let digit = decode_char(ch)?;
        ts = (ts << 5) | u64::from(digit);
    }
    Some(ts)
}

fn decode_char(ch: u8) -> Option<u8> {
    let upper = ch.to_ascii_uppercase();
    match upper {
        b'0'..=b'9' => Some(upper - b'0'),
        // Crockford maps these to their digit look-alikes.
        b'O' => Some(0),
        b'I' | b'L' => Some(1),
        b'U' => None,
        b'A'..=b'Z' => CROCKFORD.iter().position(|&c| c == upper).map(|p| p as u8),
        _ => None,
    }
}

pub fn is_ulid(value: &str) -> bool {
    value.len() == 26 && value.bytes().all(|b| decode_char(b).is_some())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ulids_are_26_chars_and_valid() {
        let id = new_ulid();
        assert_eq!(id.len(), 26);
        assert!(is_ulid(&id));
    }

    #[test]
    fn ulids_are_monotonic_and_unique_in_a_burst() {
        // A burst inside one millisecond is exactly the case plain random
        // ULIDs get wrong, and the case a fast typist produces.
        let ids: Vec<String> = (0..5_000).map(|_| new_ulid()).collect();
        let mut sorted = ids.clone();
        sorted.sort();
        assert_eq!(ids, sorted, "ulids must sort in creation order");

        let unique: std::collections::HashSet<_> = ids.iter().collect();
        assert_eq!(unique.len(), ids.len(), "ulids must be unique");
    }

    #[test]
    fn timestamp_round_trips() {
        let before = now_ms();
        let id = new_ulid();
        let after = now_ms();
        let ts = ulid_timestamp_ms(&id).expect("should parse");
        assert!(
            ts >= before && ts <= after,
            "{ts} not within {before}..{after}"
        );
    }

    #[test]
    fn rejects_non_ulids() {
        assert!(!is_ulid("too-short"));
        assert!(
            !is_ulid(&"U".repeat(26)),
            "U is excluded from crockford base32"
        );
        assert!(ulid_timestamp_ms("nope").is_none());
    }
}

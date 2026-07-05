//! A deliberately tiny blocking HTTP/1.1 client, just enough to talk to the
//! catanatron bridge (`catan-server/app.py`) over loopback.
//!
//! We don't pull in a full HTTP crate: the surface we need is one GET and one
//! POST against `127.0.0.1:8000`, returning JSON. The bridge answers with a
//! `Content-Length` and closes the connection (HTTP/1.0), so "read to EOF, split
//! on the blank line, parse the body as JSON" is a complete and correct client
//! for this one peer. Every call has a short timeout so a missing/slow server
//! degrades to an error message instead of hanging the TUI.

use std::io::{Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

use serde_json::Value;

/// Where the catanatron server lives. Matches `app.run(host, port)` in
/// `strategy-lab/server/app.py`.
#[derive(Clone)]
pub struct CatanClient {
    pub host: String,
    pub port: u16,
    /// Per-request ceiling. Simulations of many games can take a while, so this
    /// is generous; connect failures are detected far faster.
    pub timeout: Duration,
}

impl Default for CatanClient {
    fn default() -> Self {
        CatanClient {
            host: "127.0.0.1".into(),
            port: 8000,
            timeout: Duration::from_secs(120),
        }
    }
}

impl CatanClient {
    pub fn base(&self) -> String {
        format!("{}:{}", self.host, self.port)
    }

    pub fn get(&self, path: &str) -> Result<Value, String> {
        self.request("GET", path, None)
    }

    pub fn post(&self, path: &str, body: &Value) -> Result<Value, String> {
        self.request("POST", path, Some(body))
    }

    fn request(&self, method: &str, path: &str, body: Option<&Value>) -> Result<Value, String> {
        let addr = self
            .base()
            .to_socket_addrs()
            .map_err(|e| format!("bad address {}: {e}", self.base()))?
            .next()
            .ok_or_else(|| format!("could not resolve {}", self.base()))?;

        // A tight connect timeout so "server not running" fails fast.
        let mut stream = TcpStream::connect_timeout(&addr, Duration::from_millis(800))
            .map_err(|e| format!("can't reach catanatron server at {} ({e})", self.base()))?;
        stream.set_read_timeout(Some(self.timeout)).ok();
        stream.set_write_timeout(Some(self.timeout)).ok();

        let payload = body.map(|b| b.to_string()).unwrap_or_default();
        let mut req = format!(
            "{method} {path} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\nAccept: application/json\r\n",
            self.host
        );
        if body.is_some() {
            req.push_str("Content-Type: application/json\r\n");
            req.push_str(&format!("Content-Length: {}\r\n", payload.len()));
        }
        req.push_str("\r\n");
        req.push_str(&payload);

        stream
            .write_all(req.as_bytes())
            .map_err(|e| format!("write failed: {e}"))?;
        stream.flush().ok();

        let mut raw = Vec::new();
        stream
            .read_to_end(&mut raw)
            .map_err(|e| format!("read failed: {e}"))?;

        let split = find_subslice(&raw, b"\r\n\r\n")
            .map(|i| i + 4)
            .or_else(|| find_subslice(&raw, b"\n\n").map(|i| i + 2))
            .ok_or_else(|| "malformed HTTP response (no header terminator)".to_string())?;

        let header = String::from_utf8_lossy(&raw[..split]);
        let status = header
            .lines()
            .next()
            .and_then(|l| l.split_whitespace().nth(1))
            .and_then(|c| c.parse::<u16>().ok())
            .unwrap_or(0);

        let body_bytes = &raw[split..];
        let value: Value = serde_json::from_slice(body_bytes).map_err(|e| {
            if status >= 400 {
                format!("server returned HTTP {status}")
            } else {
                format!("invalid JSON from server: {e}")
            }
        })?;

        if status >= 400 {
            let msg = value
                .get("error")
                .and_then(|v| v.as_str())
                .unwrap_or("request failed");
            return Err(format!("HTTP {status}: {msg}"));
        }
        Ok(value)
    }
}

fn find_subslice(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    if needle.is_empty() || haystack.len() < needle.len() {
        return None;
    }
    haystack
        .windows(needle.len())
        .position(|w| w == needle)
}

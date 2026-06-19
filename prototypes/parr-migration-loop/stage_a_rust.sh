#!/usr/bin/env bash
# Stage A (coder stand-in) — author a faithful Rust rewrite + the parity_harness,
# then `cargo build`. In production this is the AIFactory coder generating against
# the read-only oracle + MIGRATION_BRIEF.md; here it is hand-authored so the loop
# runs deterministically.
set -euo pipefail
CRATE="$1"
mkdir -p "$CRATE/src/pay" "$CRATE/src/bin"

cat > "$CRATE/Cargo.toml" <<'TOML'
[package]
name = "port"
version = "0.1.0"
edition = "2021"

[lib]
path = "src/lib.rs"

[[bin]]
name = "parity_harness"
path = "src/bin/parity_harness.rs"

[dependencies]
serde_json = "1"
TOML

echo 'pub mod pay;' > "$CRATE/src/lib.rs"
echo 'pub mod refund;' > "$CRATE/src/pay/mod.rs"

cat > "$CRATE/src/pay/refund.rs" <<'RS'
use serde_json::{json, Value};

/// Mirror of Python refund(): error on non-positive amount, else echo a record.
pub fn refund(amount: &Value, reason: &Value) -> Result<Value, &'static str> {
    if amount.as_f64().unwrap_or(0.0) <= 0.0 {
        return Err("InvalidInput");
    }
    Ok(json!({"refunded": amount.clone(), "reason": reason.clone()}))
}

/// Mirror of Python fee(): round(amount * 0.029 + 0.30, 2).
pub fn fee(amount: &Value) -> f64 {
    let a = amount.as_f64().unwrap_or(0.0);
    ((a * 0.029 + 0.30) * 100.0).round() / 100.0
}
RS

cat > "$CRATE/src/bin/parity_harness.rs" <<'RS'
use port::pay::refund;
use serde_json::{json, Value};
use std::io::Read;

fn main() {
    let mut raw = String::new();
    let args: Vec<String> = std::env::args().collect();
    if args.len() > 1 {
        raw = std::fs::read_to_string(&args[1]).unwrap_or_default();
    } else {
        std::io::stdin().read_to_string(&mut raw).ok();
    }
    let vectors: Vec<Value> = serde_json::from_str(&raw).unwrap_or_default();
    let mut out: Vec<Value> = Vec::new();
    for v in &vectors {
        let id = v.get("id").cloned().unwrap_or(Value::Null);
        let func = v.get("function").and_then(|f| f.as_str()).unwrap_or("");
        let a = v.get("args").and_then(|a| a.as_array()).cloned().unwrap_or_default();
        let null = Value::Null;
        let rec = match func {
            "refund" => match refund::refund(a.get(0).unwrap_or(&null), a.get(1).unwrap_or(&null)) {
                Ok(o) => json!({"id": id, "output": o}),
                Err(e) => json!({"id": id, "error": e}),
            },
            "fee" => json!({"id": id, "output": refund::fee(a.get(0).unwrap_or(&null))}),
            _ => json!({"id": id, "error": "UnknownFunction"}),
        };
        out.push(rec);
    }
    println!("{}", serde_json::to_string(&out).unwrap());
}
RS

( cd "$CRATE" && cargo build --quiet --bins )
echo "   built: $CRATE/target/debug/parity_harness"

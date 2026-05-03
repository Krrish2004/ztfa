//! ZTFA prover binary (v1).
//!
//! Wraps `snarkjs groth16 prove` for the v1 demo. The HLD recommends
//! rapidsnark (5-10× faster) but rapidsnark requires significant build
//! infrastructure (gmp, custom CMake). For our 7.6k-constraint v1 circuit,
//! snarkjs proves in <2s — fast enough that the rapidsnark complexity isn't
//! justified.
//!
//! v2: swap the inner subprocess to rapidsnark; no API change required since
//! the I/O contract (witness in, proof.json + public.json out) is identical.
//!
//! CLI:
//!   ztfa-prove --zkey <path> --witness <path> \
//!              --proof-out <path> --public-out <path>

use anyhow::{Context, Result};
use clap::Parser;
use std::path::PathBuf;
use std::process::Command;

#[derive(Parser, Debug)]
#[command(name = "ztfa-prove", version)]
struct Args {
    /// Path to circuit-specific .zkey (output of phase-2 ceremony)
    #[arg(long)]
    zkey: PathBuf,

    /// Path to .wtns witness (built by ztfa_crypto.witness)
    #[arg(long)]
    witness: PathBuf,

    /// Output path for proof.json
    #[arg(long, default_value = "proof.json")]
    proof_out: PathBuf,

    /// Output path for public.json
    #[arg(long, default_value = "public.json")]
    public_out: PathBuf,

    /// Path to snarkjs CLI. Default: $ZTFA_ROOT/circuits/node_modules/snarkjs/cli.js
    #[arg(long)]
    snarkjs_cli: Option<PathBuf>,
}

fn main() -> Result<()> {
    let args = Args::parse();

    let snarkjs_cli = args.snarkjs_cli.unwrap_or_else(|| {
        let root = std::env::var("ZTFA_ROOT").unwrap_or_else(|_| ".".into());
        PathBuf::from(root)
            .join("circuits")
            .join("node_modules")
            .join("snarkjs")
            .join("cli.js")
    });

    if !snarkjs_cli.exists() {
        anyhow::bail!(
            "snarkjs CLI not found at {}. Set --snarkjs-cli or run `npm install` in circuits/.",
            snarkjs_cli.display()
        );
    }
    if !args.zkey.exists() {
        anyhow::bail!("zkey not found: {}", args.zkey.display());
    }
    if !args.witness.exists() {
        anyhow::bail!("witness not found: {}", args.witness.display());
    }

    let status = Command::new("node")
        .arg(&snarkjs_cli)
        .arg("groth16")
        .arg("prove")
        .arg(&args.zkey)
        .arg(&args.witness)
        .arg(&args.proof_out)
        .arg(&args.public_out)
        .status()
        .context("failed to spawn node + snarkjs")?;

    if !status.success() {
        anyhow::bail!("snarkjs groth16 prove exited with {status}");
    }

    // Sanity check that JSON files were written
    let _: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(&args.proof_out)
            .context("proof.json not written")?,
    )?;
    let _: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(&args.public_out)
            .context("public.json not written")?,
    )?;

    eprintln!(
        "✓ proof → {} ; public → {}",
        args.proof_out.display(),
        args.public_out.display()
    );
    Ok(())
}

//! Smoke test — spawns the prover binary against the existing fixture witness
//! and asserts proof.json + public.json are produced.

use std::path::PathBuf;
use std::process::Command;

#[test]
fn prover_smoke() {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let root = manifest.parent().unwrap();
    let zkey = root.join("circuits/build/aggregation_final.zkey");
    let witness = root.join("circuits/build/fixture_witness.wtns");
    if !zkey.exists() || !witness.exists() {
        eprintln!(
            "skip: missing artifacts. Run `bash circuits/scripts/setup.sh` and \
             `python3 scripts/gen_fixture.py`"
        );
        return;
    }

    let tmp = std::env::temp_dir();
    let proof_out = tmp.join("ztfa_smoke_proof.json");
    let public_out = tmp.join("ztfa_smoke_public.json");

    let bin = manifest.join("target/release/ztfa-prove");
    let bin = if bin.exists() {
        bin
    } else {
        manifest.join("target/debug/ztfa-prove")
    };

    let status = Command::new(&bin)
        .args([
            "--zkey",
            zkey.to_str().unwrap(),
            "--witness",
            witness.to_str().unwrap(),
            "--proof-out",
            proof_out.to_str().unwrap(),
            "--public-out",
            public_out.to_str().unwrap(),
        ])
        .env("ZTFA_ROOT", root)
        .status()
        .expect("spawn ztfa-prove");
    assert!(status.success());
    assert!(proof_out.exists());
    assert!(public_out.exists());
}

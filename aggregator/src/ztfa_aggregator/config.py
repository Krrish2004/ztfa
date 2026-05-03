"""Aggregator configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Federation
    n_clients: int = Field(default=3, alias="N_CLIENTS")
    per_client_fee_wei: int = Field(default=int(5e14), alias="PER_CLIENT_FEE_WEI")
    aggregator_payment_wei: int = Field(default=int(1e15), alias="AGGREGATOR_PAYMENT_WEI")
    round_period_sec: int = Field(default=600, alias="ROUND_PERIOD_SEC")

    # Chain
    chain_rpc_url: str = Field(default="http://localhost:8545", alias="CHAIN_RPC_URL")
    chain_id: int = Field(default=31337, alias="CHAIN_ID")
    aggregator_private_key: str = Field(
        default="0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
        alias="AGGREGATOR_PRIVATE_KEY",
    )
    federation_round_address: str = Field(default="", alias="FEDERATION_ROUND_ADDRESS")

    # Storage
    database_url: str = Field(
        default="sqlite+aiosqlite:///./aggregator.sqlite", alias="DATABASE_URL"
    )
    s3_endpoint: str = Field(default="http://localhost:9000", alias="S3_ENDPOINT")
    s3_access_key: str = Field(default="ztfa", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="ztfa_dev_minio", alias="S3_SECRET_KEY")
    s3_ciphertext_bucket: str = Field(default="ciphertexts", alias="S3_CIPHERTEXT_BUCKET")
    s3_aggregate_bucket: str = Field(default="aggregates", alias="S3_AGGREGATE_BUCKET")

    # Crypto paths
    keys_dir: Path = Field(default=Path("./keys"), alias="KEYS_DIR")
    circuit_build_dir: Path = Field(
        default=Path("./circuits/build"), alias="CIRCUIT_BUILD_DIR"
    )

    @property
    def public_context_path(self) -> Path:
        return self.keys_dir / "ckks_public.bin"

    @property
    def zkey_path(self) -> Path:
        return self.circuit_build_dir / "aggregation_final.zkey"

    @property
    def wasm_path(self) -> Path:
        return self.circuit_build_dir / "aggregation_js" / "aggregation.wasm"

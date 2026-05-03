"""Client config (env-driven)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    client_id: int = Field(default=0, alias="ZTFA_CLIENT_ID")
    client_private_key: str = Field(
        default="0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
        alias="ZTFA_CLIENT_PRIVATE_KEY",
    )
    aggregator_url: str = Field(default="http://localhost:8000", alias="ZTFA_AGGREGATOR_URL")
    chain_rpc_url: str = Field(default="http://localhost:8545", alias="CHAIN_RPC_URL")
    chain_id: int = Field(default=31337, alias="CHAIN_ID")
    federation_round_address: str = Field(default="", alias="FEDERATION_ROUND_ADDRESS")
    per_client_fee_wei: int = Field(default=int(5e14), alias="PER_CLIENT_FEE_WEI")

    mqtt_host: str = Field(default="localhost", alias="MQTT_HOST")
    mqtt_port: int = Field(default=1883, alias="MQTT_PORT")
    n_clients: int = Field(default=3, alias="N_CLIENTS")

    keys_dir: Path = Field(default=Path("./keys"), alias="KEYS_DIR")
    data_dir: Path = Field(default=Path("./client/data"), alias="ZTFA_CLIENT_DATA_DIR")
    local_rpc_port: int = Field(default=7000, alias="ZTFA_LOCAL_RPC_PORT")

    @property
    def full_context_path(self) -> Path:
        return self.keys_dir / "ckks_full.bin"

    @property
    def feature_norm_path(self) -> Path:
        return self.keys_dir / "feature_norm.json"

    @property
    def initial_weights_path(self) -> Path:
        return self.keys_dir / "w_global_round_0.pt"
